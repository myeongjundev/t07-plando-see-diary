from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def new_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Plan(db.Model):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_plans_date_order"),
        CheckConstraint("estimated_minutes >= 0", name="ck_plans_estimated_minutes"),
        CheckConstraint("priority IN ('high', 'medium', 'low')", name="ck_plans_priority"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    # The single root of ownership: tasks, executions, reflections and revisions
    # decide who owns them by joining through here rather than carrying a copy,
    # so there is never a second answer to disagree with (design section 2).
    #
    # Nullable for now. The T06 rows predate accounts, and NOT NULL is applied
    # in a later deploy once claim_t06_data has given them an owner -- the
    # migration and the claim cannot ride the same boot.
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    success_criterion: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    carried_improvement: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    revisions: Mapped[list["PlanRevision"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="PlanRevision.revision_number"
    )


class PlanRevision(db.Model):
    __tablename__ = "plan_revisions"
    __table_args__ = (
        UniqueConstraint("plan_id", "revision_number", name="uq_plan_revision_number"),
        CheckConstraint("revision_number >= 1", name="ck_plan_revision_number"),
        CheckConstraint("estimated_minutes >= 0", name="ck_plan_revision_estimated_minutes"),
    )

    revision_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    success_criterion: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    carried_improvement: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    replaced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    plan: Mapped[Plan] = relationship(back_populates="revisions")

