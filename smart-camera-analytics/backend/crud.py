"""
CRUD operations - Database interaction layer.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, update, delete, desc
from models import (
    Branch, Camera, Zone, TrackingSession,
    Detection, ZoneEvent, Alert, AuditLog, User, Interaction
)
import schemas


def utcnow():
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────
# BRANCHES
# ─────────────────────────────────────────────
async def create_branch(db: AsyncSession, data: schemas.BranchCreate) -> Branch:
    obj = Branch(name=data.name, location=data.location)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

async def list_branches(db: AsyncSession) -> List[Branch]:
    result = await db.execute(select(Branch).order_by(Branch.id))
    return result.scalars().all()


# ─────────────────────────────────────────────
# CAMERAS
# ─────────────────────────────────────────────
async def create_camera(db: AsyncSession, data: schemas.CameraCreate) -> Camera:
    obj = Camera(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

async def list_cameras(db: AsyncSession, branch_id: Optional[int] = None) -> List[Camera]:
    q = select(Camera)
    if branch_id:
        q = q.where(Camera.branch_id == branch_id)
    result = await db.execute(q.order_by(Camera.id))
    return result.scalars().all()

async def get_camera(db: AsyncSession, camera_id: int) -> Optional[Camera]:
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    return result.scalar_one_or_none()

async def update_camera_status(db: AsyncSession, camera_id: int, data: schemas.CameraUpdate) -> Optional[Camera]:
    cam = await get_camera(db, camera_id)
    if not cam:
        return None
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(cam, k, v)
    await db.commit()
    await db.refresh(cam)
    return cam

async def delete_camera(db: AsyncSession, camera_id: int) -> bool:
    """
    Delete a camera and all its dependent records.
    Children are removed explicitly in FK-safe order so the operation
    succeeds regardless of whether DB-level ON DELETE CASCADE is present.
    """
    cam = await get_camera(db, camera_id)
    if not cam:
        return False

    # Delete rows that reference zones first, then the zones, then the camera
    await db.execute(delete(ZoneEvent).where(ZoneEvent.camera_id == camera_id))
    await db.execute(delete(Interaction).where(Interaction.camera_id == camera_id))
    await db.execute(delete(Detection).where(Detection.camera_id == camera_id))
    await db.execute(delete(TrackingSession).where(TrackingSession.camera_id == camera_id))
    await db.execute(delete(Alert).where(Alert.camera_id == camera_id))
    await db.execute(delete(Zone).where(Zone.camera_id == camera_id))
    await db.execute(delete(Camera).where(Camera.id == camera_id))
    await db.commit()
    return True


# ─────────────────────────────────────────────
# ZONES
# ─────────────────────────────────────────────
async def create_zone(db: AsyncSession, data: schemas.ZoneCreate) -> Zone:
    obj = Zone(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

async def list_zones(db: AsyncSession, camera_id: int) -> List[Zone]:
    result = await db.execute(select(Zone).where(Zone.camera_id == camera_id).order_by(Zone.id))
    return result.scalars().all()

async def get_zone(db: AsyncSession, zone_id: int) -> Optional[Zone]:
    result = await db.execute(select(Zone).where(Zone.id == zone_id))
    return result.scalar_one_or_none()


# ─────────────────────────────────────────────
# TRACKING SESSIONS
# ─────────────────────────────────────────────
async def upsert_tracking_session(
    db: AsyncSession,
    camera_id: int,
    tracking_id: str,
    dwell_seconds: float,
    movement_score: float,
    zone_id: Optional[int]
) -> TrackingSession:
    result = await db.execute(
        select(TrackingSession).where(
            and_(
                TrackingSession.camera_id == camera_id,
                TrackingSession.tracking_id == tracking_id,
                TrackingSession.is_active == True
            )
        )
    )
    session = result.scalar_one_or_none()
    if session:
        session.last_seen = utcnow()
        session.total_dwell_seconds = dwell_seconds
        session.movement_score = movement_score
        session.current_zone_id = zone_id
    else:
        session = TrackingSession(
            camera_id=camera_id,
            tracking_id=tracking_id,
            total_dwell_seconds=dwell_seconds,
            movement_score=movement_score,
            current_zone_id=zone_id,
            is_active=True
        )
        db.add(session)
    await db.commit()
    await db.refresh(session)
    return session

async def deactivate_tracking_session(db: AsyncSession, camera_id: int, tracking_id: str):
    await db.execute(
        update(TrackingSession)
        .where(and_(
            TrackingSession.camera_id == camera_id,
            TrackingSession.tracking_id == tracking_id
        ))
        .values(is_active=False)
    )
    await db.commit()


# ─────────────────────────────────────────────
# DETECTIONS
# ─────────────────────────────────────────────
async def create_detection(db: AsyncSession, data: schemas.DetectionIn) -> Detection:
    obj = Detection(
        camera_id=data.camera_id,
        tracking_id=data.tracking_id,
        bbox_json=data.bbox_json,
        centroid_x=data.centroid_x,
        centroid_y=data.centroid_y,
        confidence=data.confidence,
        zone_id=data.zone_id,
        apparent_expression=data.apparent_expression or "face_not_visible"
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ─────────────────────────────────────────────
# ZONE EVENTS
# ─────────────────────────────────────────────
async def create_zone_event(db: AsyncSession, data: schemas.ZoneEventIn) -> ZoneEvent:
    obj = ZoneEvent(
        camera_id=data.camera_id,
        tracking_id=data.tracking_id,
        zone_id=data.zone_id,
        dwell_seconds=data.dwell_seconds or 0.0
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


# ─────────────────────────────────────────────
# ALERTS
# ─────────────────────────────────────────────
async def create_alert(db: AsyncSession, data: schemas.AlertCreate) -> Alert:
    obj = Alert(**data.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

async def list_alerts(
    db: AsyncSession,
    camera_id: Optional[int] = None,
    unresolved_only: bool = False,
    limit: int = 50
) -> List[Alert]:
    q = select(Alert)
    if camera_id:
        q = q.where(Alert.camera_id == camera_id)
    if unresolved_only:
        q = q.where(Alert.resolved_at == None)
    q = q.order_by(desc(Alert.created_at)).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()

async def resolve_alert(db: AsyncSession, alert_id: int) -> Optional[Alert]:
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert:
        alert.resolved_at = utcnow()
        await db.commit()
        await db.refresh(alert)
    return alert


# ─────────────────────────────────────────────
# DASHBOARD ANALYTICS
# ─────────────────────────────────────────────
async def get_current_people_count(db: AsyncSession, camera_id: Optional[int] = None) -> int:
    q = select(func.count(TrackingSession.id)).where(TrackingSession.is_active == True)
    if camera_id:
        q = q.where(TrackingSession.camera_id == camera_id)
    result = await db.execute(q)
    return result.scalar() or 0

async def get_today_visits(db: AsyncSession) -> int:
    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(TrackingSession.id))
        .where(TrackingSession.first_seen >= today)
    )
    return result.scalar() or 0

async def get_avg_dwell(db: AsyncSession) -> float:
    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.avg(TrackingSession.total_dwell_seconds))
        .where(TrackingSession.first_seen >= today)
    )
    val = result.scalar()
    return round(val, 1) if val else 0.0

async def get_active_alerts_count(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(Alert.id)).where(Alert.resolved_at == None)
    )
    return result.scalar() or 0

async def get_zone_analytics(db: AsyncSession, camera_id: Optional[int] = None) -> list:
    """Per-zone current counts and dwell time."""
    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Build zones list
    q = select(Zone)
    if camera_id:
        q = q.where(Zone.camera_id == camera_id)
    zones_result = await db.execute(q)
    zones = zones_result.scalars().all()

    analytics = []
    for zone in zones:
        # Current count in this zone
        count_result = await db.execute(
            select(func.count(TrackingSession.id)).where(
                and_(
                    TrackingSession.current_zone_id == zone.id,
                    TrackingSession.is_active == True
                )
            )
        )
        current_count = count_result.scalar() or 0

        # Avg dwell today
        avg_result = await db.execute(
            select(func.avg(ZoneEvent.dwell_seconds)).where(
                and_(
                    ZoneEvent.zone_id == zone.id,
                    ZoneEvent.entered_at >= today
                )
            )
        )
        avg_dwell = avg_result.scalar() or 0.0

        # Total visits today
        visits_result = await db.execute(
            select(func.count(ZoneEvent.id)).where(
                and_(
                    ZoneEvent.zone_id == zone.id,
                    ZoneEvent.entered_at >= today
                )
            )
        )
        total_visits = visits_result.scalar() or 0

        analytics.append({
            "zone_id": zone.id,
            "zone_name": zone.name,
            "zone_type": zone.type,
            "current_count": current_count,
            "avg_dwell_seconds": round(avg_dwell, 1),
            "total_visits_today": total_visits,
        })

    return analytics

async def get_camera_analytics(db: AsyncSession, camera_id: int, date_str: Optional[str] = None) -> dict:
    """Analytics for a specific camera."""
    cam = await get_camera(db, camera_id)
    if not cam:
        return {}

    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    det_count = await db.execute(
        select(func.count(Detection.id)).where(
            and_(Detection.camera_id == camera_id, Detection.detected_at >= today)
        )
    )
    unique_persons = await db.execute(
        select(func.count(func.distinct(TrackingSession.tracking_id))).where(
            and_(TrackingSession.camera_id == camera_id, TrackingSession.first_seen >= today)
        )
    )
    avg_dwell = await db.execute(
        select(func.avg(TrackingSession.total_dwell_seconds)).where(
            and_(TrackingSession.camera_id == camera_id, TrackingSession.first_seen >= today)
        )
    )

    return {
        "camera_id": camera_id,
        "camera_name": cam.name,
        "total_detections": det_count.scalar() or 0,
        "unique_persons": unique_persons.scalar() or 0,
        "avg_dwell_seconds": round(avg_dwell.scalar() or 0, 1),
        "peak_count": 0,  # TODO: implement peak tracking
    }


# ─────────────────────────────────────────────
# AUDIT LOG
# ─────────────────────────────────────────────
async def create_audit_log(
    db: AsyncSession,
    action: str,
    user_id: Optional[int] = None,
    details: Optional[dict] = None
):
    obj = AuditLog(user_id=user_id, action=action, details_json=details)
    db.add(obj)
    await db.commit()

async def list_audit_logs(db: AsyncSession, limit: int = 100) -> List[AuditLog]:
    result = await db.execute(
        select(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit)
    )
    return result.scalars().all()
