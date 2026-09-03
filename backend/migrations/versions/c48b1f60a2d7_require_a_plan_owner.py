"""require a plan owner

Revision ID: c48b1f60a2d7
Revises: a1c7d9e40b52
Create Date: 2026-09-04

Step 10 of docs/T07-ARCHITECTURE.md section 13, and the second half of the
ownership root: `plans.user_id` stops being nullable.

**This migration must not ship in the same deploy as the claim.**
`deploy/start.sh` runs `flask db upgrade` before BOOT_TASK, so shipping both
together would evaluate this NOT NULL before claim_t06_data had given the T06
rows an owner, and it would fail on every one of them -- taking the deploy with
it. The order is fixed in the design's section 0 and the runbook:

    deploy A   nullable column + claim_t06_data --apply
    check      the boot log says NULL=0
    deploy B   this migration, BOOT_TASK back to none

The upgrade refuses rather than trusting that sequence was followed. A NOT NULL
applied while rows are still unowned is not a failed migration on its own -- on
PostgreSQL the ALTER simply errors, but the message points at a constraint
rather than at the claim that never ran, and the next person reads it as a
schema problem. Counting first turns it into a sentence that says what to do.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c48b1f60a2d7'
down_revision = 'a1c7d9e40b52'
branch_labels = None
depends_on = None


def upgrade():
    orphans = op.get_bind().execute(
        sa.text("SELECT count(*) FROM plans WHERE user_id IS NULL")
    ).scalar_one()
    if orphans:
        raise RuntimeError(
            f"{orphans} plans still have no owner, so user_id cannot become NOT NULL. "
            "Run claim_t06_data --apply first and check the boot log says NULL=0; "
            "this migration belongs to the deploy after that one."
        )

    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.String(length=36), nullable=False)


def downgrade():
    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.String(length=36), nullable=True)
