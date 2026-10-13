# 🛡️ Protecto.AI — PPE Detection & Safety Analytics Platform

> **An enterprise-grade Computer Vision and Web Dashboard suite for automated Personal Protective Equipment (PPE) compliance monitoring, worker tracking, violation enforcement, and real-time safety telemetry.**

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.14-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0%2B-black.svg)](https://flask.palletsprojects.com/)
[![YOLOv8](https://img.shields.io/badge/YOLO-v8%20Object%20Detection-orange.svg)](https://docs.ultralytics.com/)
[![ByteTrack](https://img.shields.io/badge/ByteTrack-Tracking-green.svg)](https://github.com/ifzhang/ByteTrack)
[![TailwindCSS](https://img.shields.io/badge/TailwindCSS-Dark%20Theme-38bdf8.svg)](https://tailwindcss.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ed.svg)](https://www.docker.com/)

---

## 📸 Screenshots & Previews

<!-- Screenshot Carousel / Placeholders -->
| Live Safety Dashboard | Historical Trends & Analytics |
|:---:|:---:|
| ![Live Dashboard Preview](https://via.placeholder.com/800x450/0b0f19/06b6d4?text=Protecto.AI+Live+Video+Feed+%2B+SSE+Alerts) | ![Analytics Preview](https://via.placeholder.com/800x450/0b0f19/10b981?text=Compliance+Trends+%2B+PPE+Distribution+Charts) |

| Restricted Zone Configurator | Violations Audit Trail & Evidence |
|:---:|:---:|
| ![Restricted Zones](https://via.placeholder.com/800x450/0b0f19/f59e0b?text=Interactive+Polygon+ROI+Configurator) | ![Violation Log Evidence](https://via.placeholder.com/800x450/0b0f19/f43f5e?text=Snapshot+Thumbnails+%2B+Export+CSV) |

---

## ✨ System Architecture & Highlights

### 1. 👁️ Core Computer Vision Engine
* **YOLOv8 Object Detection** (`best.pt`): Detects workers alongside compliance and non-compliance states (`Hardhat`, `Safety Vest`, `Mask`, `Gloves`, `NO-Hardhat`, `NO-Safety Vest`, `NO-Mask`).
* **ByteTrack Identity Persistence**: Tracks workers across consecutive video frames to prevent ID flickering.
* **Person-PPE Association**: Automatically correlates detected gear to the tightest worker bounding box.
* **Background Detector Worker**: Runs inference asynchronously in a background worker, streaming high-frame-rate MJPEG directly to web clients.

### 2. 🌐 Modern Web Architecture (Flask + Tailwind CSS + SSE)
* **Real-time Live Stream**: Ultra-low-latency MJPEG video streaming at `/video_feed`.
* **Server-Sent Events (SSE)**: Live telemetry metrics (active workers, compliance rate, FPS) and violation alerts pushed directly to the dashboard without page reloads.
* **Role-Based Access Control**: Secure session management using `Flask-Login` and `Werkzeug` salted password hashing with `admin` and `viewer` roles.
* **Restricted Danger Zones (ROI)**: Interactive HTML5 canvas allowing safety managers to draw custom polygonal areas on the video; only workers entering the zone are evaluated for violations.
* **Alert Debouncing**: Configurable cooldown interval per track ID to eliminate alert fatigue.

### 3. 🗄️ Relational Database (SQLite / SQLAlchemy)
* Replaces legacy CSV files with an ACID-compliant database (`User`, `Violation`, `DailyStat`, `Camera`, `Setting` tables).
* Preserves photographic snapshot evidence for every triggered violation under `snapshots/`.
* Export audit trails to CSV or print-ready reports.

---

## 📂 Project Structure

```bash
PythonProject-master/
├── app/
│   ├── detector/
│   │   ├── __init__.py
│   │   └── ppe_detector.py        # YOLOv8 + ByteTrack background streaming engine
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py                # User account model (admin / viewer)
│   │   ├── violation.py           # Safety violation log & snapshot records
│   │   ├── daily_stat.py          # Aggregated daily compliance metrics
│   │   ├── camera.py              # Multi-camera registry & polygon ROI data
│   │   └── setting.py             # Dynamic system runtime configurations
│   ├── routes/
│   │   ├── auth.py                # Login, logout, session management
│   │   ├── main.py                # Dashboard, Analytics, Violations, Zones, Settings
│   │   ├── api.py                 # SSE stream, stats, trend charts, CSV export
│   │   └── video.py               # MJPEG video feed, start/stop, video upload
│   ├── config.py                  # Environment-driven configuration loader
│   └── extensions.py              # SQLAlchemy and Flask-Login instances
├── instance/
│   └── ppe_detection.db           # SQLite database
├── scripts/
│   └── import_csv.py              # Database seeding & ppe_log.csv migration
├── snapshots/                     # Captured violation evidence images
├── static/
│   ├── css/style.css              # Glassmorphic dark theme & animations
│   └── js/main.js                 # Frontend interactions
├── templates/
│   ├── base.html                  # Sidebar layout, toast alerts, top bar
│   ├── login.html                 # Login page with demo credentials
│   ├── dashboard.html             # Video stream, 4 KPI cards, live feed
│   ├── analytics.html             # Chart.js trend lines and doughnut charts
│   ├── violations.html            # Searchable audit table with thumbnail modals
│   ├── zones.html                 # Interactive polygon ROI zone creator
│   └── settings.html              # Confidence slider & debounce config
├── uploads/                       # Uploaded video files for inspection
├── best.pt                        # Trained YOLOv8 model weights
├── bytetrack.yaml                 # ByteTrack tracker configuration
├── run.py                         # Application entry point
├── requirements.txt               # Python package dependencies
├── .env.example                   # Environment variable template
├── .gitignore                     # Git ignore rules
├── Dockerfile                     # Production container image
└── docker-compose.yml             # Container orchestration
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
* Python 3.10, 3.11, or newer
* Git

### 2. Clone and Setup Environment
```bash
# Clone the repository
git clone https://github.com/sahilmohd-10/PythonProject.git
cd PythonProject

# Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install required dependencies
pip install -r requirements.txt
```

### 3. Environment Variables
Copy the template configuration file:
```bash
copy .env.example .env
```
Edit `.env` to configure your application secrets:
```env
FLASK_SECRET_KEY=super-secret-key-change-me
DEFAULT_CONFIDENCE=0.25
ALERT_COOLDOWN_SECONDS=30
```

### 4. Initialize Database & Import Existing CSV Data
Run the migration script to initialize the SQLite database and seed historical records from `ppe_log.csv`:
```bash
python scripts/import_csv.py
```

### 5. Launch the Application
```bash
python run.py
```
Open your browser and navigate to:
```
http://127.0.0.1:5000
```

---

## 🔑 Default Credentials

The system initializes with two pre-configured accounts:

| Role | Username | Password | Privileges |
|:---|:---|:---|:---|
| **Administrator** | `admin` | `admin123` | Full access: start/stop detection, upload videos, modify zones, change settings |
| **Safety Viewer** | `viewer` | `viewer123` | Read-only access: view live stream, audit violations, inspect analytics |

*(Credentials can be auto-filled by clicking the quick-fill buttons on the login page).*

---

## 🐳 Running with Docker

You can easily build and launch Protecto.AI via Docker:

```bash
# Build and run containers
docker-compose up --build -d

# View real-time logs
docker-compose logs -f
```
The application will be accessible at `http://localhost:5000`.

---

## 🛡️ API Endpoints Summary

| Method | Endpoint | Description |
|:---|:---|:---|
| `GET` | `/video_feed` | Multipart MJPEG live video stream |
| `POST` | `/start_detection` | Starts detection on chosen camera/video source |
| `POST` | `/stop_detection` | Halts active detection loop |
| `POST` | `/upload_video` | Uploads new `.mp4`/`.avi` video for inspection |
| `GET` | `/api/stats` | Real-time telemetry (active workers, FPS, compliance %) |
| `GET` | `/api/live_events` | Server-Sent Events (SSE) live push stream |
| `GET` | `/api/analytics/trends` | Historical compliance and category breakdown datasets |
| `GET` | `/api/violations` | Paginated and filtered safety violation logs |
| `POST` | `/api/cameras/<id>/roi` | Saves polygon ROI coordinates for restricted zone |
| `GET` | `/api/export/violations.csv` | Downloads CSV export of all recorded violations |

---

## 📜 License
This project is open-source and distributed under the [MIT License](LICENSE).
