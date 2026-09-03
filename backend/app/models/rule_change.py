"""The record of changing a plan's own rule mid-study. Design section 9.

T07-C09 through C12 ask for something narrower than "write down that you
changed your mind": the record has to sit after the day-2 entry and before the
day-3 one, and it has to point at the day-1 and day-2 records *exactly*.

That last word is why the citations are a table with foreign keys rather than a
JSON array of ids on the change. A string in a JSON column can name an
execution that was deleted, or one belonging to somebody else, and the database
will store it happily; "exactly" then means "exactly, as of whenever anyone last
looked". Two foreign keys and a couple of constraints make it a property of the
data instead of a property of the last check.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.plan import new_uuid, utc_now


class PlanRuleChange(db.Model):
    __tablename__ = "plan_rule_changes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Recorded, not derived from created_at, because C10 asks for the time the
    # rule changed. Those are the same moment when the entry is written as it
    # happens, and the service refuses a value that is not -- but the column
    # says which of the two the criterion is about.
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)  # C11
    rule_before: Mapped[str] = mapped_column(Text, nullable=False)
    rule_after: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    citations: Mapped[list["PlanRuleChangeCitation"]] = relationship(
        back_populates="rule_change",
        cascade="all, delete-orphan",
        order_by="PlanRuleChangeCitation.day_number",
    )


class PlanRuleChangeCitation(db.Model):
    """One cited execution record, and which study day it is.

    `execution_id` is NO ACTION rather than RESTRICT, and the difference is not
    cosmetic. Both refuse to let a cited execution be deleted on its own, which
    is the protection C12 wants. But RESTRICT is checked the instant the row
    goes, and deleting an account (C134) cascades down two paths at once --
    plans to tasks to executions, and plans to rule changes to citations -- with
    no guaranteed order between them. RESTRICT would abort the account delete
    roughly half the time, depending on which path PostgreSQL walked first. NO
    ACTION is checked at the end of the statement, by which point the citation
    is gone too, so the account delete completes and the standalone delete is
    still refused.
    """

    __tablename__ = "plan_rule_change_citations"
    __table_args__ = (
        # One citation per study day: no two rows claiming to be day 1.
        PrimaryKeyConstraint("rule_change_id", "day_number"),
        # And no one execution standing in for both days.
        UniqueConstraint("rule_change_id", "execution_id", name="uq_rule_change_citation_execution"),
        CheckConstraint("day_number IN (1, 2)", name="ck_rule_change_citation_day"),
    )

    rule_change_id: Mapped[str] = mapped_column(
        ForeignKey("plan_rule_changes.id", ondelete="CASCADE"), nullable=False
    )
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_id: Mapped[str] = mapped_column(
        ForeignKey("execution_logs.id", ondelete="NO ACTION"), nullable=False, index=True
    )

    rule_change: Mapped[PlanRuleChange] = relationship(back_populates="citations")
