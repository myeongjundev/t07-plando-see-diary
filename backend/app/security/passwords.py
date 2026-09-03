"""Argon2id password hashing -- the only place this application hashes a password.

Design: docs/T07-ARCHITECTURE.md section 1. T07-C101 through T07-C107.

Argon2id is memory-hard, so an attacker holding a stolen table pays memory
bandwidth per guess rather than just arithmetic, which is what blunts GPUs. The
encoded hash carries its own salt and parameters, so there is no salt column to
get wrong and no parameter to remember -- two accounts with the same password
get different stored values without any code here arranging it (T07-C104).

The cost parameters are configuration, not constants. The measurement that sets
them has to come from the deployed instance -- 0.1 CPU and 512 MiB, nothing like
the machine this is written on -- and until that runs the defaults are OWASP's
published minimum. When the number arrives, one setting changes and no code does.
"""
from __future__ import annotations

import os
from typing import Final

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Everything that means "this stored value did not match", including the ways a
# damaged row fails. argon2-cffi ASCII-encodes the stored hash before parsing
# it, so a row holding non-ASCII text raises UnicodeEncodeError rather than one
# of its own exceptions -- and an uncaught one there turns a bad row into a 500
# on the login endpoint instead of a rejection.
_REJECTIONS: Final = (
    VerifyMismatchError,
    VerificationError,
    InvalidHashError,
    UnicodeEncodeError,
    TypeError,
)

# OWASP's minimum recommendation for Argon2id. Deliberately the floor: the
# ceiling is whatever the deployed instance can do inside the latency budget
# without crowding 512 MiB, and that is measured, not guessed.
DEFAULT_TIME_COST: Final = 2
DEFAULT_MEMORY_KIB: Final = 19456
DEFAULT_PARALLELISM: Final = 1

# Argon2 has no 72-byte cliff the way bcrypt does, so nothing here truncates.
# The cap is a denial-of-service guard: hashing is deliberately expensive, and
# without a limit a megabyte password turns that expense into a weapon. Chosen
# far above any real passphrase so it never rejects a legitimate one.
MAX_PASSWORD_BYTES: Final = 1024

# Verified when the address does not exist, so that answering "no such account"
# costs the same as answering "wrong password" (T07-C99).
_DUMMY_PASSWORD: Final = "not-a-real-password-only-for-equal-timing"

_hasher: PasswordHasher | None = None
_dummy_hash: str | None = None


class PasswordTooLong(ValueError):
    """Raised before hashing, so the cost is never paid for an abusive input."""


def _int_setting(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from exc
    if value < 1:
        raise RuntimeError(f"{name} must be at least 1, got {value}")
    return value


def current_parameters() -> dict[str, int]:
    """What this process is hashing with, for the guide's version table (T07-C92)."""
    return {
        "time_cost": _int_setting("ARGON2_TIME_COST", DEFAULT_TIME_COST),
        "memory_cost": _int_setting("ARGON2_MEMORY_KIB", DEFAULT_MEMORY_KIB),
        "parallelism": _int_setting("ARGON2_PARALLELISM", DEFAULT_PARALLELISM),
    }


def get_hasher() -> PasswordHasher:
    global _hasher
    if _hasher is None:
        _hasher = PasswordHasher(type=Type.ID, hash_len=32, salt_len=16, **current_parameters())
    return _hasher


def reset_hasher() -> None:
    """Forget the cached hasher and dummy hash. For tests that change settings."""
    global _hasher, _dummy_hash
    _hasher = None
    _dummy_hash = None


def _check_length(password: str) -> None:
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise PasswordTooLong(f"password exceeds {MAX_PASSWORD_BYTES} bytes")


def hash_password(password: str) -> str:
    """Return the encoded argon2id string to store. Never returns the input."""
    _check_length(password)
    return get_hasher().hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    """True when `password` produced `stored_hash`.

    Every failure is one return value. Distinguishing "wrong password" from
    "that hash is corrupt" in the response would tell an attacker something
    about the row, and neither case is anything the caller can act on
    differently.
    """
    try:
        _check_length(password)
    except PasswordTooLong:
        # Not a match, and not worth an exception to callers: no stored hash was
        # ever produced from an input this long.
        return False
    try:
        return get_hasher().verify(stored_hash, password)
    except _REJECTIONS:
        return False


def needs_rehash(stored_hash: str) -> bool:
    """Whether this hash predates the current cost parameters.

    The parameters will change once the deployed measurement lands, and existing
    accounts would otherwise keep their weaker hashes forever. Login is the only
    moment the plaintext is in hand to redo it.
    """
    try:
        return get_hasher().check_needs_rehash(stored_hash)
    except _REJECTIONS:
        return False


def dummy_verify() -> None:
    """Spend what a real verification spends, for an address that does not exist.

    T07-C99 asks for the same message and status whether the account is missing
    or the password is wrong. Matching the wording is the easy half: without this,
    the two cases still differ by however long Argon2 takes, and the response time
    answers the question the message refuses to.

    The dummy hash is computed with the *current* parameters rather than being a
    hardcoded constant. A constant baked in at one cost setting would stop
    matching the real path the moment the parameters change -- which they will,
    once the deployed measurement lands -- and the timing would quietly diverge
    again with nothing to show that it had.
    """
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = get_hasher().hash(_DUMMY_PASSWORD)
    try:
        get_hasher().verify(_dummy_hash, "wrong-" + _DUMMY_PASSWORD)
    except _REJECTIONS:
        pass


def warm() -> None:
    """Build the hasher and the dummy hash up front.

    Called from create_app. Left to happen lazily, the very first login against
    an unknown address would pay for a hash *and* a verify while every later one
    pays for a verify -- so the first request would leak exactly the difference
    dummy_verify exists to erase.
    """
    dummy_verify()
