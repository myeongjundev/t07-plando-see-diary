"""Slowing down guessed logins. Design section 6.

Counting in memory is what a throttle looks like when it does nothing: Render
Free sleeps after fifteen idle minutes and comes back a new process, so a
module-level dict is empty again exactly when a patient attacker returns. The
counter lives in `login_attempts` for that reason, and every read here is a
query over a window rather than a number held between requests.

Three rules shape the module, and each of them is a leak closed rather than a
tidiness preference:

**Only `failure` counts.** A request turned away while locked is written as
`blocked`. If it counted, anyone could hold a victim at the fifteen-minute
ceiling forever by continuing to send requests they know will be refused --
the lock would be the attack.

**Attempts against addresses that do not exist are counted too.** Otherwise
"this address never locks" answers the question T07-C99 refuses to.

**Success clears the (email, ip_hash) failures and nothing else.** The
address-wide counter is deliberately left alone: an attacker who owns one
account on the box would otherwise reset the global limit at will by logging
into their own.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import LoginAttempt

# How far back a failure still counts.
WINDOW = timedelta(minutes=15)

# Five, because people mistype a password two or three times and this must not
# be a wall ordinary use runs into. Twenty for the address-wide count, which is
# reached by a spread of addresses rather than by one person's fingers.
EMAIL_IP_THRESHOLD = 5
IP_THRESHOLD = 20

# The first lock. Short enough to be a shrug for the person who mistyped, long
# enough that the same (email, ip) pair drops to roughly five tries a minute.
BASE_LOCK = timedelta(seconds=60)
# Doubling, because a fixed sixty seconds is a rate an attacker simply accepts:
# five guesses, wait, five more, indefinitely. The ceiling is where a targeted
# legitimate user stops being locked out for practical purposes.
#
# Note that it equals WINDOW, so in practice the ladder rarely climbs past the
# fourth rung: serving out 60 + 120 + 240 + 480 seconds of locks is already long
# enough that the earliest failures have aged out of the window and the count
# falls back. That is the intended shape -- an attacker who waits that long
# between bursts is getting five guesses per quarter hour either way -- but it
# does mean the ceiling is arithmetic more than it is behaviour.
MAX_LOCK = timedelta(minutes=15)
# 60 * 2**4 already exceeds the ceiling; past that the exponent is arithmetic
# nobody reads and, on a long-running attack, a very large integer.
MAX_STEP = 4

# Rows stop meaning anything long before this; the day is slack, not policy.
RETENTION = timedelta(hours=24)
# There is no cron on Render Free, so the cleanup rides the login path. One
# request in a hundred pays for it, which on any traffic that could fill the
# table is often enough and on a quiet day costs nothing.
PRUNE_ODDS = 100

FAILURE = "failure"
BLOCKED = "blocked"
SUCCESS = "success"


@dataclass(frozen=True)
class Lock:
    """A refusal in force. `retry_after` is what the header says."""

    until: datetime
    retry_after: int


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; PostgreSQL does not."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _lock_for(count: int, threshold: int, latest: datetime | None) -> datetime | None:
    """When a run of `count` failures stops being refused, or None.

    Measured from the failure that reached the current step rather than from
    now: a lock that restarted on every request would never end while anyone
    kept knocking, which is the same denial-of-service the `blocked` result
    exists to avoid.
    """
    if latest is None or count < threshold:
        return None
    step = min(count - threshold, MAX_STEP)
    duration = min(BASE_LOCK * (2 ** step), MAX_LOCK)
    return _aware(latest) + duration


def _failures(ip_hash: str, email: str | None, since: datetime) -> tuple[int, datetime | None]:
    """Failures in the window for one counter, and the most recent one's time.

    `email=None` means the address-wide counter, which spans every address --
    not the rows whose address column happens to be null.
    """
    query = db.select(
        db.func.count(LoginAttempt.id), db.func.max(LoginAttempt.attempted_at)
    ).where(
        LoginAttempt.ip_hash == ip_hash,
        LoginAttempt.result == FAILURE,
        LoginAttempt.attempted_at >= since,
    )
    if email is not None:
        query = query.where(LoginAttempt.email_normalized == email)
    count, latest = db.session.execute(query).one()
    return count or 0, latest


def current_lock(email: str | None, ip_hash: str, *, now: datetime | None = None) -> Lock | None:
    """Whether this caller is locked out, without writing anything.

    Called before the account is looked up and before Argon2 runs, so that an
    address that exists and one that does not take the same path to the same
    429. A lock discovered after a verification would be measurably slower for
    the account that exists.
    """
    now = now or utc_now()
    since = now - WINDOW

    pair_count, pair_latest = _failures(ip_hash, email, since) if email else (0, None)
    wide_count, wide_latest = _failures(ip_hash, None, since)

    ends = [
        end
        for end in (
            _lock_for(pair_count, EMAIL_IP_THRESHOLD, pair_latest),
            _lock_for(wide_count, IP_THRESHOLD, wide_latest),
        )
        if end is not None and end > now
    ]
    if not ends:
        return None
    until = max(ends)
    # Rounded up: a Retry-After of 0 invites an immediate retry that is still
    # inside the lock, and answering "wait no time at all" is worse than saying
    # one second.
    return Lock(until=until, retry_after=max(1, math.ceil((until - now).total_seconds())))


def _write(email: str | None, ip_hash: str, result: str, now: datetime | None = None) -> None:
    db.session.add(
        LoginAttempt(
            email_normalized=email,
            ip_hash=ip_hash,
            result=result,
            attempted_at=now or utc_now(),
        )
    )
    db.session.commit()


def record_failure(email: str | None, ip_hash: str, *, now: datetime | None = None) -> None:
    """A wrong password, an unknown address, or a body that did not parse.

    All three, because the three have to be the same event from outside. An
    unparseable address that skipped the counter would lock later than a
    well-formed unregistered one, and the difference is readable.
    """
    _write(email, ip_hash, FAILURE, now)
    maybe_prune(now=now)


def record_blocked(email: str | None, ip_hash: str, *, now: datetime | None = None) -> None:
    """A request refused while the lock was in force. Never counted."""
    _write(email, ip_hash, BLOCKED, now)


def record_success(email: str, ip_hash: str, *, now: datetime | None = None) -> None:
    """Clear this pair's failures. The address-wide count is left standing."""
    db.session.execute(
        db.delete(LoginAttempt).where(
            LoginAttempt.email_normalized == email,
            LoginAttempt.ip_hash == ip_hash,
            LoginAttempt.result == FAILURE,
        )
    )
    _write(email, ip_hash, SUCCESS, now)
    maybe_prune(now=now)


def maybe_prune(*, now: datetime | None = None) -> None:
    """Drop rows older than the retention window, one time in a hundred."""
    if random.randrange(PRUNE_ODDS) != 0:
        return
    prune(now=now)


def prune(*, now: datetime | None = None) -> None:
    cutoff = (now or utc_now()) - RETENTION
    db.session.execute(db.delete(LoginAttempt).where(LoginAttempt.attempted_at < cutoff))
    db.session.commit()
