"""add plan rule changes and their citations

Revision ID: d5a3e91c7f20
Revises: c48b1f60a2d7
Create Date: 2026-09-04

Step 10 of docs/T07-ARCHITECTURE.md section 13: the tables behind T07-C09 to
C12. Additive -- two new tables, nothing existing is touched -- so it can ship
in any deploy, and it must ship in the one that starts the five-day study.
Without it the change cannot be recorded on the evening of day 2, and the five
days start again.

`plan_rule_change_citations.execution_id` is NO ACTION rather than RESTRICT on
purpose; the reason is in app/models/rule_change.py, and it is about C134's
account delete, which cascades down two paths at once with no order between
them.
"""
import sqlalchemy as sa
from alembic import op

revision = "d5a3e91c7f20"
down_revision = "c48b1f60a2d7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "plan_rule_changes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("rule_before", sa.Text(), nullable=False),
        sa.Column("rule_after", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_plan_rule_changes_plan_id"), "plan_rule_changes", ["plan_id"], unique=False
    )

    op.create_table(
        "plan_rule_change_citations",
        sa.Column("rule_change_id", sa.String(length=36), nullable=False),
        sa.Column("day_number", sa.Integer(), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.CheckConstraint("day_number IN (1, 2)", name="ck_rule_change_citation_day"),
        sa.ForeignKeyConstraint(["rule_change_id"], ["plan_rule_changes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["execution_id"], ["execution_logs.id"], ondelete="NO ACTION"),
        sa.PrimaryKeyConstraint("rule_change_id", "day_number"),
        sa.UniqueConstraint(
            "rule_change_id", "execution_id", name="uq_rule_change_citation_execution"
        ),
    )
    op.create_index(
        op.f("ix_plan_rule_change_citations_execution_id"),
        "plan_rule_change_citations",
        ["execution_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_plan_rule_change_citations_execution_id"),
        table_name="plan_rule_change_citations",
    )
    op.drop_table("plan_rule_change_citations")
    op.drop_index(op.f("ix_plan_rule_changes_plan_id"), table_name="plan_rule_changes")
    op.drop_table("plan_rule_changes")
