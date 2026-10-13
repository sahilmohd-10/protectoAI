from typing import Any, ClassVar
from app.extensions import db


class DailyStat(db.Model):
    """Aggregated daily PPE compliance statistics."""
    __tablename__ = "daily_stats"
    __allow_unmapped__ = True

    query: ClassVar[Any]

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), unique=True, nullable=False, index=True)  # YYYY-MM-DD
    hardhat_not = db.Column(db.Integer, default=0, nullable=False)
    vest_not = db.Column(db.Integer, default=0, nullable=False)
    mask_not = db.Column(db.Integer, default=0, nullable=False)
    gloves_not = db.Column(db.Integer, default=0, nullable=False)
    total_workers = db.Column(db.Integer, default=0, nullable=False)
    compliance_rate = db.Column(db.Float, default=100.0, nullable=False)  # percentage 0.0 - 100.0

    def __init__(
        self,
        date: str = "",
        hardhat_not: int = 0,
        vest_not: int = 0,
        mask_not: int = 0,
        gloves_not: int = 0,
        total_workers: int = 0,
        compliance_rate: float = 100.0,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.date = date
        self.hardhat_not = hardhat_not
        self.vest_not = vest_not
        self.mask_not = mask_not
        self.gloves_not = gloves_not
        self.total_workers = total_workers
        self.compliance_rate = compliance_rate

    @property
    def total_violations(self) -> int:
        return self.hardhat_not + self.vest_not + self.mask_not + self.gloves_not

    def to_dict(self):
        return {
            "id": self.id,
            "date": self.date,
            "hardhat_not": self.hardhat_not,
            "vest_not": self.vest_not,
            "mask_not": self.mask_not,
            "gloves_not": self.gloves_not,
            "total_violations": self.total_violations,
            "total_workers": self.total_workers,
            "compliance_rate": round(self.compliance_rate, 1),
        }

    def __repr__(self):
        return f"<DailyStat {self.date}: {self.total_violations} violations ({self.compliance_rate}%)>"
