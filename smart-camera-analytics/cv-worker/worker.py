"""
Smart Camera Analytics - CV Worker
===================================
Reads video stream → detects persons (YOLOv8) → tracks (centroid matching)
→ computes zone/dwell analytics → sends metadata to Backend.

Privacy-First:
- No images are stored or transmitted.
- No face recognition or identity matching.
- Only metadata: bounding boxes (coords), centroids, dwell times, zone info.
- Apparent expression is probabilistic and visual-only (not biometric).
- tracking_id is session-scoped, resets on restart, never linked to identity.

Usage:
    python worker.py --config config.example.json
    python worker.py --source 0 --camera-id 1
    python worker.py --source /videos/test.mp4 --camera-id 1
    python worker.py --source rtsp://192.168.1.100:554/stream1 --camera-id 1
"""
import os
import json
import time
import logging
import argparse
import threading
from datetime import datetime, timezone
from typing import List, Dict, Optional

import cv2
import numpy as np
import requests

from frame_source import FrameSource
from tracker import CentroidTracker
from expression_utils import analyze_apparent_expression, load_face_detector
from zone_utils import get_zone_for_point

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
DEFAULT_CONFIG = {
    "backend_url": os.getenv("BACKEND_URL", "http://localhost:8000"),
    "camera_id": int(os.getenv("CAMERA_ID", "1")),
    "video_source": os.getenv("VIDEO_SOURCE", "0"),
    "yolo_model": "yolov8n.pt",           # nano model - fast
    "confidence_threshold": 0.4,
    "send_interval_seconds": 1.5,          # how often to POST metadata
    "show_preview": True,                  # local OpenCV preview window
    "frame_skip": 2,                       # process every Nth frame
    "max_tracker_distance": 80,
    "max_tracker_disappeared": 25,
    "analysis_fps": int(os.getenv("ANALYSIS_FPS", "5")),
    "analysis_refresh_seconds": int(os.getenv("ANALYSIS_REFRESH_SECONDS", "30")),
    "auto_discover_cameras": os.getenv("AUTO_DISCOVER_CAMERAS", "false").lower() == "true",
    "analysis_camera_ids": os.getenv("ANALYSIS_CAMERA_IDS", ""),
}


