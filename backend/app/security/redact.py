"""The one place a value is masked. Design section 7. T07-C115, C131.

Two things must never appear in the audit trail or in the evidence files the
submission carries: secrets, and raw IP addresses. Masking at each call site is
how one of forty call sites ends up missing it, so every path that writes a
`security_events` row and every path that prints evidence goes through here.

The rule this file follows is that a value is masked by *name*, not by looking
like a secret. Pattern-matching for token-shaped strings finds the ones that
look the part and misses a short one; a key called `password` is a password
whatever its value happens to be.

Never recorded, at all:

    비밀번호 · 비밀번호 해시 · Access 토큰 원문 · Refresh 토큰 원문
    CSRF 토큰 원문 · JWT_SECRET · Authorization 헤더 원문 · 원본 IP
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
from typing import Any

MASK = "[redacted]"

# Key names whose value never survives, whatever it holds. Compared against the
# lower-cased key with separators stripped, so `password_hash`, `passwordHash`
# and `PASSWORD HASH` are one entry.
SECRET_KEYS: frozenset[str] = frozenset({
    "password",
    "newpassword",
    "currentpassword",
    "passwordhash",
    "hash",
    "token",
    "accesstoken",
    "refreshtoken",
    "csrftoken",
    "jwt",
    "jwtsecret",
    "secret",
    "authorization",
    "cookie",
    "setcookie",
    "sessionsecret",
    "iphashsecret",
    "apikey",
    "credential",
    "credentials",
})

# Keys that hold an address rather than a secret. They are hashed rather than
# masked, because "the same visitor as last time" is the whole point of
# recording it and a constant string cannot say that.
ADDRESS_KEYS: frozenset[str] = frozenset({"ip", "ipaddress", "remoteaddr", "clientip"})

MAX_DEPTH = 6
MAX_STRING = 500


def _normalize(key: str) -> str:
    return "".join(character for character in key.lower() if character.isalnum())


def canonical_ip(value: str | None) -> str:
    """One spelling per address, before it is hashed.

    Without this, `::ffff:203.0.113.5` and `203.0.113.5` hash differently and
    the same client counts as two -- which halves the rate limit's effect on
    anyone whose requests arrive both ways. Anything unparseable is kept as
    given, trimmed: a malformed value is still a stable key, and inventing one
    would merge unrelated clients.
    """
    if not value:
        return ""
    text = value.strip()
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return text
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return str(address)


def ip_secret() -> bytes:
    """The key IP addresses are hashed with. Separate from JWT_SECRET.

    Separate because the two have different blast radii: the signing key can be
    rotated to invalidate access tokens, and doing so must not also reset every
    rate-limit window. Rotating this one does reset them, which is written into
    the runbook rather than discovered.

    Falls back to a per-process value when unset. That is wrong for production
    -- every restart would forget who had been trying -- and is why the flag
    that means "this is the deployed configuration" refuses to boot without it.
    """
    configured = os.getenv("IP_HASH_SECRET")
    if configured:
        return configured.encode("utf-8")
    return _process_fallback()


_FALLBACK: bytes | None = None


def _process_fallback() -> bytes:
    global _FALLBACK
    if _FALLBACK is None:
        _FALLBACK = os.urandom(32)
    return _FALLBACK


def hash_ip(value: str | None) -> str:
    """HMAC-SHA-256 of the canonical address. Never the address itself.

    HMAC with a private key, not a plain digest: IPv4 is 2^32 values, so a
    keyed-less SHA-256 of an address is reversible by brute force in seconds.
    A leaked table should not be a visitor log (design section 6).
    """
    return hmac.new(ip_secret(), canonical_ip(value).encode("utf-8"), hashlib.sha256).hexdigest()


def require_ip_secret() -> None:
    """Refuse to boot a deployed process without a stable IP hashing key.

    A per-process fallback makes the throttle look like it works. It counts, it
    locks, and then Render Free wakes the instance and every counter is a
    stranger again -- which is the memory-based throttle the design rejected,
    wearing a database's clothes.
    """
    if not os.getenv("IP_HASH_SECRET"):
        raise RuntimeError(
            "IP_HASH_SECRET is required in production: without it every restart "
            "resets the login throttle, which is the failure mode the database-backed "
            "counter exists to avoid."
        )


def redact(value: Any, *, _depth: int = 0) -> Any:
    """A value safe to store in `security_events.metadata` or print as evidence.

    Recursive, because the thing being logged is usually a dict of dicts and a
    secret one level down is still a secret. Depth- and length-capped: an audit
    row is a description of an event, and something that needs six levels or
    five hundred characters to describe is a payload someone is about to store
    by accident.
    """
    if _depth >= MAX_DEPTH:
        return "[truncated]"
    if isinstance(value, dict):
        masked = {}
        for key, item in value.items():
            name = _normalize(str(key))
            if name in SECRET_KEYS:
                masked[key] = MASK
            elif name in ADDRESS_KEYS:
                # Renamed as well as hashed, so nothing downstream reads a
                # digest out of a field called `ip` and prints it as an address.
                masked["ipHash"] = hash_ip(item if isinstance(item, str) else None)
            else:
                masked[key] = redact(item, _depth=_depth + 1)
        return masked
    if isinstance(value, (list, tuple)):
        return [redact(item, _depth=_depth + 1) for item in value]
    if isinstance(value, str):
        return value if len(value) <= MAX_STRING else value[:MAX_STRING] + "…"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    # Anything else is described, not serialised. A model instance rendered with
    # repr() is how a password hash reaches a log.
    return f"[{type(value).__name__}]"
