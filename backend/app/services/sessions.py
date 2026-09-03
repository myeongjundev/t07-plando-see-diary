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


class RefreshRejected(Exception):
    """The refresh token was unknown, spent, expired, or idled out."""

    def __init__(self, reason: str, *, reused: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        # True when a token that had already been rotated came back. Step 14
        # turns this into family revocation and a security event; for now the
        # caller refuses the request and the flag is the seam that says where.
        self.reused = reused


def refresh_is_live(refresh_token: str, *, now: datetime | None = None) -> bool:
    """Whether this refresh token would rotate, without spending it.

    Lets the endpoint answer "no such session" before it answers "no CSRF
    header", so the two refusals cannot be used to probe which is which. Nothing
    is decided on this read -- rotate_session re-checks everything under a lock.
    """
    now = now or utc_now()
    session = db.session.scalar(
        db.select(RefreshSession).where(RefreshSession.token_sha256 == token_digest(refresh_token))
    )
    if session is None or _aware(session.revoked_at) is not None:
        return False
    if _aware(session.expires_at) <= now:
        return False
    return _aware(session.last_used_at) + idle_ttl() > now


def rotate_session(refresh_token: str, *, now: datetime | None = None) -> IssuedSession:
    """Spend one refresh token and issue its successor. One transaction.

    The locking is the whole point. Two requests that read row A before either
    writes will both find it live and both mint a successor: the family forks,
    and the loser's token is a working credential nobody is tracking. Worse, if
    the first one revokes A before the second reads it, the second looks exactly
    like a replayed token and takes the whole family down -- a legitimate user
    logged out by their own second browser tab.

    So A is re-read under a row lock and re-checked after the lock is held. The
    user row is locked first, in the same order password change takes them, so
    the two cannot deadlock and neither can interleave: without that, "verify A
    -- password change revokes everything -- insert B" resurrects a session from
    a credential the password change was meant to kill (T07-C114).

    SQLite ignores FOR UPDATE and serialises writers instead, which produces the
    same outcome by a different route; PostgreSQL is where the lock is real.
    """
    now = now or utc_now()
    digest = token_digest(refresh_token)

    session = db.session.scalar(db.select(RefreshSession).where(RefreshSession.token_sha256 == digest))
    if session is None:
        raise RefreshRejected("unknown refresh token")

    # Serialise against password change, which locks the same row first. Without
    # it the order "verify A -- password change revokes everything -- insert B"
    # resurrects a session from a credential the change was meant to kill
    # (T07-C114). No-op on SQLite, which serialises writers instead.
    db.session.execute(db.select(User.id).where(User.id == session.user_id).with_for_update())

    # Time-based refusals first. Two concurrent requests agree about the clock,
    # so these are not the racy part and are far clearer in Python than as SQL
    # that has to mean the same thing to both engines.
    if _aware(session.expires_at) <= now:
        raise RefreshRejected("session past its absolute expiry")
    if _aware(session.last_used_at) + idle_ttl() <= now:
        raise RefreshRejected("session idle too long")

    # Claiming the row IS the race, so it is one statement: revoke where it is
    # still unrevoked, and count the rows. Exactly one caller can match, and the
    # loser learns it lost from rowcount rather than from a read it took earlier.
    #
    # SELECT ... FOR UPDATE was the design's answer and is the better-known one,
    # but SQLite ignores FOR UPDATE entirely -- both callers read the row live,
    # both insert, and the family forks. A conditional update needs no row locks
    # and is atomic on both engines.
    claimed = db.session.execute(
        db.update(RefreshSession)
        .where(RefreshSession.token_sha256 == digest, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason=ROTATED)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        db.session.rollback()
        # Already spent. Either a replay of a stolen copy or a client that lost
        # the race; the server cannot tell which, which is why step 14 revokes
        # the family rather than only this row.
        raise RefreshRejected("refresh token already used", reused=True)
    db.session.expire(session)

    successor_token = new_refresh_token()
    successor = RefreshSession(
        user_id=session.user_id,
        # Same family: rotation continues one login, it does not start another.
        family_id=session.family_id,
        token_sha256=token_digest(successor_token),
        issued_at=now,
        last_used_at=now,
        # Inherited, never extended. An absolute limit that rotation could push
        # out would not be absolute (T07-C111).
        expires_at=_aware(session.expires_at),
    )
    db.session.add(successor)
    db.session.flush()

    # The revocation itself happened in the claim above; this is only the link
    # back, and it commits in the same transaction, so a failure here takes the
    # revocation with it rather than leaving a session spent for nothing.
    session.replaced_by_id = successor.id

    access_token, claims = issue_access_token(session.user_id, successor.id, now=now)
    db.session.commit()
    return IssuedSession(
        session=successor,
        access_token=access_token,
        refresh_token=successor_token,
        # Unchanged across a rotation, so an in-flight request holding the old
        # value is not rejected by a cookie that moved under it.
        csrf_token="",
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
