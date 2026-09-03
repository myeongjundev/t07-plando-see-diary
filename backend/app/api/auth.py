"""Signup and login. T07-C94, C95, C98, C99.

Session issuance is not wired up yet -- that is step 4, and it lands on the
`login` handler here. Until then login answers whether the credentials are
right and sets nothing.
"""
from flask import g, jsonify, request

from app.api import api
from app.api.plans import error_response
from app.auth.cookies import attach_session
from app.auth.guards import login_required
from app.extensions import db
from app.models import User
from app.security.http import check_unauthenticated_request
from app.services.sessions import open_session
from app.services.accounts import (
    DUPLICATE_EMAIL,
    AccountValidationError,
    authenticate,
    create_account,
    parse_credentials,
    serialize_user,
)

# One string for both halves of a failed login. An account that does not exist
# and a password that is wrong are the same event as far as the caller is
# concerned, and telling them apart is how an address list gets built.
INVALID_CREDENTIALS = "이메일 또는 비밀번호가 올바르지 않습니다."


@api.post("/auth/signup")
def signup():
    refusal = check_unauthenticated_request()
    if refusal:
        return error_response(refusal[0], status=refusal[1])
    try:
        credentials = parse_credentials(request.get_json(silent=True))
    except AccountValidationError as exc:
        return error_response("계정을 만들 수 없습니다.", details=exc.errors)
    try:
        user = create_account(credentials)
    except AccountValidationError as exc:
        if exc.errors.get("email") == DUPLICATE_EMAIL:
            # 409, and it does say the address is taken. Signup cannot both
            # refuse duplicates (T07-C98) and hide that the address exists, and
            # the criterion asks for the refusal. The enumeration this leaves
            # open is listed in design section 11 rather than papered over.
            return error_response(
                "계정을 만들 수 없습니다.",
                details={"email": "이미 가입된 이메일입니다."},
                status=409,
            )
        raise
    return jsonify({"user": serialize_user(user)}), 201


@api.post("/auth/login")
def login():
    refusal = check_unauthenticated_request()
    if refusal:
        return error_response(refusal[0], status=refusal[1])
    try:
        credentials = parse_credentials(request.get_json(silent=True))
    except AccountValidationError:
        # Not reported field by field. A malformed address and an unregistered
        # one would otherwise be distinguishable, which is the same leak C99
        # closes on the other side.
        return error_response(INVALID_CREDENTIALS, status=401)

    user = authenticate(credentials)
    if user is None:
        return error_response(INVALID_CREDENTIALS, status=401)

    issued = open_session(user)
    response = jsonify({"user": serialize_user(user)})
    # The three tokens exist as plaintext only between open_session and here.
    # Nothing returns them in the body: the access and refresh values are
    # HttpOnly, and putting them in JSON as well would hand script the copies
    # HttpOnly exists to withhold.
    return attach_session(
        response,
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        csrf_token=issued.csrf_token,
        refresh_expires_at=issued.session.expires_at,
    )


@api.get("/auth/me")
@login_required
def me():
    """Who the browser is, for the frontend's route gate.

    The frontend never sees a token. It asks this, and the answer is derived
    from cookies it cannot read -- which is why the gate cannot be talked out of
    a redirect by editing local state.
    """
    user = db.session.get(User, g.current_user)
    if user is None:  # pragma: no cover - a live session whose account is gone
        return error_response("로그인이 필요합니다.", status=401)
    return jsonify({"user": serialize_user(user)})
