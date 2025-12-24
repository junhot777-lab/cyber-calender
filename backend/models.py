from sqlalchemy import String, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(10), primary_key=True)  # hj/sk/jh
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str] = mapped_column(String(30), nullable=False)
    passcode_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    events = relationship("Event", back_populates="owner")

class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid str
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    start_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    owner_user_id: Mapped[str] = mapped_column(String(10), ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="events")

    note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
