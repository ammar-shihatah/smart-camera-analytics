"""
SQLAlchemy ORM Models - Privacy-First Design
No biometric data, no face images, no identity linking.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    Integer, String, Float, Boolean, Text,
    ForeignKey, DateTime, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Branch(Base):
    __tablename__ = "branches"

    id:         Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    name:       Mapped[str]           = mapped_column(String(255), nullable=False)
    location:   Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=utcnow)

    cameras: Mapped[list["Camera"]] = relationship("Camera", back_populates="branch")


class Camera(Base):
    __tablename__ = "cameras"

    id:         Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    branch_id:  Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("branches.id", ondelete="CASCADE"))
    name:       Mapped[str]           = mapped_column(String(255), nullable=False)
    stream_url: Mapped[Optional[str]] = mapped_column(Text)
    status:     Mapped[str]           = mapped_column(String(50), default="offline")
    created_at: Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=utcnow)

    branch:    Mapped[Optional["Branch"]] = relationship("Branch", back_populates="cameras")
    zones:     Mapped[list["Zone"]]       = relationship("Zone", back_populates="camera")
    alerts:    Mapped[list["Alert"]]      = relationship("Alert", back_populates="camera")


class Zone(Base):
    __tablename__ = "zones"

    id:           Mapped[int]      = mapped_column(Integer, primary_key=True, index=True)
    camera_id:    Mapped[int]      = mapped_column(Integer, ForeignKey("cameras.id", ondelete="CASCADE"))
    name:         Mapped[str]      = mapped_column(String(255), nullable=False)
    type:         Mapped[str]      = mapped_column(String(50), nullable=False)
    polygon_json: Mapped[dict]     = mapped_column(JSON, nullable=False)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    camera: Mapped["Camera"] = relationship("Camera", back_populates="zones")


class TrackingSession(Base):
    __tablename__ = "tracking_sessions"

    id:                   Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    camera_id:            Mapped[int]           = mapped_column(Integer, ForeignKey("cameras.id", ondelete="CASCADE"))
    tracking_id:          Mapped[str]           = mapped_column(String(100), nullable=False, index=True)
    first_seen:           Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen:            Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=utcnow)
    total_dwell_seconds:  Mapped[float]         = mapped_column(Float, default=0.0)
    movement_score:       Mapped[float]         = mapped_column(Float, default=0.0)
    current_zone_id:      Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("zones.id", ondelete="SET NULL"), nullable=True)
    is_active:            Mapped[bool]          = mapped_column(Boolean, default=True)
    created_at:           Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=utcnow)


class Detection(Base):
    __tablename__ = "detections"

    id:                  Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    camera_id:           Mapped[int]           = mapped_column(Integer, ForeignKey("cameras.id", ondelete="CASCADE"))
    tracking_id:         Mapped[str]           = mapped_column(String(100), nullable=False, index=True)
    detected_at:         Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=utcnow)
    bbox_json:           Mapped[Optional[dict]]= mapped_column(JSON)
    centroid_x:          Mapped[Optional[float]]= mapped_column(Float)
    centroid_y:          Mapped[Optional[float]]= mapped_column(Float)
    confidence:          Mapped[Optional[float]]= mapped_column(Float)
    zone_id:             Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("zones.id", ondelete="SET NULL"), nullable=True)
    apparent_expression: Mapped[str]           = mapped_column(String(50), default="face_not_visible")


class ZoneEvent(Base):
    __tablename__ = "zone_events"

    id:            Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    camera_id:     Mapped[int]           = mapped_column(Integer, ForeignKey("cameras.id", ondelete="CASCADE"))
    tracking_id:   Mapped[str]           = mapped_column(String(100), nullable=False)
    zone_id:       Mapped[int]           = mapped_column(Integer, ForeignKey("zones.id", ondelete="CASCADE"))
    entered_at:    Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=utcnow)
    exited_at:     Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    dwell_seconds: Mapped[float]         = mapped_column(Float, default=0.0)


class Interaction(Base):
    __tablename__ = "interactions"

    id:                          Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    camera_id:                   Mapped[int]           = mapped_column(Integer, ForeignKey("cameras.id", ondelete="CASCADE"))
    tracking_id:                 Mapped[str]           = mapped_column(String(100), nullable=False)
    zone_id:                     Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("zones.id", ondelete="SET NULL"), nullable=True)
    started_at:                  Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at:                    Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds:            Mapped[float]         = mapped_column(Float, default=0.0)
    interaction_type:            Mapped[Optional[str]] = mapped_column(String(100))
    apparent_expression_summary: Mapped[Optional[str]] = mapped_column(String(100))


class Alert(Base):
    __tablename__ = "alerts"

    id:          Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    camera_id:   Mapped[int]           = mapped_column(Integer, ForeignKey("cameras.id", ondelete="CASCADE"))
    zone_id:     Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("zones.id", ondelete="SET NULL"), nullable=True)
    type:        Mapped[str]           = mapped_column(String(100), nullable=False)
    severity:    Mapped[str]           = mapped_column(String(20), default="info")
    message:     Mapped[Optional[str]] = mapped_column(Text)
    created_at:  Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    camera: Mapped["Camera"] = relationship("Camera", back_populates="alerts")


class User(Base):
    __tablename__ = "users"

    id:             Mapped[int]               = mapped_column(Integer, primary_key=True, index=True)
    name:           Mapped[str]               = mapped_column(String(255), nullable=False)
    email:          Mapped[str]               = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash:  Mapped[Optional[str]]     = mapped_column(Text, nullable=True)
    role:           Mapped[str]               = mapped_column(String(50), default="viewer")
    is_active:      Mapped[bool]              = mapped_column(Boolean, default=True)
    must_change_pw: Mapped[bool]              = mapped_column(Boolean, default=False)
    last_login:     Mapped[Optional[datetime]]= mapped_column(DateTime(timezone=True), nullable=True)
    created_at:     Mapped[datetime]          = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    user_id:      Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action:       Mapped[str]           = mapped_column(String(255), nullable=False)
    details_json: Mapped[Optional[dict]]= mapped_column(JSON)
    created_at:   Mapped[datetime]      = mapped_column(DateTime(timezone=True), default=utcnow)
