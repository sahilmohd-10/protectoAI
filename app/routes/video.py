import os
from pathlib import Path
from flask import Blueprint, Response, request, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.detector.ppe_detector import detector
from app.models.camera import Camera
from app.extensions import db

video_bp = Blueprint("video", __name__)
ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "mkv"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@video_bp.route("/video_feed")
@login_required
def video_feed():
    """MJPEG streaming route consumed directly by HTML <img> tag."""
    return Response(
        detector.generate_mjpeg_frames(demo_mode=current_app.config["DEMO_MODE"]),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@video_bp.route("/start_detection", methods=["POST"])
@login_required
def start_detection():
    # Authenticated users can start detection on active camera sources

    data = request.get_json() or {}
    camera_id = data.get("camera_id")
    source_val = data.get("source")
    camera_name = data.get("name", "Custom Stream")

    polygon_roi = None

    if camera_id:
        cam = Camera.query.get(camera_id)
        if cam:
            Camera.query.update({Camera.is_active: False})
            cam.is_active = True
            db.session.commit()
            camera_name = cam.name
            source_val = cam.source_path
            polygon_roi = cam.get_roi_points()

    if source_val is None or str(source_val) in ("0", "webcam"):
        # On headless cloud servers (e.g. Render / Linux VM without USB webcams), default to demo video
        if os.name != "nt" and not os.path.exists("/dev/video0"):
            source_val = "pp2.mp4"
            camera_name = "Demo Video (pp2.mp4)"
        else:
            source_val = 0  # Default webcam

    # Start detector
    detector.start(
        source=source_val,
        camera_name=camera_name,
        camera_id=camera_id or 1,
        roi=polygon_roi,
    )

    return jsonify({
        "status": "success",
        "message": f"Detection started on {camera_name}",
        "source": str(source_val),
    })


@video_bp.route("/stop_detection", methods=["GET", "POST"])
def stop_detection():
    """Stops detection and releases camera hardware immediately."""
    detector.stop()
    return jsonify({
        "status": "success",
        "message": "Detection halted successfully.",
    })


@video_bp.route("/upload_video", methods=["POST"])
@login_required
def upload_video():
    if current_app.config["DEMO_MODE"] or not current_user.is_admin:
        return jsonify({"status": "error", "message": "Admin authorization required to upload video files."}), 403
    if "video" not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400

    file = request.files["video"]
    if not file.filename:
        return jsonify({"status": "error", "message": "No file selected"}), 400

    if allowed_file(file.filename):
        filename = secure_filename(file.filename)
        upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
        upload_folder.mkdir(parents=True, exist_ok=True)
        save_path = upload_folder / filename
        file.save(str(save_path))

        # Register camera in DB
        cam_name = request.form.get("camera_name", f"Video: {filename}")
        cam = Camera(
            name=cam_name,
            source_type="file",
            source_path=str(save_path),
            is_active=True,
        )
        db.session.add(cam)
        db.session.commit()

        # If user chose to immediately run:
        auto_start = request.form.get("auto_start", "true").lower() in ("true", "1")
        if auto_start:
            detector.start(
                source=str(save_path),
                camera_name=cam.name,
                camera_id=cam.id,
            )

        return jsonify({
            "status": "success",
            "message": f"File '{filename}' uploaded successfully.",
            "camera_id": cam.id,
            "filename": filename,
        })

    return jsonify({"status": "error", "message": "Invalid file format"}), 400
