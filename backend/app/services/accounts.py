"""Creating accounts and checking credentials. T07-C94, C95, C98, C99.

Issuing a session is not here. This module answers "is this the right password
for this address" and nothing else, so that the answer has exactly one shape and
the code that turns a yes into a cookie can be read on its own.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User, normalize_email
from app.security.passwords import (
    MAX_PASSWORD_BYTES,
    PasswordTooLong,
    dummy_verify,
    hash_password,
    needs_rehash,
    verify_password,
)

# Eight is NIST SP 800-63B's floor for a user-chosen secret. Nothing above it is
# imposed -- no character classes, no forced mixture. Those rules push people
# toward predictable substitutions and shorter passwords, and the throttling in
# design section 6 is what actually costs an online guesser.
MIN_PASSWORD_CHARS = 8

# Deliberately permissive. Address syntax is far stranger than most patterns
# admit, and the only real proof that an address works is sending to it, which
# this app does not do. Anything stricter rejects valid users to no benefit.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DUPLICATE_EMAIL = "duplicate_email"


class AccountValidationError(ValueError):
    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("account validation failed")
        self.errors = errors


@dataclass(frozen=True)
class Credentials:
    email: str
    password: str


def parse_credentials(payload: object) -> Credentials:
    """Validate a signup or login body into a normalized pair."""
    errors: dict[str, str] = {}
    data = payload if isinstance(payload, dict) else {}
    raw_email = data.get("email")
    raw_password = data.get("password")

    if not isinstance(raw_email, str) or not raw_email.strip():
        errors["email"] = "이메일을 입력해 주세요."
    elif not EMAIL_PATTERN.match(raw_email.strip()):
        errors["email"] = "이메일 형식이 올바르지 않습니다."

    if not isinstance(raw_password, str) or not raw_password:
        errors["password"] = "비밀번호를 입력해 주세요."
    elif len(raw_password) < MIN_PASSWORD_CHARS:
        errors["password"] = f"비밀번호는 {MIN_PASSWORD_CHARS}자 이상이어야 합니다."
    elif len(raw_password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        errors["password"] = "비밀번호가 너무 깁니다."

    if errors:
        raise AccountValidationError(errors)
    return Credentials(email=normalize_email(raw_email), password=raw_password)


def create_account(credentials: Credentials) -> User:
    """Create one account, or raise AccountValidationError for a taken address.

    The check for an existing address is the unique index, not a SELECT. A
    read-then-write loses the race between two simultaneous signups for the same
    address and creates both -- and T07-C98 is exactly the promise that it does
    not. The database is the only thing that can decide this without a race.
    """
    user = User(email=credentials.email, password_hash=hash_password(credentials.password))
    db.session.add(user)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        raise AccountValidationError({"email": DUPLICATE_EMAIL}) from None
    db.session.commit()
    return user


def authenticate(credentials: Credentials) -> User | None:
    """The account for these credentials, or None. Both cost the same.

    A missing address must not be cheaper to answer than a wrong password. The
    matching response text (T07-C99) is undone by a reply that comes back in a
    tenth of the time, so the no-account path runs a real Argon2 verification
    against a throwaway hash instead of returning early.
    """
    user = db.session.scalar(db.select(User).where(User.email == credentials.email))
    if user is None:
        dummy_verify()
        return None
    try:
        if not verify_password(user.password_hash, credentials.password):
            return None
    except PasswordTooLong:  # pragma: no cover - verify_password already absorbs it
        return None

    # The cost parameters are still unmeasured on the deployed instance and will
    # rise once they are. Login is the only moment the plaintext exists to redo
    # the hash with, so it is taken.
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(credentials.password)
        db.session.commit()
    return user


def serialize_user(user: User) -> dict:
    """Public view of an account. There is no field here for anything secret."""
    return {"id": user.id, "email": user.email, "createdAt": user.created_at.isoformat()}
