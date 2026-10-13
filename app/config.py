import os
from pathlib import Path
from dotenv import load_dotenv

# Base project directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env if present
load_dotenv(dotenv_path=BASE_DIR / ".env")


class Config:
    """Application configuration settings."""

    FLASK_ENV = os.getenv("FLASK_ENV", "development")
    _secret_key = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY")
    if FLASK_ENV == "production" and not _secret_key:
        raise RuntimeError("Set SECRET_KEY in the production environment.")
    SECRET_KEY = _secret_key or "local-development-key-change-me"
    DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")
    
    # Database
    db_dir = BASE_DIR / "instance"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_file = db_dir / "ppe_detection.db"
    
    _raw_db_url = os.getenv("DATABASE_URL", "")
    if not _raw_db_url or _raw_db_url.startswith("sqlite:///instance/"):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_file.as_posix()}"
    else:
        SQLALCHEMY_DATABASE_URI = _raw_db_url

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Directories
    UPLOAD_FOLDER = BASE_DIR / "uploads"
    SNAPSHOT_FOLDER = BASE_DIR / "snapshots"
    STATIC_FOLDER = BASE_DIR / "static"
    TEMPLATE_FOLDER = BASE_DIR / "templates"
    
    # Model & Detection
    MODEL_PATH = str(BASE_DIR / os.getenv("MODEL_PATH", "best.pt"))
    TRACKER_CFG = os.getenv("TRACKER_CFG", "bytetrack.yaml")
    DEFAULT_CONFIDENCE = float(os.getenv("DEFAULT_CONFIDENCE", "0.25"))
    ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "30"))

    # Telegram Alerting & Reporting
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    CHAT_ID = os.getenv("CHAT_ID", "")
    ENABLE_TELEGRAM = os.getenv("ENABLE_TELEGRAM", "false").lower() in ("true", "1", "yes")
    WEEKLY_REPORT_DAY = os.getenv("WEEKLY_REPORT_DAY", "sunday")
    WEEKLY_REPORT_TIME = os.getenv("WEEKLY_REPORT_TIME", "18:00")