class CVWorker:
    def __init__(self, config: dict, stop_event: Optional[threading.Event] = None):
        self.config = config
        self.camera_id: int = config["camera_id"]
        self.backend_url: str = config["backend_url"].rstrip("/")
        self.ingest_api_key: str = os.getenv("INGEST_API_KEY", "")
        self.stop_event = stop_event or threading.Event()
        self.zones: List[Dict] = []

        # YOLOv8 model
        logger.info("Loading YOLOv8 model...")
        try:
            from ultralytics import YOLO
            self.model = YOLO(config["yolo_model"])
            self.use_yolo = True
            logger.info(f"✅ YOLOv8 loaded: {config['yolo_model']}")
        except Exception as e:
            logger.warning(f"⚠️  YOLOv8 not available ({e}). Using fallback HOG detector.")
            self.model = None
            self.use_yolo = False

        # Tracker
        self.tracker = CentroidTracker(
            max_disappeared=config.get("max_tracker_disappeared", 25),
            max_distance=config.get("max_tracker_distance", 80),
        )

        # Face detector (for expression analysis)
        self.face_detector = load_face_detector()

        # Metadata buffer for batched sending
        self._last_send_time = 0.0
        self._send_lock = threading.Lock()

        # HOG fallback
        self._hog = cv2.HOGDescriptor()
        self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def fetch_zones(self):
        """Fetch zone definitions from backend."""
        try:
            resp = requests.get(
                f"{self.backend_url}/internal/cameras/{self.camera_id}/zones",
                headers={"X-API-Key": self.ingest_api_key},
                timeout=5
            )
            if resp.status_code == 200:
                self.zones = resp.json()
                logger.info(f"✅ Loaded {len(self.zones)} zones for camera {self.camera_id}")
            else:
                logger.warning(f"Could not fetch zones: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Zone fetch failed: {e}. Running without zones.")

    def detect_persons_yolo(self, frame: np.ndarray) -> List[Dict]:
        """Detect persons using YOLOv8. Class 0 = person."""
        results = self.model(
            frame,
            classes=[0],  # person only
            conf=self.config.get("confidence_threshold", 0.4),
            verbose=False
        )
        detections = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                detections.append({"bbox": [x1, y1, x2, y2], "confidence": conf})
        return detections

    def detect_persons_hog(self, frame: np.ndarray) -> List[Dict]:
        """Fallback HOG person detector when YOLO unavailable."""
        gray = cv2.resize(frame, (320, 240))
        scale = frame.shape[1] / 320.0
        rects, weights = self._hog.detectMultiScale(
            gray, winStride=(8, 8), padding=(4, 4), scale=1.05
        )
        detections = []
        for (x, y, w, h), weight in zip(rects, weights):
            if weight[0] > 0.3:
                detections.append({
                    "bbox": [x*scale, y*scale*1.25, (x+w)*scale, (y+h)*scale*1.25],
                    "confidence": float(weight[0])
                })
        return detections

    def send_metadata(self, frame_people_count: int, tracked_persons, frame_shape):
        """POST metadata batch to backend. No images sent."""
        now = time.time()
        if now - self._last_send_time < self.config.get("send_interval_seconds", 1.5):
            return
        self._last_send_time = now

        # Build zone counts
        zone_counts = {}
        for p in tracked_persons:
            if p.zone_name:
                zone_counts[p.zone_name] = zone_counts.get(p.zone_name, 0) + 1

        payload = {
            "camera_id": self.camera_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "frame_people_count": frame_people_count,
            "zone_counts": zone_counts,
            "tracked_persons": [
                {
                    "tracking_id": p.tracking_id,
                    "bbox": p.bbox,
                    "centroid_x": p.centroid[0],
                    "centroid_y": p.centroid[1],
                    "confidence": None,
                    "zone_id": p.zone_id,
                    "zone_name": p.zone_name,
                    "dwell_seconds": round(p.dwell_seconds, 1),
                    "movement_score": round(p.movement_score, 4),
                    "apparent_expression": p.apparent_expression,
                    "is_new": p.is_new,
                    "zone_entry": p.zone_entry,
                    "zone_exit": p.zone_exit,
                }
                for p in tracked_persons
            ],
        }

        try:
            resp = requests.post(
                f"{self.backend_url}/api/ingest/metadata",
                json=payload,
                headers={"X-API-Key": self.ingest_api_key},
                timeout=3
            )
            if resp.status_code == 200:
                logger.debug(f"Sent metadata: {frame_people_count} persons")
            else:
                logger.warning(f"Backend responded {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            logger.warning(f"Failed to send metadata: {e}")

    def draw_overlay(self, frame: np.ndarray, tracked_persons) -> np.ndarray:
        """Draw bounding boxes, tracking IDs and zone overlays for local preview."""
        overlay = frame.copy()

        # Draw zones
        for zone in self.zones:
            poly = zone.get("polygon_json") or zone.get("polygon", [])
            if poly:
                pts = np.array(poly, dtype=np.int32)
                cv2.polylines(overlay, [pts], True, (0, 255, 255), 1)
                cx = int(np.mean(pts[:, 0]))
                cy = int(np.mean(pts[:, 1]))
                cv2.putText(overlay, zone["name"], (cx-20, cy),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

        # Draw persons
        colors = {
            "apparent_smile": (0, 255, 0),
            "neutral":        (255, 165, 0),
            "face_not_visible": (128, 128, 128),
        }
        for p in tracked_persons:
            x1, y1, x2, y2 = [int(v) for v in p.bbox]
            color = colors.get(p.apparent_expression, (200, 200, 200))
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)

            label = f"{p.tracking_id}"
            if p.zone_name:
                label += f" | {p.zone_name}"
            dwell = int(p.dwell_seconds)
            if dwell > 0:
                label += f" | {dwell}s"

            cv2.putText(overlay, label, (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

        # HUD
        h, w = frame.shape[:2]
        count_text = f"People: {len(tracked_persons)}"
        cv2.rectangle(overlay, (8, 8), (200, 32), (0, 0, 0), -1)
        cv2.putText(overlay, count_text, (12, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

        return overlay

    def run(self):
        """Main processing loop."""
        source = self.config["video_source"]

        # Convert source to int if webcam index
        try:
            source = int(source)
        except (ValueError, TypeError):
            pass

        logger.info(f"🎥 Opening video source: {source}")
        cap = FrameSource(
            source,
            username=self.config.get("cam_username"),
            password=self.config.get("cam_password"),
            fps=self.config.get("analysis_fps", 5),
        )

        if not cap.open():
            logger.error(f"❌ Cannot open video source: {source}")
            return

        # Fetch zones from backend
        self.fetch_zones()

        frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 360
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        logger.info(f"📐 Stream: {frame_w}x{frame_h} @ {fps:.1f}fps")

        frame_count = 0
        frame_skip = self.config.get("frame_skip", 2)
        show_preview = self.config.get("show_preview", True)

        logger.info("▶️  CV Worker started. Press Q to stop.")

        while not self.stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                # End of video file - loop back
                if isinstance(source, str) and not source.lower().startswith("rtsp://"):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    logger.warning("Frame read failed. Retrying...")
                    time.sleep(1.0)
                    continue

            frame_count += 1
            frame_h, frame_w = frame.shape[:2]

            # Skip frames for performance
            if frame_count % frame_skip != 0:
                continue

            # Detect persons
            if self.use_yolo:
                detections = self.detect_persons_yolo(frame)
            else:
                detections = self.detect_persons_hog(frame)

            # Update tracker
            tracked = self.tracker.update(detections, self.zones, frame_w, frame_h)

            # Analyze apparent expression per person (optional, lightweight)
            for person in tracked:
                expr = analyze_apparent_expression(
                    frame, person.bbox, self.face_detector
                )
                person.apparent_expression = expr

            # Send metadata to backend (rate limited)
            self.send_metadata(len(tracked), tracked, frame.shape)

            # Local preview
            if show_preview:
                vis = self.draw_overlay(frame, tracked)
                cv2.imshow("Smart Camera Analytics - CV Worker", vis)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    logger.info("Q pressed - stopping.")
                    break

        cap.release()
        if show_preview:
            cv2.destroyAllWindows()
        logger.info("✅ CV Worker stopped.")


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
def fetch_analysis_cameras(backend_url: str, ingest_api_key: str) -> List[Dict]:
    """Fetch camera configs for background analysis from the protected internal API."""
    resp = requests.get(
        f"{backend_url.rstrip('/')}/internal/cameras/analysis-config",
        headers={"X-API-Key": ingest_api_key},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("cameras", [])


def run_worker_thread(cam_config: dict, stop_event: threading.Event):
    try:
        CVWorker(cam_config, stop_event=stop_event).run()
    except Exception as exc:
        logger.exception(f"Analysis worker crashed for camera {cam_config.get('camera_id')}: {exc}")


def run_auto_discovery(config: dict):
    backend_url = config["backend_url"].rstrip("/")
    ingest_api_key = os.getenv("INGEST_API_KEY", "")
    refresh_seconds = max(5, int(config.get("analysis_refresh_seconds", 30)))
    allowed_ids = {
        int(x.strip()) for x in str(config.get("analysis_camera_ids") or "").split(",")
        if x.strip().isdigit()
    }

    active_workers: Dict[int, Dict] = {}
    logger.info(f"Auto camera analysis enabled. Refreshing camera config every {refresh_seconds}s")

    try:
        while True:
            try:
                cameras = fetch_analysis_cameras(backend_url, ingest_api_key)
                if allowed_ids:
                    cameras = [cam for cam in cameras if int(cam["id"]) in allowed_ids]
            except Exception as exc:
                logger.warning(f"Could not fetch analysis camera config: {exc}")
                time.sleep(refresh_seconds)
                continue

            desired = {int(cam["id"]): cam for cam in cameras}

            for cam_id, worker_state in list(active_workers.items()):
                thread = worker_state["thread"]
                should_stop = cam_id not in desired
                crashed = not thread.is_alive()
                if should_stop or crashed:
                    if should_stop:
                        logger.info(f"Stopping analysis for removed camera {cam_id}")
                    else:
                        logger.warning(f"Analysis worker for camera {cam_id} stopped; it will restart if still configured")
                    worker_state["stop_event"].set()
                    thread.join(timeout=5)
                    active_workers.pop(cam_id, None)

            for cam_id, cam in desired.items():
                if cam_id in active_workers:
                    continue

                cam_config = config.copy()
                cam_config.update({
                    "camera_id": cam_id,
                    "video_source": cam["stream_url"],
                    "cam_username": cam.get("cam_username"),
                    "cam_password": cam.get("cam_password"),
                    "show_preview": False,
                })
                stop_event = threading.Event()
                thread = threading.Thread(
                    target=run_worker_thread,
                    args=(cam_config, stop_event),
                    name=f"camera-{cam_id}-analysis",
                    daemon=False,
                )
                thread.start()
                active_workers[cam_id] = {"thread": thread, "stop_event": stop_event}
                logger.info(f"Started analysis for camera {cam_id} ({cam.get('name', 'unnamed')})")

            if not active_workers:
                logger.warning("No cameras currently available for analysis.")

            time.sleep(refresh_seconds)
    except KeyboardInterrupt:
        logger.info("Stopping all analysis workers...")
        for worker_state in active_workers.values():
            worker_state["stop_event"].set()
        for worker_state in active_workers.values():
            worker_state["thread"].join(timeout=5)


def main():
    parser = argparse.ArgumentParser(description="Smart Camera Analytics CV Worker")
    parser.add_argument("--config", type=str, help="Path to config JSON file")
    parser.add_argument("--source", type=str, help="Video source (0, /path/video.mp4, rtsp://...)")
    parser.add_argument("--camera-id", type=int, help="Backend camera ID")
    parser.add_argument("--backend-url", type=str, help="Backend URL")
    parser.add_argument("--no-preview", action="store_true", help="Disable local preview window")
    parser.add_argument("--auto-cameras", action="store_true", help="Analyze cameras from backend internal config")
    args = parser.parse_args()

    config = DEFAULT_CONFIG.copy()

    # Load from config file
    if args.config:
        with open(args.config) as f:
            file_config = json.load(f)
        config.update(file_config)

    # CLI overrides
    if args.source:
        config["video_source"] = args.source
    if args.camera_id:
        config["camera_id"] = args.camera_id
    if args.backend_url:
        config["backend_url"] = args.backend_url
    if args.no_preview:
        config["show_preview"] = False
    if args.auto_cameras:
        config["auto_discover_cameras"] = True

    if config.get("auto_discover_cameras"):
        run_auto_discovery(config)
    else:
        worker = CVWorker(config)
        worker.run()


if __name__ == "__main__":
    main()

