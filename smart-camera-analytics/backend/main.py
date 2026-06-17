"""
Smart Camera Behavior Analytics System - FastAPI Backend
Privacy-first design: no face images, no identity, temp tracking IDs only.
"""
import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

import os
import crud
import schemas
from auth import (
    get_current_user, require_permission,
    hash_password, verify_password, create_access_token,
)
from crypto import decrypt_secret
from database import get_db, engine
from models import Base, User
from websocket_manager import manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Max simultaneous browser MJPEG streams the proxy will serve
MAX_CONCURRENT_STREAMS = int(os.getenv("MAX_CONCURRENT_STREAMS", "12"))
_active_streams = 0
_streams_lock = asyncio.Lock()

# Shared secret the CV worker must present to push detection metadata
INGEST_API_KEY = os.getenv("INGEST_API_KEY", "")

# ── OpenCV / streaming (optional — backend works without it) ──────────────────
OPENCV_INSTALLED = False
STREAM_AVAILABLE = False
OPENCV_VERSION: Optional[str] = None
_stream_import_error: str = ""

try:
    import cv2
    OPENCV_INSTALLED = True
    OPENCV_VERSION = cv2.__version__
    logger.info(f"✅ OpenCV {OPENCV_VERSION} loaded successfully")
    from stream_manager import mjpeg_generator, test_rtsp_sync, build_rtsp_url
    STREAM_AVAILABLE = True
except ImportError as _e:
    _stream_import_error = str(_e)
    logger.warning(f"⚠️  OpenCV import failed — streaming disabled. Reason: {_e}")
except Exception as _e:
    _stream_import_error = str(_e)
    logger.error(f"❌ Unexpected error loading OpenCV: {_e}", exc_info=True)


def _stream_unavailable_detail() -> str:
    if not OPENCV_INSTALLED:
        return "Streaming not available: OpenCV is not installed in the backend container"
    return f"Streaming not available: {_stream_import_error or 'stream manager failed to load'}"

# In-memory store for password reset tokens (use Redis in production)
_reset_tokens: dict[str, int] = {}  # token → user_id


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safe migrations — add new columns if they don't exist
        migrations = [
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS cam_username VARCHAR(255)",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS cam_password VARCHAR(255)",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS last_error TEXT",
            "ALTER TABLE cameras ADD COLUMN IF NOT EXISTS last_connected_at TIMESTAMPTZ",
            "ALTER TABLE users   ADD COLUMN IF NOT EXISTS is_active      BOOLEAN DEFAULT TRUE",
            "ALTER TABLE users   ADD COLUMN IF NOT EXISTS must_change_pw BOOLEAN DEFAULT FALSE",
            "ALTER TABLE users   ADD COLUMN IF NOT EXISTS last_login     TIMESTAMPTZ",
            "ALTER TABLE users   ADD COLUMN IF NOT EXISTS password_hash  TEXT",
        ]
        for sql in migrations:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass
    logger.info("✅ Database tables ready")

    # Seed default super_admin if no users exist
    async with AsyncSession(engine) as db:
        result = await db.execute(select(User).limit(1))
        if not result.scalar_one_or_none():
            admin = User(
                name="Super Admin",
                email="admin@sca.local",
                password_hash=hash_password("Admin@1234"),
                role="super_admin",
                is_active=True,
                must_change_pw=True,
            )
            db.add(admin)
            await db.commit()
            logger.info("✅ Default admin created — email: admin@sca.local  password: Admin@1234")

    yield
    logger.info("🛑 Shutting down")


app = FastAPI(
    title="Smart Camera Analytics API",
    description="Privacy-first camera behavior analytics system",
    version="2.0.0",
    lifespan=lifespan,
)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# HEALTH (public)
# ─────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/system/health", tags=["System"])
async def system_health():
    """
    Detailed system health — shows OpenCV status, FFmpeg, streaming availability.
    Useful for diagnosing stream issues without looking at container logs.
    """
    import shutil

    ffmpeg_available = shutil.which("ffmpeg") is not None

    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "opencv_installed": OPENCV_INSTALLED,
        "opencv_version": OPENCV_VERSION or "not installed",
        "ffmpeg_available": ffmpeg_available,
        "streaming_enabled": STREAM_AVAILABLE,
        "stream_error": _stream_import_error if not STREAM_AVAILABLE else None,
    }


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────
@app.post("/api/auth/login", response_model=schemas.TokenResponse, tags=["Auth"])
async def login(data: schemas.LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not user.password_hash or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    user.last_login = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id, user.role)
    await crud.create_audit_log(db, "user.login", details={"user_id": user.id})

    return schemas.TokenResponse(
        access_token=token,
        user=schemas.UserOut.model_validate(user),
    )


