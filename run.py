"""
Protecto.AI - PPE Detection & Safety Analytics Platform
Main entry point to launch the Flask web application and background services.
"""

import os
import sys
from pathlib import Path

# Ensure root directory is on Python search path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.camera import Camera
from app.models.setting import Setting
from app.detector.ppe_detector import detector

# Instantiate the Flask application
app = create_app()

# Bind Flask app context to detector for background DB logging & alerts
detector.set_app_context_callback(app.app_context)


def initialize_runtime():
    """Ensures database tables, directories, and baseline data exist."""
    with app.app_context():
        db.create_all()

        # Provision an administrator only on local development or when explicitly configured.
        admin_username = os.getenv("INITIAL_ADMIN_USERNAME")
        admin_password = os.getenv("INITIAL_ADMIN_PASSWORD")
        if not admin_username and app.config["FLASK_ENV"] != "production" and not app.config["DEMO_MODE"]:
            admin_username = "admin"
            admin_password = "admin123"
        if admin_username and admin_password and not User.query.filter_by(username=admin_username).first():
            admin = User(username=admin_username, email=None, role="admin")
            admin.set_password(admin_password)
            db.session.add(admin)

        # Seed default cameras if empty
        if Camera.query.count() == 0 and not app.config["DEMO_MODE"]:
            cam1 = Camera(name="Main Webcam (Camera 0)", source_type="webcam", source_path="0", is_active=True)
            cam2 = Camera(name="Demo Video (pp2.mp4)", source_type="file", source_path="pp2.mp4", is_active=False)
            db.session.add_all([cam1, cam2])
            print("[+] Seeded default camera sources.")

        db.session.commit()

        conf_val = Setting.get_value("confidence", app.config["DEFAULT_CONFIDENCE"])
        detector.confidence_threshold = (
            float(conf_val) if conf_val is not None else float(app.config["DEFAULT_CONFIDENCE"])
        )
        cooldown_val = Setting.get_value("cooldown", app.config["ALERT_COOLDOWN_SECONDS"])
        detector.alert_cooldown = (
            int(cooldown_val) if cooldown_val is not None else int(app.config["ALERT_COOLDOWN_SECONDS"])
        )

# Run initialization on import so WSGI servers (e.g. Gunicorn) set up tables & seeds
initialize_runtime()

if __name__ == "__main__":
    default_host = "0.0.0.0" if app.config["FLASK_ENV"] == "production" else "127.0.0.1"
    host = os.getenv("FLASK_HOST", default_host)
    port = int(os.getenv("PORT", os.getenv("FLASK_PORT", 5000)))
    debug = os.getenv("DEBUG", "False").lower() in ("true", "1")

    print("\n" + "=" * 60)
    print("[*] Protecto.AI PPE Monitoring System")
    print(f"[*] Running locally at: http://{host}:{port}")
    print("=" * 60 + "\n")

    # Run threaded server to support concurrent MJPEG streaming and UI requests
    app.run(host=host, port=port, debug=False, threaded=True)
