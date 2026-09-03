from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.models.plan import new_uuid, utc_now


class Reflection(db.Model):
    __tablename__ = "reflections"
    __table_args__ = (CheckConstraint("period_end >= period_start", name="ck_reflection_period"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    # Both foreign keys need an explicit delete action or PostgreSQL refuses the
    # users -> plans cascade that T07-C134 depends on, and deleting an account
    # fails on a RESTRICT halfway down. The reflection belongs to its plan, so it
    # goes with it; the forward link to a successor plan is only a pointer, so it
    # is cleared rather than dragging the reflection along.
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    improvement: Mapped[str] = mapped_column(Text)
    next_plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
