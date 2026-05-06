# Smart Camera Behavior Analytics System (SCA)

> Privacy-first · Real-time · No face recognition · No identity storage

A complete system for analyzing human behavior in physical spaces using computer vision — tracking movement patterns, zone dwell times, crowd density, and aggregate insights without storing any biometric data or identifying individuals.

---

## 🔒 Privacy Principles

| What we DO | What we DON'T |
|---|---|
| ✅ Assign **temporary session IDs** per camera session | ❌ Face recognition |
| ✅ Store movement **metadata** (coords, dwell, zone) | ❌ Store face images |
| ✅ Aggregate analytics (counts, averages) | ❌ Link IDs across sessions |
| ✅ Apparent expression (visual cue only) | ❌ Store video footage |
| ✅ Auto-delete data after 30 days | ❌ Identify any individual |
| ✅ Audit logs for all data access | ❌ Biometric data |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Network                            │
│                                                                  │
│  ┌──────────────┐    REST/WS     ┌──────────────────────────┐  │
│  │  CV Worker   │ ─────────────► │   FastAPI Backend        │  │
│  │  (Python)    │                │   (Python + SQLAlchemy)  │  │
│  │              │                │   :8000                  │  │
│  │  YOLOv8      │                └──────────┬───────────────┘  │
│  │  Centroid    │                           │                   │
│  │  Tracker     │                    ┌──────▼──────┐           │
│  │              │                    │ PostgreSQL  │           │
│  │  Zone Utils  │                    │ :5432       │           │
│  └──────────────┘                    └─────────────┘           │
│                                           │ WebSocket           │
│                                    ┌──────▼──────────────────┐ │
│                                    │  React Dashboard        │ │
│                                    │  (Vite + Recharts)      │ │
│                                    │  :5173                  │ │
│                                    └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- (For CV Worker without Docker) Python 3.10+, OpenCV, webcam or video file

### 1. Clone & Configure

```bash
git clone <repo>
cd smart-camera-analytics
cp .env.example .env
# Edit .env with your settings
```

### 2. Start Core Services (Backend + DB + Frontend)

```bash
docker compose up -d db backend frontend
```

Open **http://localhost:5173** — Dashboard is live.

### 3. Start CV Worker

**Option A — Docker (headless, no preview)**
```bash
# With webcam
VIDEO_SOURCE=0 docker compose --profile worker up cv-worker

# With video file (place in ./videos/ folder)
VIDEO_SOURCE=/videos/test.mp4 docker compose --profile worker up cv-worker
```

**Option B — Local Python (with live preview window)**
```bash
cd cv-worker
pip install -r requirements.txt

# Webcam
python worker.py --source 0 --camera-id 1

# Video file
python worker.py --source /path/to/test.mp4 --camera-id 1

# RTSP IP camera
python worker.py --source rtsp://admin:pass@192.168.1.100:554/stream1 --camera-id 1

# With config file
cp config.example.json config.json
# Edit config.json
python worker.py --config config.json
```

---

## 📁 Project Structure

```
smart-camera-analytics/
├── docker-compose.yml
├── .env.example
├── README.md
│
├── database/
│   └── init.sql              # Schema + seed data
│
├── backend/                  # FastAPI
│   ├── main.py               # Routes, WebSocket endpoints
│   ├── models.py             # SQLAlchemy ORM models
│   ├── schemas.py            # Pydantic validation schemas
│   ├── crud.py               # Database operations
│   ├── database.py           # Async DB connection
│   ├── websocket_manager.py  # WS connection manager
│   └── requirements.txt
│
├── cv-worker/                # Computer Vision
│   ├── worker.py             # Main processing loop
│   ├── tracker.py            # Centroid tracker (TODO: ByteTrack)
│   ├── zone_utils.py         # Polygon zone geometry
│   ├── expression_utils.py   # Apparent expression (privacy-safe)
│   ├── config.example.json
│   └── requirements.txt
│
└── frontend/                 # React Dashboard
    ├── src/
    │   ├── main.jsx          # Entry point + global styles
    │   ├── App.jsx           # Router + sidebar layout
    │   ├── api.js            # API client + WebSocket helpers
    │   ├── pages/
    │   │   ├── Dashboard.jsx # Overview + live charts
    │   │   ├── Cameras.jsx   # Camera management
    │   │   ├── CameraView.jsx# Per-camera live feed
    │   │   └── Alerts.jsx    # Alert management
    │   └── components/
    │       └── StatCard.jsx
    └── package.json
```

