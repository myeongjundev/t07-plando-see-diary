"""add accounts, sessions, throttling, audit, and plan ownership

Revision ID: a1c7d9e40b52
Revises: b84587642a1b
Create Date: 2026-09-03

Step 1 of docs/T07-ARCHITECTURE.md section 13.

`plans.user_id` arrives nullable and stays that way. The rows this database
already holds have no owner yet, and the claim that gives them one runs from
`deploy/start.sh` -- which runs `flask db upgrade` first. A NOT NULL in this
migration would therefore be evaluated before the claim it depends on and fail
on every existing row. Tightening it is a separate migration in a later deploy.

The two reflections foreign keys are rebuilt only to add delete actions. As
written they have none, so PostgreSQL defaults them to NO ACTION and refuses the
users -> plans cascade that deleting an account needs (T07-C134); the delete
fails halfway down instead of doing nothing, which is the worse of the two.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision = 'a1c7d9e40b52'
down_revision = 'b84587642a1b'
branch_labels = None
depends_on = None

# SQLite cannot autoincrement a BIGINT; it wants INTEGER PRIMARY KEY.
BIG_ID = sa.BigInteger().with_variant(sa.Integer, 'sqlite')
JSON_COLUMN = sa.JSON().with_variant(JSONB, 'postgresql')


def _reflection_foreign_key_names(foreign_keys):
    """Return the deployed names for the two legacy reflection FKs.

    The T06 tables were created before this repository adopted an Alembic
    naming convention. PostgreSQL therefore assigned names such as
    ``reflections_plan_id_fkey`` while SQLite reports those constraints as
    unnamed. The migration must drop the names that are actually present in
    PostgreSQL and retain the convention fallback that batch mode needs for
    SQLite.
    """
    fallbacks = {
        ('plan_id',): 'fk_reflections_plan_id_plans',
        ('next_plan_id',): 'fk_reflections_next_plan_id_plans',
    }
    names = {}
    for foreign_key in foreign_keys:
        columns = tuple(foreign_key.get('constrained_columns') or ())
        if columns in fallbacks:
            names[columns] = foreign_key.get('name') or fallbacks[columns]

    missing = [columns[0] for columns in fallbacks if columns not in names]
    if missing:
        raise RuntimeError(
            'Cannot rebuild reflections foreign keys; missing columns: '
            + ', '.join(sorted(missing))
        )
    return names


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), nullable=False),
        # Stored lower-cased by the application; the unique index is on the
        # normalized form, which is what makes T07-C98 hold.
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email', name='uq_users_email'),
    )

    op.create_table(
        'refresh_sessions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('family_id', sa.String(length=36), nullable=False),
        sa.Column('token_sha256', sa.String(length=64), nullable=False),
        sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_reason', sa.String(length=20), nullable=True),
        sa.Column('replaced_by_id', sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            "revoked_reason IS NULL OR revoked_reason IN "
            "('logout', 'rotated', 'reuse', 'password_change', 'account_delete')",
            name='ck_refresh_sessions_revoked_reason',
        ),
        # A revoked row without a reason loses the evidence of why, and a reason
        # without a timestamp claims a revocation that never happened.
        sa.CheckConstraint(
            '(revoked_at IS NULL) = (revoked_reason IS NULL)',
            name='ck_refresh_sessions_revoked_pair',
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['replaced_by_id'], ['refresh_sessions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_sha256', name='uq_refresh_sessions_token_sha256'),
    )
    with op.batch_alter_table('refresh_sessions', schema=None) as batch_op:
        batch_op.create_index('ix_refresh_sessions_family_id', ['family_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_refresh_sessions_user_id'), ['user_id'], unique=False)

    op.create_table(
        'login_attempts',
        sa.Column('id', BIG_ID, autoincrement=True, nullable=False),
        # Nullable and unconstrained on purpose: attempts against addresses that
        # do not exist are counted too, so "never locks" cannot be used to tell
        # which addresses are real.
        sa.Column('email_normalized', sa.String(length=320), nullable=True),
        sa.Column('ip_hash', sa.String(length=64), nullable=False),
        sa.Column('result', sa.String(length=10), nullable=False),
        sa.Column('attempted_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("result IN ('failure', 'blocked', 'success')", name='ck_login_attempts_result'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('login_attempts', schema=None) as batch_op:
        batch_op.create_index('ix_login_attempts_email_time', ['email_normalized', 'attempted_at'], unique=False)
        batch_op.create_index('ix_login_attempts_ip_time', ['ip_hash', 'attempted_at'], unique=False)

    op.create_table(
        'security_events',
        sa.Column('id', BIG_ID, autoincrement=True, nullable=False),
        sa.Column('event_type', sa.String(length=40), nullable=False),
        sa.Column('result', sa.String(length=20), nullable=False),
        # SET NULL, not CASCADE: the audit trail has to outlive the account it
        # describes, or it is no use after the breach it exists to explain.
        sa.Column('user_id', sa.String(length=36), nullable=True),
        sa.Column('session_id', sa.String(length=36), nullable=True),
        sa.Column('ip_hash', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('metadata', JSON_COLUMN, nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('security_events', schema=None) as batch_op:
        batch_op.create_index('ix_security_events_created_at', [sa.text('created_at DESC')], unique=False)
        batch_op.create_index(
            'ix_security_events_type_created_at', ['event_type', sa.text('created_at DESC')], unique=False
        )

    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.String(length=36), nullable=True))
        batch_op.create_index(batch_op.f('ix_plans_user_id'), ['user_id'], unique=False)
        batch_op.create_foreign_key('fk_plans_user_id_users', 'users', ['user_id'], ['id'], ondelete='CASCADE')

    # Rebuild the reflections foreign keys with delete actions. PostgreSQL
    # assigned deployment-specific names to T06's formerly unnamed keys, so
    # inspect first rather than assuming the later naming convention already
    # applied to the existing table. SQLite still uses the convention fallback
    # while batch mode recreates the table.
    reflection_foreign_keys = sa.inspect(op.get_bind()).get_foreign_keys('reflections')
    reflection_fk_names = _reflection_foreign_key_names(reflection_foreign_keys)
    with op.batch_alter_table('reflections', schema=None, naming_convention={
        'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
    }) as batch_op:
        batch_op.drop_constraint(reflection_fk_names[('plan_id',)], type_='foreignkey')
        batch_op.drop_constraint(reflection_fk_names[('next_plan_id',)], type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_reflections_plan_id_plans', 'plans', ['plan_id'], ['id'], ondelete='CASCADE'
        )
        batch_op.create_foreign_key(
            'fk_reflections_next_plan_id_plans', 'plans', ['next_plan_id'], ['id'], ondelete='SET NULL'
        )


def downgrade():
    with op.batch_alter_table('reflections', schema=None) as batch_op:
        batch_op.drop_constraint('fk_reflections_next_plan_id_plans', type_='foreignkey')
        batch_op.drop_constraint('fk_reflections_plan_id_plans', type_='foreignkey')
        batch_op.create_foreign_key('fk_reflections_plan_id_plans', 'plans', ['plan_id'], ['id'])
        batch_op.create_foreign_key('fk_reflections_next_plan_id_plans', 'plans', ['next_plan_id'], ['id'])

    with op.batch_alter_table('plans', schema=None) as batch_op:
        batch_op.drop_constraint('fk_plans_user_id_users', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_plans_user_id'))
        batch_op.drop_column('user_id')

    op.drop_table('security_events')
    op.drop_table('login_attempts')
    op.drop_table('refresh_sessions')
    op.drop_table('users')
