"""
Simple Centroid-Based Person Tracker

MVP implementation using centroid distance matching.
TODO: Replace with ByteTrack for production-quality tracking:
      pip install bytetracker
      from bytetracker import BYTETracker

Privacy: tracking_id is a session-scoped integer, NOT linked to identity.
IDs are assigned per session and reset on worker restart.
"""
import time
import math
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from collections import deque


@dataclass
class TrackedPerson:
    tracking_id: str
    bbox: List[float]           # [x1, y1, x2, y2]
    centroid: Tuple[float, float]
    first_seen: float           # unix timestamp
    last_seen: float
    zone_id: Optional[int]
    zone_name: Optional[str]
    dwell_seconds: float
    movement_score: float
    apparent_expression: str
    frames_seen: int
    centroid_history: deque = field(default_factory=lambda: deque(maxlen=30))
    zone_entry: bool = False    # True for one frame on zone entry
    zone_exit: bool = False     # True for one frame on zone exit
    is_new: bool = True         # True on first detection


class CentroidTracker:
    """
    Centroid matching tracker.
    Matches new detections to existing tracks by nearest centroid.
    
    TODO: For production, replace with ByteTrack:
    
    from ultralytics import YOLO
    model = YOLO("yolov8n.pt")
    results = model.track(frame, persist=True, tracker="bytetrack.yaml")
    # Results will have .boxes.id for tracking IDs
    """

    def __init__(
        self,
        max_disappeared: int = 30,      # frames before removing a track
        max_distance: float = 80.0,     # max centroid distance to match
    ):
        self.max_disappeared = max_disappeared
        self.max_distance = max_distance
        self._next_id = 1
        self._tracks: Dict[str, TrackedPerson] = {}
        self._disappeared: Dict[str, int] = {}

    def _centroid(self, bbox: List[float]) -> Tuple[float, float]:
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def _distance(self, c1: Tuple, c2: Tuple) -> float:
        return math.sqrt((c1[0] - c2[0])**2 + (c1[1] - c2[1])**2)

    def _make_id(self) -> str:
        tid = f"T{self._next_id:04d}"
        self._next_id += 1
        return tid

    def update(
        self,
        detections: List[Dict],     # list of {bbox, confidence}
        zones: List[Dict],          # list of zone dicts
        frame_w: int = 640,
        frame_h: int = 480,
    ) -> List[TrackedPerson]:
        """
        Update tracks with new detections.
        Returns list of currently active TrackedPerson objects.
        """
        from zone_utils import get_zone_for_point, calculate_movement_score

        now = time.time()

        # Reset zone entry/exit flags
        for t in self._tracks.values():
            t.zone_entry = False
            t.zone_exit = False
            t.is_new = False

        if not detections:
            # Mark all tracks as disappeared
            for tid in list(self._disappeared.keys()):
                self._disappeared[tid] += 1
                if self._disappeared[tid] > self.max_disappeared:
                    self._remove_track(tid)
            return list(self._tracks.values())

        new_centroids = [self._centroid(d["bbox"]) for d in detections]

        if not self._tracks:
            # No existing tracks - create new ones
            for i, det in enumerate(detections):
                self._add_track(det, new_centroids[i], zones, now)
        else:
            existing_ids = list(self._tracks.keys())
            existing_centroids = [self._tracks[tid].centroid for tid in existing_ids]

            # Build distance matrix
            matched_det = set()
            matched_track = set()

            # Greedy matching: nearest centroid
            pairs = []
            for di, nc in enumerate(new_centroids):
                best_dist = float("inf")
                best_ti = None
                for ti, ec in enumerate(existing_centroids):
                    d = self._distance(nc, ec)
                    if d < best_dist:
                        best_dist = d
                        best_ti = ti
                if best_dist < self.max_distance and best_ti is not None:
                    pairs.append((di, best_ti, best_dist))

            # Sort by distance, assign greedily
            pairs.sort(key=lambda x: x[2])
            for di, ti, _ in pairs:
                if di in matched_det or ti in matched_track:
                    continue
                matched_det.add(di)
                matched_track.add(ti)

                tid = existing_ids[ti]
                det = detections[di]
                person = self._tracks[tid]

                old_zone_id = person.zone_id

                # Update track
                person.bbox = det["bbox"]
                person.centroid = new_centroids[di]
                person.centroid_history.append(new_centroids[di])
                person.last_seen = now
                person.dwell_seconds = now - person.first_seen
                person.frames_seen += 1
                person.movement_score = calculate_movement_score(
                    list(person.centroid_history), frame_w, frame_h
                )

                # Zone update
                zone = get_zone_for_point(new_centroids[di], zones)
                new_zone_id = zone["id"] if zone else None
                new_zone_name = zone["name"] if zone else None

                if new_zone_id != old_zone_id:
                    person.zone_entry = new_zone_id is not None
                    person.zone_exit = old_zone_id is not None

                person.zone_id = new_zone_id
                person.zone_name = new_zone_name
                self._disappeared[tid] = 0

            # Unmatched detections → new tracks
            for di, det in enumerate(detections):
                if di not in matched_det:
                    self._add_track(det, new_centroids[di], zones, now)

            # Unmatched tracks → increment disappeared
            for ti, tid in enumerate(existing_ids):
                if ti not in matched_track:
                    self._disappeared[tid] = self._disappeared.get(tid, 0) + 1
                    if self._disappeared[tid] > self.max_disappeared:
                        self._remove_track(tid)

        return list(self._tracks.values())

    def _add_track(self, det: Dict, centroid: Tuple, zones: List, now: float):
        from zone_utils import get_zone_for_point
        zone = get_zone_for_point(centroid, zones)
        tid = self._make_id()
        history = deque(maxlen=30)
        history.append(centroid)
        person = TrackedPerson(
            tracking_id=tid,
            bbox=det["bbox"],
            centroid=centroid,
            first_seen=now,
            last_seen=now,
            zone_id=zone["id"] if zone else None,
            zone_name=zone["name"] if zone else None,
            dwell_seconds=0.0,
            movement_score=0.0,
            apparent_expression="face_not_visible",
            frames_seen=1,
            centroid_history=history,
            is_new=True,
            zone_entry=zone is not None,
        )
        self._tracks[tid] = person
        self._disappeared[tid] = 0

    def _remove_track(self, tid: str):
        self._tracks.pop(tid, None)
        self._disappeared.pop(tid, None)

    def get_active_count(self) -> int:
        return len(self._tracks)
