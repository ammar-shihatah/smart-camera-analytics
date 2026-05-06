"""
Pydantic Schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, EmailStr


# ─────────────────────────────────────────────
# BRANCH
# ─────────────────────────────────────────────
class BranchCreate(BaseModel):
    name: str
    location: Optional[str] = None

class BranchOut(BaseModel):
    id: int
    name: str
    location: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# CAMERA
# ─────────────────────────────────────────────
class CameraCreate(BaseModel):
    branch_id: int
    name: str
    stream_url: Optional[str] = None
    status: Optional[str] = "offline"

class CameraUpdate(BaseModel):
    status: Optional[str] = None
    name: Optional[str] = None
    stream_url: Optional[str] = None

class CameraOut(BaseModel):
    id: int
    branch_id: Optional[int]
    name: str
    stream_url: Optional[str]
    status: str
    created_at: datetime
    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# ZONE
# ─────────────────────────────────────────────
class ZoneCreate(BaseModel):
    camera_id: int
    name: str
    type: str
    polygon_json: Any   # list of [x,y] coordinate pairs

class ZoneOut(BaseModel):
    id: int
    camera_id: int
    name: str
    type: str
    polygon_json: Any
    created_at: datetime
    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# TRACKING SESSION
# ─────────────────────────────────────────────
class TrackingSessionOut(BaseModel):
    id: int
    camera_id: int
    tracking_id: str
    first_seen: datetime
    last_seen: datetime
    total_dwell_seconds: float
    movement_score: float
    current_zone_id: Optional[int]
    is_active: bool
    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# DETECTION (from CV Worker)
# ─────────────────────────────────────────────
class DetectionIn(BaseModel):
    camera_id: int
    tracking_id: str
    bbox_json: Optional[Any] = None
    centroid_x: Optional[float] = None
    centroid_y: Optional[float] = None
    confidence: Optional[float] = None
    zone_id: Optional[int] = None
    apparent_expression: Optional[str] = "face_not_visible"

class DetectionOut(BaseModel):
    id: int
    camera_id: int
    tracking_id: str
    detected_at: datetime
    centroid_x: Optional[float]
    centroid_y: Optional[float]
    confidence: Optional[float]
    zone_id: Optional[int]
    apparent_expression: str
    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# ZONE EVENT
# ─────────────────────────────────────────────
class ZoneEventIn(BaseModel):
    camera_id: int
    tracking_id: str
    zone_id: int
    dwell_seconds: Optional[float] = 0.0

class ZoneEventOut(BaseModel):
    id: int
    camera_id: int
    tracking_id: str
    zone_id: int
    entered_at: datetime
    exited_at: Optional[datetime]
    dwell_seconds: float
    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# CV WORKER METADATA BATCH (main ingestion endpoint)
# ─────────────────────────────────────────────
class TrackingPersonData(BaseModel):
    tracking_id: str
    bbox: Optional[List[float]] = None      # [x1,y1,x2,y2]
    centroid_x: Optional[float] = None
    centroid_y: Optional[float] = None
    confidence: Optional[float] = None
    zone_id: Optional[int] = None
    zone_name: Optional[str] = None
    dwell_seconds: Optional[float] = 0.0
    movement_score: Optional[float] = 0.0
    apparent_expression: Optional[str] = "face_not_visible"
    is_new: Optional[bool] = False
    zone_entry: Optional[bool] = False
    zone_exit: Optional[bool] = False

class CVMetadataBatch(BaseModel):
    camera_id: int
    timestamp: datetime
    frame_people_count: int
    tracked_persons: List[TrackingPersonData]
    zone_counts: Optional[dict] = {}


# ─────────────────────────────────────────────
# ALERT
# ─────────────────────────────────────────────
class AlertOut(BaseModel):
    id: int
    camera_id: int
    zone_id: Optional[int]
    type: str
    severity: str
    message: Optional[str]
    created_at: datetime
    resolved_at: Optional[datetime]
    model_config = {"from_attributes": True}

class AlertCreate(BaseModel):
    camera_id: int
    zone_id: Optional[int] = None
    type: str
    severity: str = "info"
    message: Optional[str] = None


# ─────────────────────────────────────────────
# DASHBOARD ANALYTICS
# ─────────────────────────────────────────────
class ZoneAnalytics(BaseModel):
    zone_id: int
    zone_name: str
    zone_type: str
    current_count: int
    avg_dwell_seconds: float
    total_visits_today: int

class DashboardOverview(BaseModel):
    total_people_now: int
    total_visits_today: int
    avg_dwell_seconds: float
    active_alerts: int
    cameras_online: int
    cameras_total: int
    zone_analytics: List[ZoneAnalytics]

class CameraAnalytics(BaseModel):
    camera_id: int
    camera_name: str
    total_detections: int
    unique_persons: int
    avg_dwell_seconds: float
    peak_count: int


# ─────────────────────────────────────────────
# USER & AUDIT
# ─────────────────────────────────────────────
class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    created_at: datetime
    model_config = {"from_attributes": True}

class AuditLogOut(BaseModel):
    id: int
    user_id: Optional[int]
    action: str
    details_json: Optional[Any]
    created_at: datetime
    model_config = {"from_attributes": True}
