from datetime import datetime
from app.extensions import db


class Violation(db.Model):
    """Logs individual PPE safety violations with metadata and snapshot path."""
    __tablename__ = "violations"

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    track_id = db.Column(db.Integer, nullable=True)
    violation_type = db.Column(db.String(64), nullable=False, index=True)  # e.g., 'Hardhat', 'Safety Vest', 'Mask'
    camera = db.Column(db.String(100), default="Camera 1", nullable=False)
    snapshot_path = db.Column(db.String(255), nullable=True)
    confidence = db.Column(db.Float, default=0.0)
    acknowledged = db.Column(db.Boolean, default=False)

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