---

## 🌐 API Reference

### Dashboard
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard/overview` | Full dashboard stats |
| GET | `/api/dashboard/people-count` | Current live count |
| GET | `/api/dashboard/zone-analytics` | Per-zone stats |
| GET | `/api/dashboard/alerts` | Alerts list |
| POST | `/api/alerts/{id}/resolve` | Resolve an alert |

### Cameras
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/cameras` | Create camera |
| GET | `/api/cameras` | List all cameras |
| GET | `/api/cameras/{id}` | Get camera details |
| PATCH | `/api/cameras/{id}` | Update status/config |
| GET | `/api/cameras/{id}/analytics` | Camera analytics |
| GET | `/api/cameras/{id}/zones` | List zones |

### Zones
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/zones` | Create zone with polygon |
| GET | `/api/cameras/{id}/zones` | List zones for camera |

### CV Worker
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ingest/metadata` | Receive CV batch (no images) |

### WebSocket
| URL | Description |
|-----|-------------|
| `ws://localhost:8000/ws/dashboard` | All cameras live feed |
| `ws://localhost:8000/ws/camera/{id}` | Single camera feed |

### Interactive Docs
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 📊 Zone Configuration

Zones are defined as polygon coordinates in JSON format:

```json
{
  "camera_id": 1,
  "name": "Service Counter",
  "type": "counter",
  "polygon_json": [[100, 100], [500, 100], [500, 400], [100, 400]]
}
```

Zone types: `entrance` | `counter` | `waiting` | `shared_area` | `room_area`

---

## 🔧 CV Worker Configuration

Edit `cv-worker/config.example.json`:

```json
{
  "video_source": "0",          // 0=webcam, path=file, rtsp://=IP cam
  "camera_id": 1,               // Must match backend camera ID
  "yolo_model": "yolov8n.pt",   // n=nano(fast), s=small, m=medium
  "confidence_threshold": 0.4,
  "send_interval_seconds": 1.5,
  "frame_skip": 2,              // Process every 2nd frame
  "show_preview": true          // OpenCV window
}
```

---

## 🗄️ Data Retention Policy

Data is automatically deleted after:
- **Detections**: 30 days
- **Zone events**: 30 days  
- **Tracking sessions**: 30 days
- **Audit logs**: 90 days

Manual purge: `POST /api/admin/purge-old-data`

Or schedule via cron / pg_cron:
```sql
SELECT delete_old_detections();  -- run daily
```

---

## 🔄 Upgrading Tracker to ByteTrack

The current `CentroidTracker` is an MVP implementation. To upgrade to ByteTrack:

```python
# In cv-worker/tracker.py, replace CentroidTracker.update() with:
# (requires: pip install bytetracker)

from ultralytics import YOLO
model = YOLO("yolov8n.pt")
results = model.track(frame, persist=True, tracker="bytetrack.yaml", classes=[0])
for box in results[0].boxes:
    tracking_id = f"T{int(box.id[0]):04d}"
    bbox = box.xyxy[0].tolist()
    # ... rest of logic
```

---

## 🏗️ Production Checklist

- [ ] Change `SECRET_KEY` in `.env`
- [ ] Change database password in `.env`
- [ ] Configure HTTPS / reverse proxy (nginx)
- [ ] Set `show_preview: false` in CV Worker for headless operation
- [ ] Configure pg_cron for automatic data retention
- [ ] Set up monitoring (Prometheus / Grafana)
- [ ] Review and configure `CORS_ORIGINS`
- [ ] Add authentication to backend endpoints

---

## 📜 License

MIT License — See LICENSE file.

**Important**: This system is designed for legitimate business analytics (retail, branch management, service quality) with explicit privacy controls. Ensure compliance with local privacy laws (GDPR, etc.) and provide appropriate notice to individuals being recorded.
