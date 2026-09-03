"""Signup and login. T07-C94, C95, C98, C99.

Session issuance is not wired up yet -- that is step 4, and it lands on the
`login` handler here. Until then login answers whether the credentials are
right and sets nothing.
"""
from flask import jsonify, request

from app.api import api
from app.api.plans import error_response
from app.security.http import check_unauthenticated_request
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

    # Step 4 issues the session cookies here.
    return jsonify({"user": serialize_user(user)})
