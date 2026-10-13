import os
from datetime import datetime, timedelta
from pathlib import Path
from secrets import token_urlsafe
from flask import Flask
from app.config import Config
from app.extensions import db, login_manager
from sqlalchemy import inspect, text


def create_app(config_class=Config):
    """Application factory for PPE Detection & Analysis System."""
    base_dir = Path(__file__).resolve().parent.parent

    app = Flask(
        __name__,
        template_folder=str(base_dir / "templates"),
        static_folder=str(base_dir / "static"),
    )
    app.config.from_object(config_class)

    # Ensure necessary runtime directories exist
    instance_dir = base_dir / "instance"
    uploads_dir = base_dir / "uploads"
    snapshots_dir = base_dir / "snapshots"
    for folder in [instance_dir, uploads_dir, snapshots_dir]:
        folder.mkdir(parents=True, exist_ok=True)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)

    # Setup User loader
    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register Blueprints
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.api import api_bp
    from app.routes.video import video_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(video_bp)

    @app.context_processor
    def inject_runtime_flags():
        return {"demo_mode": app.config["DEMO_MODE"]}

    # Add profile fields to databases created by earlier versions.
    with app.app_context():
        db.create_all()
        inspector = inspect(db.engine)
        if inspector.has_table("users"):
            existing_columns = {column["name"] for column in inspector.get_columns("users")}
            profile_columns = {
                "full_name": "VARCHAR(120)",
                "phone": "VARCHAR(20)",
                "site_name": "VARCHAR(120)",
            }
            with db.engine.begin() as connection:
                for column_name, column_type in profile_columns.items():
                    if column_name not in existing_columns:
                        connection.execute(text(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}"))

        if app.config["DEMO_MODE"]:
            from app.models.camera import Camera
            from app.models.daily_stat import DailyStat
            from app.models.violation import Violation

            if not User.query.filter_by(username="demo").first():
                demo_user = User(
                    username="demo",
                    email="demo@protecto.local",
                    full_name="Protecto Demo",
                    phone="0000000000",
                    site_name="Sample Worksite",
                    role="user",
                )
                demo_user.set_password(token_urlsafe(32))
                db.session.add(demo_user)

            if not Camera.query.filter_by(source_type="demo").first():
                db.session.add(Camera(
                    name="Sample Worksite Feed",
                    source_type="demo",
                    source_path="demo",
                    is_active=True,
                ))

            if Violation.query.count() == 0:
                sample_incidents = [
                    (0, "Hardhat", 1),
                    (0, "Safety Vest", 2),
                    (1, "Mask", 3),
                    (2, "Hardhat", 4),
                    (4, "Safety Vest", 5),
                    (8, "Hardhat", 6),
                ]
                for days_ago, incident_type, track_id in sample_incidents:
                    db.session.add(Violation(
                        timestamp=datetime.utcnow() - timedelta(days=days_ago, hours=track_id),
                        track_id=track_id,
                        violation_type=incident_type,
                        camera="Sample Worksite Feed",
                        confidence=0.82 + track_id / 100,
                    ))

            if DailyStat.query.count() == 0:
                for days_ago, compliance in ((0, 92.0), (1, 89.5), (2, 94.0), (4, 87.0), (8, 96.0)):
                    db.session.add(DailyStat(
                        date=(datetime.utcnow().date() - timedelta(days=days_ago)).isoformat(),
                        hardhat_not=2 if days_ago % 2 == 0 else 1,
                        vest_not=1,
                        mask_not=1 if days_ago == 2 else 0,
                        total_workers=18,
                        compliance_rate=compliance,
                    ))

            db.session.commit()

    return app
