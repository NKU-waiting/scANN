"""User 数据模型。"""

import hashlib
from datetime import UTC, datetime

from werkzeug.security import check_password_hash, generate_password_hash

from app.core.extensions import db


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = {"sqlite_autoincrement": True}

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(16), nullable=False, default="user")
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def token_version(self) -> str:
        """Return an opaque login epoch that changes for every password hash."""
        return hashlib.sha256(self.password_hash.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at.isoformat(),
        }
