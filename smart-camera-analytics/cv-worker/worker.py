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
import sys
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
}


class CVWorker:
    def __init__(self, config: dict):
        self.config = config
        self.camera_id: int = config["camera_id"]
        self.backend_url: str = config["backend_url"].rstrip("/")
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
                f"{self.backend_url}/api/cameras/{self.camera_id}/zones",
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
                headers={"X-API-Key": os.getenv("INGEST_API_KEY", "")},
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
        cap = cv2.VideoCapture(source)

        if not cap.isOpened():
            logger.error(f"❌ Cannot open video source: {source}")
            sys.exit(1)

        # Fetch zones from backend
        self.fetch_zones()

        frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        logger.info(f"📐 Stream: {frame_w}x{frame_h} @ {fps:.1f}fps")

        frame_count = 0
        frame_skip = self.config.get("frame_skip", 2)
        show_preview = self.config.get("show_preview", True)

        logger.info("▶️  CV Worker started. Press Q to stop.")

        while True:
            ret, frame = cap.read()
            if not ret:
                # End of video file - loop back
                if isinstance(source, str):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                else:
                    logger.warning("Frame read failed. Retrying...")
                    time.sleep(0.1)
                    continue

            frame_count += 1

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
def main():
    parser = argparse.ArgumentParser(description="Smart Camera Analytics CV Worker")
    parser.add_argument("--config", type=str, help="Path to config JSON file")
    parser.add_argument("--source", type=str, help="Video source (0, /path/video.mp4, rtsp://...)")
    parser.add_argument("--camera-id", type=int, help="Backend camera ID")
    parser.add_argument("--backend-url", type=str, help="Backend URL")
    parser.add_argument("--no-preview", action="store_true", help="Disable local preview window")
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

    worker = CVWorker(config)
    worker.run()


if __name__ == "__main__":
    main()
