"""Opening, reading and revoking login sessions. Design section 4.

A login creates one `refresh_sessions` row and a family id. Rotation (step 5)
adds rows to that family; revocation marks them. The access token names a row
through its `sid` claim, so this module is what decides, on every request,
whether a signed token still means anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.extensions import db
from app.models import RefreshSession, User
from app.security.tokens import (
    absolute_ttl,
    idle_ttl,
    issue_access_token,
    new_csrf_token,
    new_refresh_token,
    token_digest,
)

# Written to refresh_sessions.revoked_reason. The check constraint holds the
# same list, so a reason invented here fails at the database rather than
# quietly becoming a value nothing knows how to read.
LOGOUT = "logout"
ROTATED = "rotated"
REUSE = "reuse"
PASSWORD_CHANGE = "password_change"
ACCOUNT_DELETE = "account_delete"


@dataclass(frozen=True)
class IssuedSession:
    """What login hands to the caller. The plaintext tokens exist only here."""

    session: RefreshSession
    access_token: str
    refresh_token: str
    csrf_token: str
    access_expires_at: datetime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; PostgreSQL does not.

    Comparing a naive value to an aware one raises, so an expiry check that
    worked in production would crash in the tests, or the reverse. Normalising
    on the way out keeps one code path for both.
    """
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def open_session(user: User, *, now: datetime | None = None) -> IssuedSession:
    """Start a new family for this login."""
    now = now or utc_now()
    refresh_token = new_refresh_token()
    csrf_token = new_csrf_token()
    # The CSRF value is not stored, in plaintext or digest. Design section 5:
    # binding it to a row buys nothing that __Host- and the Public Suffix List
    # do not already give, and costs three failure modes -- bootstrapping it for
    # signup and login, ordering the check on refresh, and racing an in-flight
    # request against a rotation that replaces it.
    session = RefreshSession(
        user_id=user.id,
        token_sha256=token_digest(refresh_token),
        issued_at=now,
        last_used_at=now,
        expires_at=now + absolute_ttl(),
    )
    # family_id defaults to a fresh uuid, and this row is the head of it.
    db.session.add(session)
    db.session.flush()
    access_token, claims = issue_access_token(user.id, session.id, now=now)
    db.session.commit()
    return IssuedSession(
        session=session,
        access_token=access_token,
        refresh_token=refresh_token,
        csrf_token=csrf_token,
        access_expires_at=claims.expires_at,
    )


def live_session(session_id: str, *, now: datetime | None = None) -> RefreshSession | None:
    """The session named by an access token's `sid`, if it is still usable.

    This is the read that costs the hybrid design its statelessness, and the
    reason T07-C114 holds: a token signed before logout still verifies, and
    still gets nothing, because the row it names is revoked.

    Idle is measured from `last_used_at`, which only rotation writes. An
    authenticated request therefore costs one indexed read and no write, at the
    price of the idle clock advancing in ten-minute steps -- which is ample
    resolution for a two-day limit.
    """
    now = now or utc_now()
    session = db.session.get(RefreshSession, session_id)
    if session is None:
        return None
    if _aware(session.revoked_at) is not None:
        return None
    if _aware(session.expires_at) <= now:
        return None
    if _aware(session.last_used_at) + idle_ttl() <= now:
        return None
    return session


def revoke(session: RefreshSession, reason: str, *, now: datetime | None = None) -> None:
    """Mark one session dead. Already-dead sessions keep their original reason.

    Overwriting would lose why it first ended -- and 'rotated' turning into
    'logout' after the fact is exactly the history reuse detection reads.
    """
    if session.revoked_at is not None:
        return
    session.revoked_at = now or utc_now()
    session.revoked_reason = reason


def revoke_family(family_id: str, reason: str, *, now: datetime | None = None) -> int:
    """Kill every session descended from one login. Returns how many died."""
    now = now or utc_now()
    rows = db.session.scalars(
        db.select(RefreshSession).where(
            RefreshSession.family_id == family_id,
            RefreshSession.revoked_at.is_(None),
        )
    ).all()
    for row in rows:
        revoke(row, reason, now=now)
    return len(rows)


def revoke_all_for_user(user_id: str, reason: str, *, now: datetime | None = None) -> int:
    """Every live session for one account. Used by password change (T07-C114)."""
    now = now or utc_now()
    rows = db.session.scalars(
        db.select(RefreshSession).where(
            RefreshSession.user_id == user_id,
            RefreshSession.revoked_at.is_(None),
        )
    ).all()
    for row in rows:
        revoke(row, reason, now=now)
    return len(rows)
