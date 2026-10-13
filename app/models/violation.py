from typing import Any, Optional, ClassVar
from datetime import datetime, timezone
from app.extensions import db


class Violation(db.Model):
    """Logs individual PPE safety violations with metadata and snapshot path."""
    __tablename__ = "violations"
    __allow_unmapped__ = True

    query: ClassVar[Any]

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    track_id = db.Column(db.Integer, nullable=True)
    violation_type = db.Column(db.String(64), nullable=False, index=True)  # e.g., 'Hardhat', 'Safety Vest', 'Mask'
    camera = db.Column(db.String(100), default="Camera 1", nullable=False)
    snapshot_path = db.Column(db.String(255), nullable=True)
    confidence = db.Column(db.Float, default=0.0)
    acknowledged = db.Column(db.Boolean, default=False)

    def __init__(
        self,
        timestamp: Optional[datetime] = None,
        track_id: Optional[int] = None,
        violation_type: str = "",
        camera: str = "Camera 1",
        snapshot_path: Optional[str] = None,
        confidence: float = 0.0,
        acknowledged: bool = False,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.track_id = track_id
        self.violation_type = violation_type
        self.camera = camera
        self.snapshot_path = snapshot_path
        self.confidence = confidence
        self.acknowledged = acknowledged

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S") if self.timestamp else None,
            "track_id": self.track_id,
            "violation_type": self.violation_type,
            "camera": self.camera,
            "snapshot_path": self.snapshot_path,
            "confidence": round(self.confidence, 2) if self.confidence else 0.0,
            "acknowledged": self.acknowledged,
        }

    def __repr__(self):
        return f"<Violation {self.violation_type} [Track {self.track_id}] @ {self.timestamp}>"
