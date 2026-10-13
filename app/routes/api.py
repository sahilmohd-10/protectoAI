import json
import time
from datetime import datetime, timedelta, timezone
from flask import Blueprint, jsonify, request, Response, send_file, current_app
from flask_login import login_required, current_user
import io
import csv
from collections import defaultdict
from sqlalchemy import or_

from app.detector.ppe_detector import detector
from app.models.violation import Violation
from app.models.daily_stat import DailyStat
from app.models.camera import Camera
from app.models.setting import Setting
from app.extensions import db

api_bp = Blueprint("api", __name__)


@api_bp.route("/stats")
@login_required
def get_stats():
    """Live telemetry stats for dashboard cards."""
    # Today's aggregated violations from DB
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    violations_today = Violation.query.filter(Violation.timestamp >= today_start).count()

    # Most missed PPE item
    hardhat_viols = Violation.query.filter(Violation.timestamp >= today_start, Violation.violation_type == "Hardhat").count()
    vest_viols = Violation.query.filter(Violation.timestamp >= today_start, Violation.violation_type == "Safety Vest").count()
    mask_viols = Violation.query.filter(Violation.timestamp >= today_start, Violation.violation_type == "Mask").count()

    missed_counts = {"Hardhat": hardhat_viols, "Safety Vest": vest_viols, "Mask": mask_viols}
    most_missed = max(missed_counts, key=missed_counts.get) if violations_today > 0 else "None"

    data = {
        "metrics": detector.metrics,
        "violations_today": violations_today,
        "most_missed_ppe": most_missed,
        "breakdown": missed_counts,
    }
    return jsonify(data)


@api_bp.route("/live_events")
@login_required
def live_events():
    """Server-Sent Events (SSE) endpoint pushing live metrics and new violation alerts."""
    if current_app.config["DEMO_MODE"]:
        return jsonify({"status": "disabled", "message": "Live events are disabled in demo mode."}), 403

    def event_stream():
        last_sent_count = 0
        while True:
            # 1. Push metrics update
            metrics_payload = json.dumps({"type": "metrics", "data": detector.metrics})
            yield f"data: {metrics_payload}\n\n"

            # 2. Push any new violations from detector queue
            current_count = len(detector.recent_violations)
            if current_count > last_sent_count:
                new_items = detector.recent_violations[:current_count - last_sent_count]
                for v in reversed(new_items):
                    viol_payload = json.dumps({"type": "violation", "data": v})
                    yield f"data: {viol_payload}\n\n"
                last_sent_count = current_count

            time.sleep(1.0)

    return Response(event_stream(), mimetype="text/event-stream")


@api_bp.route("/violations")
@login_required
def list_violations():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    violation_type = request.args.get("type", "").strip()
    camera_filter = request.args.get("camera", "").strip()
    date_filter = request.args.get("date", "").strip()
    search_filter = request.args.get("q", "").strip()

    query = Violation.query

    if violation_type:
        query = query.filter(Violation.violation_type == violation_type)
    if camera_filter:
        query = query.filter(Violation.camera == camera_filter)
    if search_filter:
        search_terms = [
            Violation.camera.ilike(f"%{search_filter}%"),
            Violation.violation_type.ilike(f"%{search_filter}%"),
        ]
        if search_filter.isdigit():
            search_terms.append(Violation.track_id == int(search_filter))
        query = query.filter(or_(*search_terms))
    if date_filter:
        try:
            target_date = datetime.strptime(date_filter, "%Y-%m-%d")
            next_day = target_date + timedelta(days=1)
            query = query.filter(Violation.timestamp >= target_date, Violation.timestamp < next_day)
        except ValueError:
            pass

    pagination = query.order_by(Violation.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "items": [v.to_dict() for v in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": pagination.page,
    })


@api_bp.route("/violations/<int:violation_id>/acknowledge", methods=["POST"])
@login_required
def acknowledge_violation(violation_id):
    violation = Violation.query.get_or_404(violation_id)
    violation.acknowledged = True
    db.session.commit()
    return jsonify({"status": "success", "message": "Violation marked as reviewed."})


