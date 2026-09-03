"""Accounts, refresh sessions, login attempts, security events.

Design: docs/T07-ARCHITECTURE.md section 2.

Two deliberate departures from the SQL sketched there, both so the same schema
runs on the SQLite the tests use and the PostgreSQL that is deployed:

- `uuid` columns are `String(36)`, matching every existing table in this app.
- `email` is a plain unique `String` rather than `citext`. Addresses are
  lower-cased on the way in (`normalize_email`), so a plain unique index gives
  the same guarantee, and it is the write path -- not the column type -- that
  has to be right either way. citext does not exist in SQLite, and a uniqueness
  rule that only holds in production is one nobody can test.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.extensions import db
from app.models.plan import new_uuid, utc_now

# SQLite has no BIGSERIAL: an autoincrementing key there must be INTEGER.
BigIntPk = BigInteger().with_variant(Integer, "sqlite")
# JSONB where it exists, JSON where it does not.
JsonColumn = JSON().with_variant(JSONB, "postgresql")

# Long enough for the addresses RFC 5321 permits, so the column is never the
# thing that rejects a legitimate one.
EMAIL_MAX = 320
# Hex SHA-256.
DIGEST_LEN = 64


def normalize_email(email: str) -> str:
    """The one place an address becomes its stored form.

    Uniqueness (T07-C98) is only as good as this being the single write path;
    two spellings of one address stored differently is the same bug as no
    unique index at all.
    """
    return email.strip().lower()


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    # Stored lower-cased. See normalize_email.
    email: Mapped[str] = mapped_column(String(EMAIL_MAX), nullable=False, unique=True)
    # The argon2id encoded string, which carries its own salt and parameters.
    # There is no plaintext, hint, or recovery-question column, and there is not
    # meant to be one (T07-C103).
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Sessions issued before this instant are not honoured (T07-C114).
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class RefreshSession(db.Model):
    """One row per live refresh token; the access JWT's `sid` names one of these.

    Rotation writes a new row and revokes the old one, so a family is a chain
    linked by `replaced_by_id`. Keeping the spent rows is what makes reuse
    detectable: a token whose row is already revoked was replayed.
    """

    __tablename__ = "refresh_sessions"
    __table_args__ = (
        CheckConstraint(
            "revoked_reason IS NULL OR revoked_reason IN "
            "('logout', 'rotated', 'reuse', 'password_change', 'account_delete')",
            name="ck_refresh_sessions_revoked_reason",
        ),
        CheckConstraint(
            "(revoked_at IS NULL) = (revoked_reason IS NULL)",
            name="ck_refresh_sessions_revoked_pair",
        ),
        Index("ix_refresh_sessions_family_id", "family_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # One login, one family. Reuse detection revokes the family, not the row.
    family_id: Mapped[str] = mapped_column(String(36), nullable=False, default=new_uuid)
    # The token itself is never stored. A leaked table must not be a set of
    # working credentials. SHA-256 rather than argon2 because a 256-bit random
    # token is not a dictionary-attack target.
    token_sha256: Mapped[str] = mapped_column(String(DIGEST_LEN), nullable=False, unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    # Idle expiry reads this. Written only on rotation, so an authenticated
    # request costs a read and no write. Section 2 of the design.
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    # Absolute expiry. Inherited unchanged by every rotation in the family --
    # if rotation extended it, it would not be absolute.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)
    replaced_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("refresh_sessions.id", ondelete="SET NULL"), nullable=True
    )


class LoginAttempt(db.Model):
    """Every login attempt, so throttling survives the instance restarting.

    Render Free sleeps after fifteen minutes and comes back a new process. A
    counter in memory resets on every wake, which is not a slower attacker but
    the appearance of one.

    Attempts against addresses that do not exist are recorded too. Counting only
    real accounts would make "this address never locks" a way to enumerate them,
    which is the leak T07-C99 exists to close.
    """

    __tablename__ = "login_attempts"
    __table_args__ = (
        CheckConstraint(
            "result IN ('failure', 'blocked', 'success')",
            name="ck_login_attempts_result",
        ),
        Index("ix_login_attempts_email_time", "email_normalized", "attempted_at"),
        Index("ix_login_attempts_ip_time", "ip_hash", "attempted_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    email_normalized: Mapped[str | None] = mapped_column(String(EMAIL_MAX), nullable=True)
    # HMAC-SHA-256(IP_HASH_SECRET, canonical_ip). The raw address is not stored:
    # recognising a repeat visitor does not require being able to name them, and
    # a leaked table should not be a visitor log.
    ip_hash: Mapped[str] = mapped_column(String(DIGEST_LEN), nullable=False)
    # Only 'failure' counts toward a lock. 'blocked' records that a request was
    # turned away while locked, which would otherwise extend the lock forever.
    result: Mapped[str] = mapped_column(String(10), nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class SecurityEvent(db.Model):
    """The audit trail T06 did not have.

    `user_id` is SET NULL on account deletion rather than cascading. T07-C134
    wants a deleted account's data gone; an audit log that deletes itself with
    the account is no use after a breach. Cutting the column that names the
    person satisfies both -- provided nothing in `detail` names them either,
    which is a rule about what callers put here, not one the schema can enforce.
    """

    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Not a foreign key: the point of the row often survives the session it
    # describes, and a cascade would delete the record of a revocation.
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(DIGEST_LEN), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    # Column is "metadata"; the attribute cannot be, because SQLAlchemy's
    # declarative base already owns that name.
    detail: Mapped[dict] = mapped_column("metadata", JsonColumn, nullable=False, default=dict)


Index("ix_security_events_created_at", SecurityEvent.created_at.desc())
Index("ix_security_events_type_created_at", SecurityEvent.event_type, SecurityEvent.created_at.desc())
