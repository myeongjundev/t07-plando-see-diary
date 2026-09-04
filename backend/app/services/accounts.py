"""Creating accounts, checking credentials, changing a password.
T07-C94, C95, C98, C99, C114.

Issuing a session is not here: this module answers "is this the right password
for this account", so that the answer has one shape and the code that turns a
yes into a cookie can be read on its own.

`change_password` is the one exception, and deliberately so. Replacing the hash
and revoking every session for that account have to happen under one lock, held
in the same order `rotate_session` takes it -- and an invariant that spans two
modules belongs in one function rather than in an endpoint that calls both and
hopes for the ordering.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User, normalize_email
from app.services.sessions import PASSWORD_CHANGE, revoke_all_for_user
from app.security.passwords import (
    MAX_PASSWORD_BYTES,
    PasswordTooLong,
    dummy_verify,
    hash_password,
    needs_rehash,
    verify_password,
)

# Eight is NIST SP 800-63B's floor for a user-chosen secret.
MIN_PASSWORD_CHARS = 8

# A letter and a digit, on signup only. This is a deliberate departure from
# 800-63B, which advises against composition rules because they push people
# toward predictable substitutions -- `Password1!` satisfies every rule anyone
# has ever written and is on every guessing list. It is here because the product
# asks for it, and the cost is written down rather than hidden: it belongs in
# the guide's section ⑥ alongside the other accepted limitations.
#
# Two things keep the cost small. Uppercase and symbols are *not* required, so
# the rule does not dictate a shape; and what actually costs an online guesser
# is still the throttle in design section 6, not this.
LETTER_PATTERN = re.compile(r"[A-Za-z]")
DIGIT_PATTERN = re.compile(r"[0-9]")

# No allowlist of permitted characters, deliberately. Rejecting a character
# someone chose is a rule with no benefit -- the value is hashed, never
# interpolated anywhere -- and every such list eventually rejects a good
# passphrase. The only cap is MAX_PASSWORD_BYTES, which is a denial-of-service
# guard on the hasher, not a policy.

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


def parse_credentials(payload: object, *, enforce_policy: bool = False) -> Credentials:
    """Validate a signup or login body into a normalized pair.

    `enforce_policy` is signup only, and the asymmetry is the point. Applying
    the composition rules on login would refuse an account created before them
    -- including the one the T06 data was claimed into, whose password was
    chosen by a person and never passed through here -- and would do it with a
    401 that says the credentials were wrong. It would also be readable: an
    address that fails validation answers faster than one that reaches Argon2,
    which is the timing difference `dummy_verify` exists to erase.
    """
    errors: dict[str, str] = {}
    data = payload if isinstance(payload, dict) else {}
    raw_email = data.get("email")
    raw_password = data.get("password")

    if not isinstance(raw_email, str) or not raw_email.strip():
        errors["email"] = "이메일을 입력해 주세요."
    elif not EMAIL_PATTERN.match(raw_email.strip()):
        errors["email"] = "이메일 형식이 올바르지 않습니다."

    password_error = password_policy_error(raw_password, enforce_policy=enforce_policy)
    if password_error:
        errors["password"] = password_error

    if errors:
        raise AccountValidationError(errors)
    return Credentials(email=normalize_email(raw_email), password=raw_password)


def password_policy_error(raw_password: object, *, enforce_policy: bool) -> str | None:
    """The one place the password rules are spelled out. None means it passes.

    Shared by signup and by the change endpoint, because a new password reached
    through a different door must not be held to a different rule -- a change
    form that accepted `1234` would be a way around the policy signup applies.
    """
    if not isinstance(raw_password, str) or not raw_password:
        return "비밀번호를 입력해 주세요."
    if len(raw_password) < MIN_PASSWORD_CHARS:
        return f"비밀번호는 {MIN_PASSWORD_CHARS}자 이상이어야 합니다."
    if len(raw_password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return "비밀번호가 너무 깁니다."
    if enforce_policy and not (
        LETTER_PATTERN.search(raw_password) and DIGIT_PATTERN.search(raw_password)
    ):
        # One message for both halves. Saying which of the two is missing is no
        # more useful than saying both, and the shorter rule is easier to act on.
        return "비밀번호에 영문과 숫자를 함께 넣어 주세요."
    return None


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


class WrongPassword(Exception):
    """The current password did not match. Kept separate from validation.

    A malformed new password and a wrong current one are different answers:
    the first is a 400 the caller can fix by typing something else, the second
    is a 401 that says the person at the keyboard has not proved who they are.
    """


def change_password(user_id: str, current_password: str, new_password: str) -> User:
    """Replace one account's password and kill every session it had. T07-C114.

    Three things happen together or not at all, which is why they are one
    transaction rather than three calls the endpoint makes in a row.

    **The user row is locked first**, before anything is read or written. That
    is the same order `rotate_session` takes them in (design section 4), and
    taking them in the same order is the whole reason the two cannot deadlock.

    **It is also what makes the revocation stick.** Without the lock, a refresh
    already in flight can verify token A, wait while this function revokes
    everything, and then insert its successor B -- a live session minted from a
    credential the password change was meant to kill. The revocation would look
    correct in the table and be worthless in practice. Serialising on the user
    row is what closes that window; SQLite ignores FOR UPDATE and serialises
    writers instead, which reaches the same outcome by another route.

    **Re-authentication is required**, not optional. A session alone must not be
    enough to change the password: an unattended screen would otherwise be a
    full account takeover rather than a chance to read someone's diary.

    The caller's own session dies with the rest. The endpoint opens a new one in
    the same response, so the person who just changed their password is not
    logged out for having done it -- but they are logged out *everywhere else*,
    which is the point of the criterion.
    """
    user = db.session.scalar(db.select(User).where(User.id == user_id).with_for_update())
    if user is None:  # pragma: no cover - a live session whose account is gone
        raise WrongPassword()

    if not verify_password(user.password_hash, current_password):
        raise WrongPassword()
    if new_password == current_password:
        # Refused rather than quietly accepted. It would revoke every session
        # and change nothing, which is a confusing way to log someone out of
        # their other devices and no way at all to change a password.
        raise AccountValidationError({"newPassword": "새 비밀번호가 현재 비밀번호와 같습니다."})

    user.password_hash = hash_password(new_password)
    revoke_all_for_user(user_id, PASSWORD_CHANGE)
    # Not committed here. The endpoint records the audit row inside the same
    # transaction, so a change and the record of it cannot disagree.
    db.session.flush()
    return user


def serialize_user(user: User) -> dict:
    """Public view of an account. There is no field here for anything secret."""
    return {"id": user.id, "email": user.email, "createdAt": user.created_at.isoformat()}
