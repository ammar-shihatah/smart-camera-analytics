-- Smart Camera Behavior Analytics System
-- Database Schema - Privacy-First Design
-- No face images, no biometric data, no identity stored

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─────────────────────────────────────────────
-- BRANCHES
-- ─────────────────────────────────────────────
CREATE TABLE branches (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    location    VARCHAR(500),
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- CAMERAS
-- ─────────────────────────────────────────────
CREATE TABLE cameras (
    id          SERIAL PRIMARY KEY,
    branch_id   INTEGER REFERENCES branches(id) ON DELETE CASCADE,
    name        VARCHAR(255) NOT NULL,
    stream_url  TEXT,
    status      VARCHAR(50) DEFAULT 'offline' CHECK (status IN ('online','offline','error','maintenance')),
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- ZONES
-- ─────────────────────────────────────────────
CREATE TABLE zones (
    id           SERIAL PRIMARY KEY,
    camera_id    INTEGER REFERENCES cameras(id) ON DELETE CASCADE,
    name         VARCHAR(255) NOT NULL,
    type         VARCHAR(50) NOT NULL CHECK (type IN ('entrance','counter','waiting','shared_area','room_area')),
    polygon_json JSONB NOT NULL,
    created_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- TRACKING SESSIONS (no identity stored)
-- ─────────────────────────────────────────────
CREATE TABLE tracking_sessions (
    id                  SERIAL PRIMARY KEY,
    camera_id           INTEGER REFERENCES cameras(id) ON DELETE CASCADE,
    tracking_id         VARCHAR(100) NOT NULL,   -- temp session ID only, not linked to identity
    first_seen          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen           TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    total_dwell_seconds FLOAT DEFAULT 0,
    movement_score      FLOAT DEFAULT 0,
    current_zone_id     INTEGER REFERENCES zones(id) ON DELETE SET NULL,
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_tracking_sessions_camera ON tracking_sessions(camera_id);
CREATE INDEX idx_tracking_sessions_active ON tracking_sessions(is_active);
CREATE INDEX idx_tracking_sessions_tracking_id ON tracking_sessions(tracking_id);

-- ─────────────────────────────────────────────
-- DETECTIONS (no images, no biometric data)
-- ─────────────────────────────────────────────
CREATE TABLE detections (
    id                  SERIAL PRIMARY KEY,
    camera_id           INTEGER REFERENCES cameras(id) ON DELETE CASCADE,
    tracking_id         VARCHAR(100) NOT NULL,
    detected_at         TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    bbox_json           JSONB,           -- bounding box coords only, no image
    centroid_x          FLOAT,
    centroid_y          FLOAT,
    confidence          FLOAT,
    zone_id             INTEGER REFERENCES zones(id) ON DELETE SET NULL,
    apparent_expression VARCHAR(50) DEFAULT 'face_not_visible'
        CHECK (apparent_expression IN ('apparent_smile','neutral','face_not_visible'))
);

CREATE INDEX idx_detections_camera ON detections(camera_id);
CREATE INDEX idx_detections_detected_at ON detections(detected_at);
CREATE INDEX idx_detections_tracking_id ON detections(tracking_id);

-- ─────────────────────────────────────────────
-- ZONE EVENTS
-- ─────────────────────────────────────────────
CREATE TABLE zone_events (
    id             SERIAL PRIMARY KEY,
    camera_id      INTEGER REFERENCES cameras(id) ON DELETE CASCADE,
    tracking_id    VARCHAR(100) NOT NULL,
    zone_id        INTEGER REFERENCES zones(id) ON DELETE CASCADE,
    entered_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    exited_at      TIMESTAMP WITH TIME ZONE,
    dwell_seconds  FLOAT DEFAULT 0
);

CREATE INDEX idx_zone_events_zone ON zone_events(zone_id);
CREATE INDEX idx_zone_events_camera ON zone_events(camera_id);

-- ─────────────────────────────────────────────
-- INTERACTIONS
-- ─────────────────────────────────────────────
CREATE TABLE interactions (
    id                          SERIAL PRIMARY KEY,
    camera_id                   INTEGER REFERENCES cameras(id) ON DELETE CASCADE,
    tracking_id                 VARCHAR(100) NOT NULL,
    zone_id                     INTEGER REFERENCES zones(id) ON DELETE SET NULL,
    started_at                  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ended_at                    TIMESTAMP WITH TIME ZONE,
    duration_seconds            FLOAT DEFAULT 0,
    interaction_type            VARCHAR(100),
    apparent_expression_summary VARCHAR(100)
);

-- ─────────────────────────────────────────────
-- ALERTS
-- ─────────────────────────────────────────────
CREATE TABLE alerts (
    id          SERIAL PRIMARY KEY,
    camera_id   INTEGER REFERENCES cameras(id) ON DELETE CASCADE,
    zone_id     INTEGER REFERENCES zones(id) ON DELETE SET NULL,
    type        VARCHAR(100) NOT NULL,
    severity    VARCHAR(20) DEFAULT 'info' CHECK (severity IN ('info','warning','critical')),
    message     TEXT,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_alerts_camera ON alerts(camera_id);
CREATE INDEX idx_alerts_created_at ON alerts(created_at);
CREATE INDEX idx_alerts_resolved ON alerts(resolved_at);

-- ─────────────────────────────────────────────
-- USERS
-- ─────────────────────────────────────────────
CREATE TABLE users (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(255) NOT NULL,
    email          VARCHAR(255) UNIQUE NOT NULL,
    password_hash  TEXT,
    role           VARCHAR(50) DEFAULT 'viewer'
                   CHECK (role IN ('super_admin','admin','branch_manager','operations_manager','receptionist','viewer')),
    is_active      BOOLEAN DEFAULT TRUE,
    must_change_pw BOOLEAN DEFAULT FALSE,
    last_login     TIMESTAMP WITH TIME ZONE,
    created_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);

-- ─────────────────────────────────────────────
-- AUDIT LOGS
-- ─────────────────────────────────────────────
CREATE TABLE audit_logs (
    id           SERIAL PRIMARY KEY,
    user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action       VARCHAR(255) NOT NULL,
    details_json JSONB,
    created_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_user ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);

-- ─────────────────────────────────────────────
-- DATA RETENTION POLICY
-- Auto-delete old detections after 30 days
-- ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION delete_old_detections() RETURNS void AS $$
BEGIN
    DELETE FROM detections WHERE detected_at < NOW() - INTERVAL '30 days';
    DELETE FROM zone_events WHERE entered_at < NOW() - INTERVAL '30 days';
    DELETE FROM tracking_sessions WHERE last_seen < NOW() - INTERVAL '30 days';
    DELETE FROM audit_logs WHERE created_at < NOW() - INTERVAL '90 days';
END;
$$ LANGUAGE plpgsql;

-- ─────────────────────────────────────────────
-- SEED DATA
-- ─────────────────────────────────────────────
INSERT INTO branches (name, location) VALUES
    ('Main Branch', 'Downtown HQ'),
    ('North Branch', 'North District');

INSERT INTO cameras (branch_id, name, stream_url, status) VALUES
    (1, 'Entrance Cam', 'rtsp://demo/stream1', 'online'),
    (1, 'Counter Cam',  'rtsp://demo/stream2', 'online'),
    (1, 'Waiting Area', 'rtsp://demo/stream3', 'offline');

INSERT INTO zones (camera_id, name, type, polygon_json) VALUES
    (1, 'Main Entrance', 'entrance', '[[0,0],[320,0],[320,240],[0,240]]'),
    (1, 'Counter Area',  'counter',  '[[320,0],[640,0],[640,240],[320,240]]'),
    (1, 'Waiting Zone',  'waiting',  '[[0,240],[640,240],[640,480],[0,480]]'),
    (2, 'Service Counter','counter', '[[100,100],[500,100],[500,400],[100,400]]');

-- Default admin — password is "Admin@1234" (hashed by backend on first start)
-- The backend seeds this automatically if no users exist.

INSERT INTO alerts (camera_id, zone_id, type, severity, message) VALUES
    (1, 3, 'crowd_alert',   'warning',  'High crowd density in Waiting Zone'),
    (1, 2, 'long_wait',     'critical', 'Average wait time exceeded 10 minutes at Counter'),
    (2, 4, 'queue_buildup', 'info',     'Queue forming at Service Counter');