@app.get("/api/auth/me", response_model=schemas.UserOut, tags=["Auth"])
async def me(current_user: User = Depends(get_current_user)):
    return schemas.UserOut.model_validate(current_user)


@app.post("/api/auth/change-password", tags=["Auth"])
async def change_password(
    data: schemas.ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    current_user.password_hash = hash_password(data.new_password)
    current_user.must_change_pw = False
    await db.commit()
    await crud.create_audit_log(db, "user.password_changed", details={"user_id": current_user.id})
    return {"message": "Password changed successfully"}


@app.post("/api/auth/forgot-password", tags=["Auth"])
async def forgot_password(data: schemas.ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    # Always return success to prevent email enumeration
    if user and user.is_active:
        token = secrets.token_urlsafe(32)
        _reset_tokens[token] = user.id
        await crud.create_audit_log(db, "user.forgot_password", details={"user_id": user.id})
        # In production: send email with token
        logger.info(f"Password reset token for {user.email}: {token}")
        return {"message": "If the email exists, a reset link has been sent", "dev_token": token}
    return {"message": "If the email exists, a reset link has been sent"}


@app.post("/api/auth/reset-password", tags=["Auth"])
async def reset_password(data: schemas.ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    user_id = _reset_tokens.pop(data.token, None)
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = hash_password(data.new_password)
    user.must_change_pw = False
    await db.commit()
    await crud.create_audit_log(db, "user.password_reset", details={"user_id": user.id})
    return {"message": "Password reset successfully"}


# ─────────────────────────────────────────────
# USERS (admin only)
# ─────────────────────────────────────────────
@app.get("/api/users", response_model=List[schemas.UserOut], tags=["Users"])
async def list_users(
    _=Depends(require_permission("users.view")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@app.post("/api/users", response_model=schemas.UserOut, tags=["Users"])
async def create_user(
    data: schemas.UserCreate,
    current_user: User = Depends(require_permission("users.create")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
        must_change_pw=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    await crud.create_audit_log(db, "user.created", details={"user_id": user.id, "created_by": current_user.id})
    return user


@app.patch("/api/users/{user_id}", response_model=schemas.UserOut, tags=["Users"])
async def update_user(
    user_id: int,
    data: schemas.UserUpdate,
    current_user: User = Depends(require_permission("users.update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if data.name is not None:
        user.name = data.name
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    await db.commit()
    await db.refresh(user)
    await crud.create_audit_log(db, "user.updated", details={"user_id": user_id, "by": current_user.id})
    return user


@app.delete("/api/users/{user_id}", tags=["Users"])
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_permission("users.delete")),
    db: AsyncSession = Depends(get_db),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
    await crud.create_audit_log(db, "user.deleted", details={"user_id": user_id, "by": current_user.id})
    return {"message": "User deleted"}


# ─────────────────────────────────────────────
# BRANCHES
# ─────────────────────────────────────────────
@app.post("/api/branches", response_model=schemas.BranchOut, tags=["Branches"])
async def create_branch(
    data: schemas.BranchCreate,
    current_user: User = Depends(require_permission("branches.create")),
    db: AsyncSession = Depends(get_db),
):
    branch = await crud.create_branch(db, data)
    await crud.create_audit_log(db, "branch.created", details={"branch_id": branch.id, "by": current_user.id})
    return branch


@app.get("/api/branches", response_model=List[schemas.BranchOut], tags=["Branches"])
async def list_branches(
    _=Depends(require_permission("branches.view")),
    db: AsyncSession = Depends(get_db),
):
    return await crud.list_branches(db)


# ─────────────────────────────────────────────
# CAMERAS
# ─────────────────────────────────────────────
@app.post("/api/cameras", response_model=schemas.CameraOut, tags=["Cameras"])
async def create_camera(
    data: schemas.CameraCreate,
    current_user: User = Depends(require_permission("cameras.manage")),
    db: AsyncSession = Depends(get_db),
):
    cam = await crud.create_camera(db, data)
    await crud.create_audit_log(db, "camera.created", details={"camera_id": cam.id, "by": current_user.id})
    return cam


@app.get("/api/cameras", response_model=List[schemas.CameraOut], tags=["Cameras"])
async def list_cameras(
    branch_id: Optional[int] = Query(None),
    _=Depends(require_permission("cameras.view")),
    db: AsyncSession = Depends(get_db),
):
    return await crud.list_cameras(db, branch_id=branch_id)


@app.get("/api/cameras/{camera_id}", response_model=schemas.CameraOut, tags=["Cameras"])
async def get_camera(
    camera_id: int,
    _=Depends(require_permission("cameras.view")),
    db: AsyncSession = Depends(get_db),
):
    cam = await crud.get_camera(db, camera_id)
    if not cam:
        raise HTTPException(404, detail="Camera not found")
    return cam


@app.patch("/api/cameras/{camera_id}", response_model=schemas.CameraOut, tags=["Cameras"])
async def update_camera(
    camera_id: int,
    data: schemas.CameraUpdate,
    current_user: User = Depends(require_permission("cameras.manage")),
    db: AsyncSession = Depends(get_db),
):
    cam = await crud.update_camera_status(db, camera_id, data)
    if not cam:
        raise HTTPException(404, detail="Camera not found")
    await crud.create_audit_log(db, "camera.updated", user_id=current_user.id, details={"camera_id": camera_id})
    return cam


@app.delete("/api/cameras/{camera_id}", tags=["Cameras"])
async def delete_camera(
    camera_id: int,
    current_user: User = Depends(require_permission("cameras.manage")),
    db: AsyncSession = Depends(get_db),
):
    ok = await crud.delete_camera(db, camera_id)
    if not ok:
        raise HTTPException(404, detail="Camera not found")
    await crud.create_audit_log(db, "camera.deleted", user_id=current_user.id, details={"camera_id": camera_id})
    return {"message": "Camera deleted"}


# ─────────────────────────────────────────────
# CAMERA STREAM  (RTSP → MJPEG proxy)
# ─────────────────────────────────────────────
@app.get("/api/cameras/{camera_id}/stream", tags=["Stream"])
async def camera_stream(  # noqa: C901
    camera_id: int,
    token: Optional[str] = Query(None),
    fps: int = Query(15, ge=1, le=30),
    profile: str = Query("stored"),
    quality: int = Query(5, ge=2, le=31),
    transport: str = Query("tcp"),
    db: AsyncSession = Depends(get_db),
):
    """
    MJPEG stream proxy. Use as <img src="/api/cameras/{id}/stream?token=xxx">.
    Converts RTSP → MJPEG so browsers can display it without plugins.
    """
    if not STREAM_AVAILABLE:
        raise HTTPException(503, _stream_unavailable_detail())

    user = await _ws_auth(token, db)
    if not user:
        raise HTTPException(401, "Authentication required")

    cam = await crud.get_camera(db, camera_id)
    if not cam:
        raise HTTPException(404, "Camera not found")

    # Enforce a cap on concurrent streams to protect the server
    global _active_streams
    async with _streams_lock:
        if _active_streams >= MAX_CONCURRENT_STREAMS:
            raise HTTPException(
                503,
                f"Server is at capacity ({MAX_CONCURRENT_STREAMS} concurrent streams). "
                "Close another live view and try again.",
            )
        _active_streams += 1
    logger.info(f"Stream START cam={camera_id} active={_active_streams}/{MAX_CONCURRENT_STREAMS}")

    password = decrypt_secret(cam.cam_password)

    async def _counted_stream():
        global _active_streams
        try:
            async for chunk in mjpeg_generator(
                stream_url=cam.stream_url or "",
                username=cam.cam_username,
                password=password,
                fps=fps,
                profile=profile,
                jpeg_quality=quality,
                transport=transport,
            ):
                yield chunk
        finally:
            async with _streams_lock:
                _active_streams = max(0, _active_streams - 1)
            logger.info(f"Stream END   cam={camera_id} active={_active_streams}/{MAX_CONCURRENT_STREAMS}")

    return StreamingResponse(
        _counted_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store"},
    )


@app.get("/api/cameras/{camera_id}/test-connection", response_model=schemas.TestConnectionResult, tags=["Stream"])
async def test_camera_connection(  # noqa
    camera_id: int,
    current_user: User = Depends(require_permission("cameras.manage")),
    db: AsyncSession = Depends(get_db),
):
    """
    Test RTSP connectivity from the backend server.
    Returns detailed diagnostic info including suggested fixes.
    """
    if not STREAM_AVAILABLE:
        raise HTTPException(503, _stream_unavailable_detail())

    cam = await crud.get_camera(db, camera_id)
    if not cam:
        raise HTTPException(404, "Camera not found")

    if not cam.stream_url:
        return schemas.TestConnectionResult(
            success=False,
            connection_status="no_url",
            rtsp_reachable=False,
            backend_can_open_stream=False,
            error_message="No stream URL configured",
            suggested_fix="Add an RTSP URL in camera settings",
        )

    url = build_rtsp_url(cam.stream_url, cam.cam_username, decrypt_secret(cam.cam_password))
    loop = asyncio.get_event_loop()

    try:
        result = await asyncio.wait_for(
            loop.run_in_executor(None, test_rtsp_sync, url),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        result = {
            "success": False,
            "connection_status": "timeout",
            "rtsp_reachable": False,
            "backend_can_open_stream": False,
            "error_message": "Connection timed out after 15 seconds",
            "suggested_fix": "Check network route from server to camera IP. Ensure port 554 is open.",
        }

    # Persist status + last_error back to camera
    cam.status = "online" if result["success"] else "error"
    cam.last_error = result.get("error_message") if not result["success"] else None
    if result["success"]:
        cam.last_connected_at = datetime.now(timezone.utc)
    await db.commit()

    await crud.create_audit_log(
        db, "camera.test_connection",
        user_id=current_user.id,
        details={"camera_id": camera_id, "result": result["connection_status"]},
    )

    return schemas.TestConnectionResult(**result)


# ─────────────────────────────────────────────
# ZONES
# ─────────────────────────────────────────────
@app.post("/api/zones", response_model=schemas.ZoneOut, tags=["Zones"])
async def create_zone(
    data: schemas.ZoneCreate,
    current_user: User = Depends(require_permission("zones.manage")),
    db: AsyncSession = Depends(get_db),
):
    zone = await crud.create_zone(db, data)
    await crud.create_audit_log(db, "zone.created", details={"zone_id": zone.id, "by": current_user.id})
    return zone


@app.get("/api/cameras/{camera_id}/zones", response_model=List[schemas.ZoneOut], tags=["Zones"])
async def list_zones(
    camera_id: int,
    _=Depends(require_permission("zones.view")),
    db: AsyncSession = Depends(get_db),
):
    return await crud.list_zones(db, camera_id)


# ─────────────────────────────────────────────
# CV WORKER INGESTION (protected by a shared API key)
# ─────────────────────────────────────────────
def verify_ingest_key(x_api_key: Optional[str] = Header(None)):
    """Require the CV worker to present X-API-Key matching INGEST_API_KEY."""
    if not INGEST_API_KEY:
        # No key configured → ingestion disabled to avoid an open endpoint
        raise HTTPException(503, "Ingestion disabled: INGEST_API_KEY not configured")
    if x_api_key != INGEST_API_KEY:
        raise HTTPException(401, "Invalid or missing API key")


@app.get("/internal/cameras/analysis-config", tags=["CV Worker"])
async def analysis_camera_config(
    _=Depends(verify_ingest_key),
    db: AsyncSession = Depends(get_db),
):
    """
    Internal camera list for the CV worker.

    This intentionally returns decrypted camera credentials, so it is protected
    by INGEST_API_KEY and must never be exposed to browsers.
    """
    cameras = await crud.list_cameras(db)
    return {
        "cameras": [
            {
                "id": cam.id,
                "name": cam.name,
                "stream_url": cam.stream_url,
                "cam_username": cam.cam_username,
                "cam_password": decrypt_secret(cam.cam_password),
                "status": cam.status,
            }
            for cam in cameras
            if cam.stream_url and cam.status != "maintenance"
        ]
    }


@app.get("/internal/cameras/{camera_id}/zones", tags=["CV Worker"])
async def internal_camera_zones(
    camera_id: int,
    _=Depends(verify_ingest_key),
    db: AsyncSession = Depends(get_db),
):
    """Internal zone definitions for the CV worker without requiring JWT."""
    return await crud.list_zones(db, camera_id)


@app.post("/api/ingest/metadata", tags=["CV Worker"])
async def ingest_metadata(
    batch: schemas.CVMetadataBatch,
    _=Depends(verify_ingest_key),
    db: AsyncSession = Depends(get_db),
):
    for person in batch.tracked_persons:
        await crud.upsert_tracking_session(
            db,
            camera_id=batch.camera_id,
            tracking_id=person.tracking_id,
            dwell_seconds=person.dwell_seconds or 0.0,
            movement_score=person.movement_score or 0.0,
            zone_id=person.zone_id,
        )
        await crud.create_detection(db, schemas.DetectionIn(
            camera_id=batch.camera_id,
            tracking_id=person.tracking_id,
            bbox_json=person.bbox,
            centroid_x=person.centroid_x,
            centroid_y=person.centroid_y,
            confidence=person.confidence,
            zone_id=person.zone_id,
            apparent_expression=person.apparent_expression,
        ))
        if person.zone_entry and person.zone_id:
            await crud.create_zone_event(db, schemas.ZoneEventIn(
                camera_id=batch.camera_id,
                tracking_id=person.tracking_id,
                zone_id=person.zone_id,
                dwell_seconds=person.dwell_seconds or 0.0,
            ))
        if person.zone_id and person.dwell_seconds and person.dwell_seconds > 600:
            await crud.create_alert(db, schemas.AlertCreate(
                camera_id=batch.camera_id,
                zone_id=person.zone_id,
                type="long_wait",
                severity="warning",
                message="Person waiting over 10 minutes in zone",
            ))

    for zone_name, count in (batch.zone_counts or {}).items():
        if count >= 10:
            await crud.create_alert(db, schemas.AlertCreate(
                camera_id=batch.camera_id,
                type="crowd_alert",
                severity="critical" if count >= 15 else "warning",
                message=f"High crowd density in {zone_name}: {count} people",
            ))

    ws_payload = {
        "type": "live_update",
        "camera_id": batch.camera_id,
        "timestamp": batch.timestamp.isoformat(),
        "people_count": batch.frame_people_count,
        "zone_counts": batch.zone_counts,
        "tracked_persons": [p.model_dump() for p in batch.tracked_persons],
    }
    await manager.broadcast_camera(batch.camera_id, ws_payload)
    await manager.broadcast_global(ws_payload)
    return {"status": "ok", "received": len(batch.tracked_persons)}


# ─────────────────────────────────────────────
# DASHBOARD ANALYTICS
# ─────────────────────────────────────────────
@app.get("/api/dashboard/overview", response_model=schemas.DashboardOverview, tags=["Dashboard"])
async def dashboard_overview(
    _=Depends(require_permission("analytics.view")),
    db: AsyncSession = Depends(get_db),
):
    people_now    = await crud.get_current_people_count(db)
    visits_today  = await crud.get_today_visits(db)
    avg_dwell     = await crud.get_avg_dwell(db)
    active_alerts = await crud.get_active_alerts_count(db)
    zone_analytics= await crud.get_zone_analytics(db)
    cams          = await crud.list_cameras(db)
    online        = sum(1 for c in cams if c.status == "online")

    return schemas.DashboardOverview(
        total_people_now=people_now,
        total_visits_today=visits_today,
        avg_dwell_seconds=avg_dwell,
        active_alerts=active_alerts,
        cameras_online=online,
        cameras_total=len(cams),
        zone_analytics=[schemas.ZoneAnalytics(**z) for z in zone_analytics],
    )


@app.get("/api/dashboard/people-count", tags=["Dashboard"])
async def current_people_count(
    camera_id: Optional[int] = Query(None),
    _=Depends(require_permission("analytics.view")),
    db: AsyncSession = Depends(get_db),
):
    count = await crud.get_current_people_count(db, camera_id)
    return {"count": count, "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/dashboard/zone-analytics", tags=["Dashboard"])
async def zone_analytics(
    camera_id: Optional[int] = Query(None),
    _=Depends(require_permission("analytics.view")),
    db: AsyncSession = Depends(get_db),
):
    return await crud.get_zone_analytics(db, camera_id)


@app.get("/api/dashboard/alerts", response_model=List[schemas.AlertOut], tags=["Dashboard"])
async def get_alerts(
    camera_id: Optional[int] = Query(None),
    unresolved_only: bool = Query(False),
    limit: int = Query(50),
    _=Depends(require_permission("alerts.view")),
    db: AsyncSession = Depends(get_db),
):
    return await crud.list_alerts(db, camera_id=camera_id, unresolved_only=unresolved_only, limit=limit)


@app.post("/api/alerts/{alert_id}/resolve", response_model=schemas.AlertOut, tags=["Dashboard"])
async def resolve_alert(
    alert_id: int,
    current_user: User = Depends(require_permission("alerts.resolve")),
    db: AsyncSession = Depends(get_db),
):
    alert = await crud.resolve_alert(db, alert_id)
    if not alert:
        raise HTTPException(404, detail="Alert not found")
    await crud.create_audit_log(db, "alert.resolved", details={"alert_id": alert_id, "by": current_user.id})
    return alert


@app.get("/api/cameras/{camera_id}/analytics", response_model=schemas.CameraAnalytics, tags=["Dashboard"])
async def camera_analytics(
    camera_id: int,
    date: Optional[str] = Query(None),
    _=Depends(require_permission("analytics.view")),
    db: AsyncSession = Depends(get_db),
):
    data = await crud.get_camera_analytics(db, camera_id, date)
    if not data:
        raise HTTPException(404, detail="Camera not found")
    return schemas.CameraAnalytics(**data)


# ─────────────────────────────────────────────
# AUDIT LOGS
# ─────────────────────────────────────────────
@app.get("/api/audit-logs", response_model=List[schemas.AuditLogOut], tags=["Audit"])
async def get_audit_logs(
    limit: int = Query(100, le=500),
    _=Depends(require_permission("audit.view")),
    db: AsyncSession = Depends(get_db),
):
    return await crud.list_audit_logs(db, limit=limit)


# ─────────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────────
@app.post("/api/admin/purge-old-data", tags=["Admin"])
async def purge_old_data(
    _=Depends(require_permission("*")),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import text
    await db.execute(text("SELECT delete_old_detections()"))
    await db.commit()
    await crud.create_audit_log(db, "data.purge_executed", details={"trigger": "manual"})
    return {"status": "purged"}


# ─────────────────────────────────────────────
# WEBSOCKET (auth via token query param)
# ─────────────────────────────────────────────
async def _ws_auth(token: Optional[str], db: AsyncSession) -> Optional[User]:
    """Validate WS token — returns user or None."""
    if not token:
        return None
    try:
        from jose import jwt as _jwt
        from auth import SECRET_KEY, ALGORITHM
        payload = _jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
    except Exception:
        return None


@app.websocket("/ws/dashboard")
async def ws_dashboard(ws: WebSocket, token: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    user = await _ws_auth(token, db)
    if not user:
        await ws.close(code=4001)
        return
    await manager.connect_global(ws)
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        manager.disconnect_global(ws)


@app.websocket("/ws/camera/{camera_id}")
async def ws_camera(ws: WebSocket, camera_id: int, token: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    user = await _ws_auth(token, db)
    if not user:
        await ws.close(code=4001)
        return
    await manager.connect_camera(ws, camera_id)
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        manager.disconnect_camera(ws, camera_id)