@api_bp.route("/analytics/trends")
@login_required
def analytics_trends():
    """Returns Chart.js compatible time-series and breakdown datasets."""
    days = min(max(request.args.get("days", 3650, type=int), 1), 3650)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Historical Daily stats from SQLite
    stats = DailyStat.query.filter(DailyStat.date >= cutoff.date()).order_by(DailyStat.date.asc()).all()

    violations_by_date = defaultdict(lambda: {"Hardhat": 0, "Safety Vest": 0, "Mask": 0, "Gloves": 0})
    category_totals = {"Hardhat": 0, "Safety Vest": 0, "Mask": 0, "Gloves": 0}
    heatmap = [[0 for _ in range(24)] for _ in range(7)]
    viols = Violation.query.filter(Violation.timestamp >= cutoff).all()
    for v in viols:
        if v.timestamp:
            day = v.timestamp.strftime("%Y-%m-%d")
            if v.violation_type in category_totals:
                violations_by_date[day][v.violation_type] += 1
                category_totals[v.violation_type] += 1
            w = v.timestamp.weekday()
            h = v.timestamp.hour
            if 0 <= w < 7 and 0 <= h < 24:
                heatmap[w][h] += 1

    compliance_by_date = {stat.date: stat.compliance_rate for stat in stats}
    dates = sorted(set(compliance_by_date) | set(violations_by_date))
    compliance_rates = [compliance_by_date.get(day) for day in dates]
    hardhat_totals = [violations_by_date[day]["Hardhat"] for day in dates]
    vest_totals = [violations_by_date[day]["Safety Vest"] for day in dates]
    mask_totals = [violations_by_date[day]["Mask"] for day in dates]
    gloves_totals = [violations_by_date[day]["Gloves"] for day in dates]
    known_compliance_rates = [rate for rate in compliance_rates if rate is not None]

    return jsonify({
        "line_chart": {
            "labels": dates,
            "compliance": compliance_rates,
            "hardhat": hardhat_totals,
            "vest": vest_totals,
            "mask": mask_totals,
        },
        "donut_chart": {
            "labels": ["Hardhat", "Safety Vest", "Mask", "Gloves"],
            "data": [category_totals["Hardhat"], category_totals["Safety Vest"], category_totals["Mask"], category_totals["Gloves"]],
        },
        "summary": {
            "total_violations": len(viols),
            "days_recorded": len(stats),
            "avg_compliance": round(sum(known_compliance_rates) / max(len(known_compliance_rates), 1), 1),
        },
        "heatmap": heatmap,
    })


@api_bp.route("/cameras", methods=["GET", "POST"])
@login_required
def handle_cameras():
    if request.method == "POST":
        if not current_user.is_admin:
            return jsonify({"status": "error", "message": "Administrator authorization required."}), 403
        data = request.get_json() or {}
        name = data.get("name")
        source_type = data.get("source_type", "webcam")
        source_path = data.get("source_path", "0")
        if not name or not source_path:
            return jsonify({"status": "error", "message": "Name and source path required"}), 400

        cam = Camera(name=name, source_type=source_type, source_path=source_path)
        db.session.add(cam)
        db.session.commit()
        return jsonify({"status": "success", "camera": cam.to_dict()})

    cameras = Camera.query.order_by(Camera.id.asc()).all() if current_app.config["DEMO_MODE"] else Camera.sync_connected_cameras()
    return jsonify({
        "status": "success",
        "cameras": [camera.to_dict() for camera in cameras],
        "active_camera_id": detector.camera_id,
    })


@api_bp.route("/cameras/<int:cam_id>/roi", methods=["POST"])
@login_required
def update_roi(cam_id):
    if current_app.config["DEMO_MODE"] or not current_user.is_admin:
        return jsonify({"status": "error", "message": "Administrator authorization required."}), 403
    cam = Camera.query.get_or_404(cam_id)
    data = request.get_json() or {}
    points = data.get("points")  # [[x1, y1], [x2, y2], ...]
    if points is not None and (not isinstance(points, list) or len(points) < 3 or any(
        not isinstance(point, list) or len(point) != 2 or
        not all(isinstance(value, (int, float)) and 0 <= value <= 10000 for value in point)
        for point in points
    )):
        return jsonify({"status": "error", "message": "A zone must contain at least three valid points."}), 400
    cam.set_roi_points(points)
    db.session.commit()

    if detector.camera_id == cam_id:
        detector.polygon_roi = points

    return jsonify({"status": "success", "message": "ROI polygon updated."})


@api_bp.route("/settings", methods=["POST"])
@login_required
def update_settings():
    if current_app.config["DEMO_MODE"] or not current_user.is_admin:
        return jsonify({"status": "error", "message": "Administrator authorization required."}), 403

    data = request.get_json() or {}
    try:
        confidence = float(data.get("confidence"))
        cooldown = int(data.get("cooldown"))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Enter valid confidence and cooldown values."}), 400
    if not 0.05 <= confidence <= 0.95 or not 1 <= cooldown <= 3600:
        return jsonify({"status": "error", "message": "Confidence must be 0.05-0.95 and cooldown 1-3600 seconds."}), 400

    Setting.set_value("confidence", confidence, "Minimum model confidence threshold")
    Setting.set_value("cooldown", cooldown, "Alert cooldown per worker and PPE type")
    detector.confidence_threshold = confidence
    detector.alert_cooldown = cooldown
    return jsonify({"status": "success", "message": "Detection settings saved."})


@api_bp.route("/export/violations.csv")
@login_required
def export_violations_csv():
    """Generates downloadable CSV export of all violation records."""
    violations = Violation.query.order_by(Violation.timestamp.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Timestamp", "Track ID", "Violation Type", "Camera", "Confidence", "Snapshot Path"])

    for v in violations:
        writer.writerow([
            v.id,
            v.timestamp.strftime("%Y-%m-%d %H:%M:%S") if v.timestamp else "",
            v.track_id,
            v.violation_type,
            v.camera,
            v.confidence,
            v.snapshot_path or "",
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=violations_export.csv"}
    )


@api_bp.route("/violations/clear", methods=["POST"])
@login_required
def clear_violations():
    """Admin-only: clear all violation records."""
    from flask_login import current_user
    if current_app.config["DEMO_MODE"] or not current_user.is_admin:
        return jsonify({"status": "error", "message": "Admin authorization required."}), 403

    try:
        Violation.query.delete()
        db.session.commit()
        return jsonify({"status": "success", "message": "All violation records have been cleared."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500
