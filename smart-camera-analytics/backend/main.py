"""
Smart Camera Behavior Analytics System - FastAPI Backend
Privacy-first design: no face images, no identity, temp tracking IDs only.
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

import crud
import schemas
from database import get_db, engine
from models import Base
from websocket_manager import manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup if not exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database tables ready")
    yield
    logger.info("🛑 Shutting down")


app = FastAPI(
    title="Smart Camera Analytics API",
    description="Privacy-first camera behavior analytics system",
    version="1.0.0",
    lifespan=lifespan,
)

import os
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# HEALTH
# ─────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ─────────────────────────────────────────────
# BRANCHES
# ─────────────────────────────────────────────
@app.post("/api/branches", response_model=schemas.BranchOut, tags=["Branches"])
async def create_branch(data: schemas.BranchCreate, db: AsyncSession = Depends(get_db)):
    branch = await crud.create_branch(db, data)
    await crud.create_audit_log(db, "branch_created", details={"branch_id": branch.id, "name": branch.name})
    return branch

@app.get("/api/branches", response_model=List[schemas.BranchOut], tags=["Branches"])
async def list_branches(db: AsyncSession = Depends(get_db)):
    return await crud.list_branches(db)


# ─────────────────────────────────────────────
# CAMERAS
# ─────────────────────────────────────────────
@app.post("/api/cameras", response_model=schemas.CameraOut, tags=["Cameras"])
async def create_camera(data: schemas.CameraCreate, db: AsyncSession = Depends(get_db)):
    cam = await crud.create_camera(db, data)
    await crud.create_audit_log(db, "camera_created", details={"camera_id": cam.id})
    return cam

@app.get("/api/cameras", response_model=List[schemas.CameraOut], tags=["Cameras"])
async def list_cameras(
    branch_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    return await crud.list_cameras(db, branch_id=branch_id)

@app.get("/api/cameras/{camera_id}", response_model=schemas.CameraOut, tags=["Cameras"])
async def get_camera(camera_id: int, db: AsyncSession = Depends(get_db)):
    cam = await crud.get_camera(db, camera_id)
    if not cam:
        raise HTTPException(404, detail="Camera not found")
    return cam

@app.patch("/api/cameras/{camera_id}", response_model=schemas.CameraOut, tags=["Cameras"])
async def update_camera(camera_id: int, data: schemas.CameraUpdate, db: AsyncSession = Depends(get_db)):
    cam = await crud.update_camera_status(db, camera_id, data)
    if not cam:
        raise HTTPException(404, detail="Camera not found")
    return cam


# ─────────────────────────────────────────────
# ZONES
# ─────────────────────────────────────────────
@app.post("/api/zones", response_model=schemas.ZoneOut, tags=["Zones"])
async def create_zone(data: schemas.ZoneCreate, db: AsyncSession = Depends(get_db)):
    zone = await crud.create_zone(db, data)
    await crud.create_audit_log(db, "zone_created", details={"zone_id": zone.id, "camera_id": data.camera_id})
    return zone

@app.get("/api/cameras/{camera_id}/zones", response_model=List[schemas.ZoneOut], tags=["Zones"])
async def list_zones(camera_id: int, db: AsyncSession = Depends(get_db)):
    return await crud.list_zones(db, camera_id)


# ─────────────────────────────────────────────
# CV WORKER METADATA INGESTION
# This is the main endpoint called by the CV Worker every 1-2 seconds
# ─────────────────────────────────────────────
@app.post("/api/ingest/metadata", tags=["CV Worker"])
async def ingest_metadata(batch: schemas.CVMetadataBatch, db: AsyncSession = Depends(get_db)):
    """
    Receive metadata batch from CV Worker.
    Stores tracking sessions, detections, zone events.
    No images or face data stored.
    """
    # Update tracking sessions & store detections
    for person in batch.tracked_persons:
        await crud.upsert_tracking_session(
            db,
            camera_id=batch.camera_id,
            tracking_id=person.tracking_id,
            dwell_seconds=person.dwell_seconds or 0.0,
            movement_score=person.movement_score or 0.0,
            zone_id=person.zone_id,
        )

        # Store detection (no image, coords only)
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

        # Store zone entry event
        if person.zone_entry and person.zone_id:
            await crud.create_zone_event(db, schemas.ZoneEventIn(
                camera_id=batch.camera_id,
                tracking_id=person.tracking_id,
                zone_id=person.zone_id,
                dwell_seconds=person.dwell_seconds or 0.0,
            ))

        # Auto-generate alerts
        if person.zone_id and person.dwell_seconds and person.dwell_seconds > 600:
            await crud.create_alert(db, schemas.AlertCreate(
                camera_id=batch.camera_id,
                zone_id=person.zone_id,
                type="long_wait",
                severity="warning",
                message=f"Person waiting over 10 minutes in zone",
            ))

    # Check crowd density per zone
    for zone_name, count in (batch.zone_counts or {}).items():
        if count >= 10:
            await crud.create_alert(db, schemas.AlertCreate(
                camera_id=batch.camera_id,
                type="crowd_alert",
                severity="critical" if count >= 15 else "warning",
                message=f"High crowd density in {zone_name}: {count} people",
            ))

    # Broadcast live update to dashboard via WebSocket
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
async def dashboard_overview(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select, func
    from models import Camera

    people_now = await crud.get_current_people_count(db)
    visits_today = await crud.get_today_visits(db)
    avg_dwell = await crud.get_avg_dwell(db)
    active_alerts = await crud.get_active_alerts_count(db)
    zone_analytics = await crud.get_zone_analytics(db)

    cams = await crud.list_cameras(db)
    online = sum(1 for c in cams if c.status == "online")

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
    db: AsyncSession = Depends(get_db)
):
    count = await crud.get_current_people_count(db, camera_id)
    return {"count": count, "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/api/dashboard/zone-analytics", tags=["Dashboard"])
async def zone_analytics(
    camera_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    return await crud.get_zone_analytics(db, camera_id)

@app.get("/api/dashboard/alerts", response_model=List[schemas.AlertOut], tags=["Dashboard"])
async def get_alerts(
    camera_id: Optional[int] = Query(None),
    unresolved_only: bool = Query(False),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db)
):
    return await crud.list_alerts(db, camera_id=camera_id, unresolved_only=unresolved_only, limit=limit)

@app.post("/api/alerts/{alert_id}/resolve", response_model=schemas.AlertOut, tags=["Dashboard"])
async def resolve_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await crud.resolve_alert(db, alert_id)
    if not alert:
        raise HTTPException(404, detail="Alert not found")
    await crud.create_audit_log(db, "alert_resolved", details={"alert_id": alert_id})
    return alert

@app.get("/api/cameras/{camera_id}/analytics", response_model=schemas.CameraAnalytics, tags=["Dashboard"])
async def camera_analytics(
    camera_id: int,
    date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
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
    db: AsyncSession = Depends(get_db)
):
    await crud.create_audit_log(db, "audit_logs_accessed")
    return await crud.list_audit_logs(db, limit=limit)


# ─────────────────────────────────────────────
# DATA RETENTION MANAGEMENT
# ─────────────────────────────────────────────
@app.post("/api/admin/purge-old-data", tags=["Admin"])
async def purge_old_data(db: AsyncSession = Depends(get_db)):
    """Trigger manual data purge. Deletes data older than retention policy."""
    from sqlalchemy import text
    await db.execute(text("SELECT delete_old_detections()"))
    await db.commit()
    await crud.create_audit_log(db, "data_purge_executed", details={"trigger": "manual"})
    return {"status": "purged", "message": "Old data deleted per retention policy"}


# ─────────────────────────────────────────────
# WEBSOCKET ENDPOINTS
# ─────────────────────────────────────────────
@app.websocket("/ws/dashboard")
async def ws_dashboard(ws: WebSocket):
    """Global dashboard WebSocket - receives all camera updates."""
    await manager.connect_global(ws)
    try:
        while True:
            # Keep alive - client can send pings
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        manager.disconnect_global(ws)

@app.websocket("/ws/camera/{camera_id}")
async def ws_camera(ws: WebSocket, camera_id: int):
    """Camera-specific WebSocket - live view updates."""
    await manager.connect_camera(ws, camera_id)
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        manager.disconnect_camera(ws, camera_id)
