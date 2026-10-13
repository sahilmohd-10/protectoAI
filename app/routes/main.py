from pathlib import Path
from flask import Blueprint, render_template, request, flash, redirect, url_for, send_from_directory, current_app
from flask_login import login_required, current_user, login_user

from app.models.camera import Camera
from app.models.violation import Violation
from app.models.setting import Setting
from app.models.daily_stat import DailyStat
from app.detector.ppe_detector import detector
from app.extensions import db

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def dashboard():
    demo_mode = current_app.config["DEMO_MODE"]
    if demo_mode and not current_user.is_authenticated:
        from app.models.user import User
        demo_user = User.query.filter_by(username="demo").first()
        if demo_user:
            login_user(demo_user)

    if not current_user.is_authenticated:
        return render_template("home.html")

    cameras = Camera.query.order_by(Camera.id.asc()).all() if demo_mode else Camera.sync_connected_cameras()
    active_camera = Camera.query.filter_by(id=detector.camera_id).first()
    if not active_camera and cameras:
        active_camera = cameras[0]
    recent_viols = Violation.query.order_by(Violation.timestamp.desc()).limit(10).all()
    demo_rates = [stat.compliance_rate for stat in DailyStat.query.all()] if demo_mode else []
    demo_compliance = round(sum(demo_rates) / len(demo_rates), 1) if demo_rates else detector.metrics["compliance_rate"]
    return render_template(
        "dashboard.html",
        cameras=cameras,
        active_camera=active_camera,
        recent_violations=recent_viols,
        demo_mode=demo_mode,
        demo_compliance=demo_compliance,
        user=current_user,
    )


@main_bp.route("/dashboard")
@login_required
def dashboard_alias():
    return redirect(url_for("main.dashboard"))


@main_bp.route("/analytics")
@login_required
def analytics():
    return render_template("analytics.html", user=current_user)


@main_bp.route("/violations")
@login_required
def violations_page():
    cameras = Camera.query.all()
    review_counts = {
        "open": Violation.query.filter_by(acknowledged=False).count(),
        "reviewed": Violation.query.filter_by(acknowledged=True).count(),
    }
    return render_template("violations.html", cameras=cameras, review_counts=review_counts, user=current_user)


@main_bp.route("/zones")
@login_required
def zones():
    cameras = Camera.query.order_by(Camera.id.asc()).all()
    return render_template("zones.html", cameras=cameras, user=current_user)


@main_bp.route("/settings")
@login_required
def settings_page():
    settings = {
        "confidence": Setting.get_value("confidence", current_app.config["DEFAULT_CONFIDENCE"]),
        "cooldown": Setting.get_value("cooldown", current_app.config["ALERT_COOLDOWN_SECONDS"]),
    }
    return render_template("settings.html", settings=settings, user=current_user)


@main_bp.route("/admin/users")
@login_required
def users_page():
    if not current_user.is_admin:
        flash("Administrator privileges required.", "danger")
        return redirect(url_for("main.dashboard"))
    from app.models.user import User
    users = User.query.order_by(User.created_at.desc()).all()
    role_counts = {
        "admins": User.query.filter_by(role="admin").count(),
        "users": User.query.filter(User.role != "admin").count(),
    }
    return render_template("users.html", users=users, role_counts=role_counts, user=current_user)


@main_bp.route("/snapshots/<path:filename>")
@login_required
def serve_snapshot(filename):
    snapshots_dir = Path(current_app.config["SNAPSHOT_FOLDER"])
    return send_from_directory(snapshots_dir, filename)
