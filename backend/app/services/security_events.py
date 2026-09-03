"""Writing the audit trail. Design section 7. T07-C127 to C131.

T06 had no audit log, and that was the previous submission's "what I'd do next".
This is it.

Two rules shape the module:

**Everything goes through `redact`.** Not "callers should be careful" -- the
detail dict is masked here, on the way in, so a call site that hands over a
whole request payload cannot leak it. That is what makes C115 and C131
checkable: there is one function to read.

**Recording never breaks the request.** An audit row is worth having and is not
worth turning a successful login into a 500. A write that fails is rolled back
and logged as text, and the caller proceeds. The alternative -- an audit failure
denying service -- is a denial-of-service switch wired to the least reliable
part of the system.
"""
from __future__ import annotations

import logging
from typing import Any

from flask import current_app, has_request_context, request

from app.extensions import db
from app.models import SecurityEvent
from app.security.redact import hash_ip, redact

logger = logging.getLogger(__name__)

# The vocabulary. A closed list, because an event type invented at a call site
# is one no query will ever look for, and the evidence scripts read these names.
LOGIN_SUCCESS = "LOGIN_SUCCESS"
LOGIN_FAILURE = "LOGIN_FAILURE"
LOGIN_BLOCKED = "LOGIN_BLOCKED"
LOGOUT = "LOGOUT"
SESSION_REVOKED = "SESSION_REVOKED"
SESSION_EXPIRED = "SESSION_EXPIRED"
REFRESH_TOKEN_ROTATED = "REFRESH_TOKEN_ROTATED"
REFRESH_TOKEN_REUSE_DETECTED = "REFRESH_TOKEN_REUSE_DETECTED"
CSRF_REJECTED = "CSRF_REJECTED"
AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
PASSWORD_CHANGED = "PASSWORD_CHANGED"
SIGNUP_SUCCESS = "SIGNUP_SUCCESS"
SIGNUP_DUPLICATE = "SIGNUP_DUPLICATE"
ACCOUNT_DELETED = "ACCOUNT_DELETED"

EVENT_TYPES: frozenset[str] = frozenset({
    LOGIN_SUCCESS, LOGIN_FAILURE, LOGIN_BLOCKED, LOGOUT,
    SESSION_REVOKED, SESSION_EXPIRED,
    REFRESH_TOKEN_ROTATED, REFRESH_TOKEN_REUSE_DETECTED,
    CSRF_REJECTED, AUTHORIZATION_DENIED,
    PASSWORD_CHANGED, SIGNUP_SUCCESS, SIGNUP_DUPLICATE, ACCOUNT_DELETED,
})

SUCCESS = "success"
FAILURE = "failure"
DETECTED = "detected"


def client_ip() -> str | None:
    """The caller's address, as far as it can be trusted.

    Render terminates TLS and proxies, so the socket address is the proxy's and
    `X-Forwarded-For` carries the client's -- but that header is caller-supplied
    and trusting all of it lets anyone spread their attempts across an unlimited
    number of fake addresses, which defeats the throttle it feeds.

    The rightmost entry is the one the proxy in front of us added, so that is
    the one taken. Werkzeug's ProxyFix is not used because it takes the leftmost
    by default and the number of hops to trust is a deployment fact this file
    should not be guessing at.
    """
    if not has_request_context():
        return None
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if parts:
            return parts[-1]
    return request.remote_addr


def record(
    event_type: str,
    result: str,
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    detail: dict[str, Any] | None = None,
    ip: str | None = None,
    commit: bool = True,
) -> SecurityEvent | None:
    """Write one audit row. Returns None if it could not be written.

    `commit=False` is for callers already inside a transaction that must succeed
    or fail as a unit -- a password change and the record of it, for instance,
    should not be able to disagree.
    """
    if event_type not in EVENT_TYPES:  # pragma: no cover - guards a typo at a call site
        raise ValueError(f"unknown security event type: {event_type!r}")

    def build() -> SecurityEvent:
        address = ip if ip is not None else client_ip()
        return SecurityEvent(
            event_type=event_type,
            result=result,
            user_id=user_id,
            session_id=session_id,
            # Hashed here, never stored raw, and never handed to the caller.
            ip_hash=hash_ip(address) if address else None,
            detail=redact(detail or {}),
        )

    if not commit:
        # Part of the caller's transaction, and errors belong to them. Swallowing
        # one here would mean rolling back work they are midway through and
        # returning as though nothing happened.
        event = build()
        db.session.add(event)
        db.session.flush()
        return event

    try:
        # Building is inside the try as well as writing. Redaction walks a dict
        # the caller assembled, and a value that upsets it must not turn a
        # successful login into a 500 either -- the whole point of this branch
        # is that nothing about auditing can deny service.
        event = build()
        db.session.add(event)
        db.session.commit()
        return event
    except Exception:  # pragma: no cover - exercised by the failure test
        # Rolled back so the session is usable again. The caller's request has
        # already succeeded; losing the audit row is bad and failing the request
        # to announce it is worse.
        db.session.rollback()
        # The message only, never the row -- the row is the thing we could not
        # confirm was masked.
        current_app.logger.warning("Could not record security event %s.", event_type)
        return None
