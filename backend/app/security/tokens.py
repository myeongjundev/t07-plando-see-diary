"""Access tokens and the opaque refresh secret. Design section 4.

Two credentials with opposite shapes, for opposite reasons.

The access token is a signed JWT that travels on every request. It carries the
minimum needed to find the session -- `sub`, `sid`, `iat`, `exp`, `jti` -- and
nothing else, because a JWT payload is base64, not ciphertext: everyone who
holds it can read it.

The refresh token is 256 bits of randomness and means nothing on its own. Only
its SHA-256 is stored, so a leaked table is not a set of working credentials,
and it travels only to /api/auth. SHA-256 rather than Argon2 because a random
256-bit value is not a dictionary-attack target -- the reason passwords need a
slow hash does not apply.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Final

import jwt

ALGORITHM: Final = "HS256"

# 10 minutes. Short enough that a stolen access cookie is worth little, long
# enough that rotation -- and its database write -- happens six times an hour
# rather than constantly.
DEFAULT_ACCESS_TTL_SECONDS: Final = 600
# Idle: unused for two days and the session is gone.
DEFAULT_IDLE_TTL_SECONDS: Final = 48 * 3600
# Absolute: fourteen days from the login, inherited unchanged by every rotation
# in the family. A limit rotation could extend would not be absolute.
DEFAULT_ABSOLUTE_TTL_SECONDS: Final = 14 * 24 * 3600

REFRESH_TOKEN_BYTES: Final = 32  # 256 bits
CSRF_TOKEN_BYTES: Final = 32


class InvalidAccessToken(Exception):
    """The token was absent, malformed, unsigned by us, or expired."""


@dataclass(frozen=True)
class AccessClaims:
    user_id: str
    session_id: str
    token_id: str
    expires_at: datetime


def _seconds(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer number of seconds, got {raw!r}") from exc
    if value < 1:
        raise RuntimeError(f"{name} must be at least 1, got {value}")
    return value


def access_ttl() -> timedelta:
    return timedelta(seconds=_seconds("ACCESS_TTL_SECONDS", DEFAULT_ACCESS_TTL_SECONDS))


def idle_ttl() -> timedelta:
    return timedelta(seconds=_seconds("IDLE_TTL_SECONDS", DEFAULT_IDLE_TTL_SECONDS))


def absolute_ttl() -> timedelta:
    return timedelta(seconds=_seconds("ABSOLUTE_TTL_SECONDS", DEFAULT_ABSOLUTE_TTL_SECONDS))


def signing_key() -> str:
    """The HS256 key, from the environment.

    Render generates it (`generateValue` in render.yaml), so the value has never
    been in git, on a laptop, or in a transcript -- which is the whole of what
    T07-C113 asks to be shown.

    Outside production a per-process random key is used instead of failing,
    because a developer running the test suite has no deployment to inherit one
    from. It is never a fallback in production: `require` is what create_app
    calls when REQUIRE_POSTGRES is set, and it refuses to start without one.
    Rotating the key invalidates live access tokens; refresh sessions survive
    and clients recover silently on their next rotation.
    """
    configured = os.getenv("JWT_SECRET")
    if configured:
        return configured
    global _ephemeral_key
    if _ephemeral_key is None:
        _ephemeral_key = secrets.token_urlsafe(32)
    return _ephemeral_key


_ephemeral_key: str | None = None


# RFC 7518 3.2: an HMAC key should be at least as long as the hash it feeds.
# Render's generateValue is comfortably longer; this catches a hand-set one.
MIN_SIGNING_KEY_BYTES: Final = 32


def require_signing_key() -> None:
    """Refuse to start a production process without a usable key.

    Silently falling back to a random one would work, right up to the second
    instance -- or the next restart, which Render Free does every time it wakes
    -- when every token minted by the first stops verifying and everyone is
    logged out for no visible reason.

    Length is checked too. A short HMAC key is brute-forceable offline from a
    single captured token, and PyJWT only warns; a warning in a log nobody reads
    is not a check.
    """
    configured = os.getenv("JWT_SECRET")
    if not configured:
        raise RuntimeError("JWT_SECRET must be set when REQUIRE_POSTGRES is on.")
    if len(configured.encode("utf-8")) < MIN_SIGNING_KEY_BYTES:
        raise RuntimeError(
            f"JWT_SECRET must be at least {MIN_SIGNING_KEY_BYTES} bytes; "
            "a shorter HMAC key can be recovered offline from one captured token."
        )


def new_refresh_token() -> str:
    """256 bits from the OS.

    `secrets`, not `random`: the Mersenne Twister behind `random` has its
    internal state recoverable from a few outputs, which for a session token
    means one leaked value predicts the rest.
    """
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(CSRF_TOKEN_BYTES)


def token_digest(token: str) -> str:
    """What gets stored. The token itself never does."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_access_token(user_id: str, session_id: str, *, now: datetime | None = None) -> tuple[str, AccessClaims]:
    now = now or datetime.now(timezone.utc)
    expires_at = now + access_ttl()
    claims = AccessClaims(
        user_id=user_id,
        session_id=session_id,
        token_id=str(uuid.uuid4()),
        expires_at=expires_at,
    )
    payload = {
        "sub": claims.user_id,
        # Names the refresh session this token belongs to. The guard reads that
        # row on every request, which is what makes logout immediate (T07-C114).
        "sid": claims.session_id,
        "jti": claims.token_id,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, signing_key(), algorithm=ALGORITHM), claims


def read_access_token(token: str) -> AccessClaims:
    """Verify and decode, or raise InvalidAccessToken.

    `algorithms` is a fixed list, so the token's own `alg` header cannot choose
    how it is checked -- the confusion attack where a token arrives claiming
    `none`, or claiming HMAC against a key meant to be a public one.

    `exp` is required rather than merely honoured when present: a token without
    one would otherwise verify and never expire.
    """
    try:
        payload = jwt.decode(
            token,
            signing_key(),
            algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "sub", "sid", "jti"]},
        )
    except jwt.InvalidTokenError as exc:
        raise InvalidAccessToken(str(exc)) from None

    subject, session_id, token_id = payload.get("sub"), payload.get("sid"), payload.get("jti")
    if not all(isinstance(value, str) and value for value in (subject, session_id, token_id)):
        raise InvalidAccessToken("claims are present but not strings")
    return AccessClaims(
        user_id=subject,
        session_id=session_id,
        token_id=token_id,
        expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
    )
