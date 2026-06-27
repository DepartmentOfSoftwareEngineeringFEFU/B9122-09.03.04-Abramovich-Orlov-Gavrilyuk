"""
Database models for User and Auth
"""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Boolean, DateTime, Date
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    """User DB Model"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    email: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    first_name: Mapped[Optional[str]] = mapped_column(String(50), default="")
    last_name: Mapped[Optional[str]] = mapped_column(String(50), default="")
    display_name: Mapped[Optional[str]] = mapped_column(String(100), default="")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    can_approve_users: Mapped[bool] = mapped_column(Boolean, default=False)

    date_joined: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<User {self.username}>"
