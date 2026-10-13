from typing import Any, Optional, ClassVar
import json
from datetime import datetime, timezone
from app.extensions import db


class Camera(db.Model):
    """Camera source configuration with support for ROI restricted polygons."""
    __tablename__ = "cameras"
    __allow_unmapped__ = True

    query: ClassVar[Any]

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    source_type = db.Column(db.String(20), default="file", nullable=False)  # 'webcam', 'file', 'rtsp'
    source_path = db.Column(db.String(255), nullable=False)  # '0', file path, or rtsp://...
    is_active = db.Column(db.Boolean, default=True)
    polygon_roi = db.Column(db.Text, nullable=True)  # JSON-encoded array of [x, y] coordinates
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __init__(
        self,
        name: str = "",
        source_type: str = "file",
        source_path: str = "0",
        is_active: bool = True,
        polygon_roi: Optional[str] = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.name = name
        self.source_type = source_type
        self.source_path = source_path
        self.is_active = is_active
        self.polygon_roi = polygon_roi

    def get_roi_points(self):
        """Returns ROI coordinates as a list of [x, y] pairs, or None if not set."""
        if not self.polygon_roi:
            return None
        try:
            return json.loads(self.polygon_roi)
        except Exception:
            return None

    def set_roi_points(self, points):
        """Encodes list of [x, y] points as JSON."""
        self.polygon_roi = json.dumps(points) if points else None

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "is_active": self.is_active,
            "polygon_roi": self.get_roi_points(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def sync_connected_cameras(cls, max_tested=4):
        """
        Scans system for physically connected webcam devices and indices.
        Uses DirectShow filter graph (pygrabber) on Windows for instant, non-blocking
        device enumeration with friendly hardware names, with OpenCV fallback.
        """
        import os

        detected = []  # list of tuples (index_int, friendly_name)

        # 1. Try DirectShow enumeration (Instant, no device lock, gets real hardware name)
        if os.name == 'nt':
            try:
                import importlib
                dshow_graph = importlib.import_module("pygrabber.dshow_graph")
                graph = dshow_graph.FilterGraph()
                dev_names = graph.get_input_devices()
                for idx, name in enumerate(dev_names):
                    detected.append((idx, name))
            except Exception:
                pass

        # 2. If DirectShow didn't detect devices, probe with OpenCV
        if not detected:
            import cv2
            for idx in range(max_tested):
                try:
                    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY)
                    if cap.isOpened():
                        detected.append((idx, f"Webcam {idx}"))
                        cap.release()
                except Exception:
                    pass

        # 3. Always register at least index 0 and index 1 so any attached webcam is instantly selectable
        known_indices = {idx for idx, _ in detected}
        for fallback_idx in [0, 1]:
            if fallback_idx not in known_indices:
                fallback_name = "External USB Webcam (Camera 1)" if fallback_idx == 1 else "Primary Webcam (Camera 0)"
                detected.append((fallback_idx, fallback_name))

        # 4. Sync into database
        for idx, dev_name in detected:
            idx_str = str(idx)
            cam = cls.query.filter_by(source_type="webcam", source_path=idx_str).first()
            display_name = dev_name if dev_name else f"Webcam {idx}"
            if f"Camera {idx}" not in display_name:
                display_name = f"{display_name} (Camera {idx})"

            if cam:
                cam.name = display_name
            else:
                new_cam = cls(
                    name=display_name,
                    source_type="webcam",
                    source_path=idx_str,
                    is_active=False
                )
                db.session.add(new_cam)

        # 5. Ensure demo video option exists
        demo_cam = cls.query.filter_by(source_type="file", source_path="pp2.mp4").first()
        if not demo_cam:
            demo_cam = cls(
                name="Zone 1 - Demo Video Stream",
                source_type="file",
                source_path="pp2.mp4",
                is_active=False
            )
            db.session.add(demo_cam)

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

        return cls.query.order_by(cls.id.asc()).all()

    def __repr__(self):
        return f"<Camera #{self.id} {self.name} ({self.source_type}: {self.source_path})>"
