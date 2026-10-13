from datetime import datetime, timezone
from typing import Any, Optional, ClassVar
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


class User(UserMixin, db.Model):
    """User account model with role-based access control (admin / viewer)."""
    __tablename__ = "users"
    __allow_unmapped__ = True

    query: ClassVar[Any]

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    full_name = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    site_name = db.Column(db.String(120), nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default="user", nullable=False)  # 'admin' or 'user'
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __init__(
        self,
        username: Optional[str] = None,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        phone: Optional[str] = None,
        site_name: Optional[str] = None,
        password: Optional[str] = None,
        password_hash: Optional[str] = None,
        role: str = "user",
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.username = username
        self.email = email
        self.full_name = full_name
        self.phone = phone
        self.site_name = site_name
        self.role = role or "user"
        if password_hash:
            self.password_hash = password_hash
        elif password:
            self.set_password(password)

    def set_password(self, password: str):
        """Hashes and sets the user's password."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """Verifies candidate password against stored hash."""
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        """Returns True if the user has administrator privileges."""
        return self.role == "admin"

    @property
    def is_standard_user(self) -> bool:
        """Returns True if the user is a standard monitoring user."""
        return self.role in ("user", "viewer")

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "phone": self.phone,
            "site_name": self.site_name,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"
