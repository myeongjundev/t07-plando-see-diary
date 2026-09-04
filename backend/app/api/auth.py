"""The authentication endpoints. T07-C94 through C99, C109, C110, C114.

signup and login answer for themselves, because there is no session yet to hang
a guard on; refresh answers for itself too, because it is the request that
arrives exactly when the access token has expired. logout and me sit behind
`@login_required` like every other protected route.
"""
from flask import jsonify, request

from app.api import api
from app.api.plans import error_response
from app.auth.cookies import attach_rotated_session, attach_session, clear_session, read_refresh_cookie
from app.auth.csrf import CSRF_FAILED, NOT_JSON, check_state_changing_request, csrf_matches
from app.auth.guards import NOT_AUTHENTICATED, login_required
from app.extensions import db
from app.models import User
from app.services.ownership import current_session_id, current_user_id
from app.security.http import check_unauthenticated_request, origin_is_allowed, wants_json
from app.security.redact import hash_ip
from app.services import security_events as events
from app.services import throttle
from app.services.sessions import (
    LOGOUT,
    REUSE,
    RefreshRejected,
    end_session,
    open_session,
    refresh_is_live,
    revoke_family,
    rotate_session,
    spent_by_rotation,
)
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

# Deliberately unhelpful. Saying "this account is locked" would confirm that
# the account exists, which is the one thing C99 asks the login path not to
# say -- so a locked-out legitimate user is told less than would be kind.
# That trade is written down in the guide's section ⑥ rather than hidden.
TOO_MANY_ATTEMPTS = "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요."


def revoke_reused_family(family_id: str, user_id: str | None) -> None:
    """Kill every session descended from a login whose token was replayed.

    A token already spent for a successor has come back, so it was copied
    between then and now. There is no way to tell whether the request in hand is
    the thief or the victim, so both are cut off.

    Revoking only the replayed row would leave the successor -- the token the
    attacker walked away with -- alive and working, which is the failure
    rotation exists to close. The cost is that a legitimate user has to log in
    again; that is much better than a session quietly shared with someone else
    (design section 4, and the accepted limitation in section 11).

    Two callers, because a replay can arrive on either side of the rotation
    lock, and both are the same event.
    """
    revoke_family(family_id, REUSE)
    events.record(
        events.REFRESH_TOKEN_REUSE_DETECTED,
        events.DETECTED,
        user_id=user_id,
        detail={"familyId": family_id},
        commit=False,
    )
    db.session.commit()


@api.post("/auth/signup")
def signup():
    refusal = check_unauthenticated_request()
    if refusal:
        return error_response(refusal[0], status=refusal[1])
    try:
        # The minimum policy is enforced here and not on login. The frontend
        # checks the same three rules while someone types, and this is the check
        # that decides -- a browser is not where a policy lives.
        credentials = parse_credentials(request.get_json(silent=True), enforce_policy=True)
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
            #
            # The event carries no address. Which one was already taken is the
            # single interesting fact here and the one that must not be written
            # down: an audit log full of them is the enumeration list C99 exists
            # to prevent, sitting in the database.
            events.record(events.SIGNUP_DUPLICATE, events.FAILURE)
            return error_response(
                "계정을 만들 수 없습니다.",
                details={"email": "이미 가입된 이메일입니다."},
                status=409,
            )
        raise
    events.record(events.SIGNUP_SUCCESS, events.SUCCESS, user_id=user.id)
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
        # closes on the other side. It still goes through the throttle below,
        # for the same reason -- but with no address to count against.
        credentials = None

    email = credentials.email if credentials else None
    ip_hash = hash_ip(events.client_ip())

    # Before the account lookup and before Argon2, so that an address that
    # exists and one that does not reach the same 429 by the same route and in
    # the same time. Checked after parsing only because parsing touches neither
    # the database nor the hasher (design section 6).
    lock = throttle.current_lock(email, ip_hash)
    if lock is not None:
        # Written as `blocked`, which the counter ignores. Counting it would let
        # anyone keep a victim locked for the full fifteen minutes just by
        # continuing to send requests they know will be refused.
        throttle.record_blocked(email, ip_hash)
        events.record(events.LOGIN_BLOCKED, events.FAILURE)
        response, status = error_response(TOO_MANY_ATTEMPTS, status=429)
        response.headers["Retry-After"] = str(lock.retry_after)
        return response, status

    user = authenticate(credentials) if credentials else None
    if user is None:
        throttle.record_failure(email, ip_hash)
        # No user_id, because there may be no user -- and no address, for the
        # same reason the duplicate above does not carry one. What the row is
        # for is the shape of the traffic: how many failures, from which hashed
        # address, how close together.
        events.record(events.LOGIN_FAILURE, events.FAILURE)
        return error_response(INVALID_CREDENTIALS, status=401)

    # Releases this pair, and only this pair. The address-wide count survives,
    # or an attacker with one account of their own could clear it at will.
    throttle.record_success(email, ip_hash)
    issued = open_session(user)
    events.record(
        events.LOGIN_SUCCESS, events.SUCCESS,
        user_id=user.id, session_id=issued.session.id,
    )
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


@api.post("/auth/refresh")
def refresh():
    """Spend the refresh cookie and hand back its successor.

    The row is checked before CSRF, which is the reverse of every other
    state-changing endpoint. The reason is the ordering the design settled on:
    this is the one request that arrives precisely when the access token has
    expired, so it cannot be behind @login_required, and refusing it on CSRF
    before knowing whether the refresh credential is even valid would answer a
    replayed token and an unauthenticated caller differently.
    """
    if not wants_json():
        return error_response(NOT_JSON, status=415)
    if not origin_is_allowed():
        return error_response(CSRF_FAILED, status=403)

    token = read_refresh_cookie(request)
    if not token:
        return error_response(NOT_AUTHENTICATED, status=401)

    # Read-only, and before the CSRF check so that a bad token and a missing
    # header cannot be told apart by which error comes back first.
    if not refresh_is_live(token):
        # This branch is where a sequential replay lands: a token spent for a
        # successor some time ago, arriving again. It is not live, so rotation
        # is never reached, and detection has to happen here or not at all.
        #
        # Deliberately before the CSRF check, and answering 401 either way. The
        # CSRF value survives rotation and is readable, so an attacker holding a
        # stolen refresh cookie usually holds a matching one; gating detection
        # on the header would let the case that matters most walk past it.
        replayed = spent_by_rotation(token)
        if replayed is not None:
            revoke_reused_family(replayed.family_id, replayed.user_id)
        response = error_response(NOT_AUTHENTICATED, status=401)
        return clear_session(response[0]), response[1]

    if not csrf_matches():
        # Refused before anything is spent. Rotating first and rejecting after
        # would let a cross-site request burn the session it was not allowed to
        # use -- a logout the attacker cannot read but can certainly cause.
        return error_response(CSRF_FAILED, status=403)

    try:
        issued = rotate_session(token)
    except RefreshRejected as rejected:
        if rejected.reused:
            # The concurrent version of the same thing: the row was live when
            # the pre-check read it and had been claimed by the time rotation
            # tried. The sequential version is handled above.
            revoke_reused_family(rejected.family_id, rejected.user_id)
        # One answer for all of them -- unknown, spent, expired, idled out.
        # Telling them apart would say which half of a stolen pair is still
        # worth something, and would tell an attacker replaying a token that
        # their replay is what triggered the revocation.
        response = error_response(NOT_AUTHENTICATED, status=401)
        return clear_session(response[0]), response[1]

    events.record(
        events.REFRESH_TOKEN_ROTATED,
        events.SUCCESS,
        user_id=issued.session.user_id,
        session_id=issued.session.id,
    )
    return attach_rotated_session(
        jsonify({"ok": True}),
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        refresh_expires_at=issued.session.expires_at,
    )


@api.post("/auth/logout")
@login_required
def logout():
    """End this session on the server, then clear the browser's copy.

    The order matters. Revoking first means that if the response is lost -- a
    dropped connection, a closed tab -- the session is already dead and the
    cookies the browser kept are worth nothing. Clearing first and revoking
    after would leave a live session behind exactly when the user could not see
    that logout had failed.

    This is what T07-C109 and C114 are asking to be shown: the same request,
    with the same cookie, succeeding before and refused after.
    """
    refusal = check_state_changing_request()
    if refusal:
        return error_response(refusal[0], status=refusal[1])

    session_id = current_session_id()
    user_id = current_user_id()
    end_session(session_id, LOGOUT)
    events.record(events.LOGOUT, events.SUCCESS, user_id=user_id, session_id=session_id)
    response = jsonify({"ok": True})
    return clear_session(response)


@api.get("/auth/me")
@login_required
def me():
    """Who the browser is, for the frontend's route gate.

    The frontend never sees a token. It asks this, and the answer is derived
    from cookies it cannot read -- which is why the gate cannot be talked out of
    a redirect by editing local state.
    """
    user = db.session.get(User, current_user_id())
    if user is None:  # pragma: no cover - a live session whose account is gone
        return error_response("로그인이 필요합니다.", status=401)
    return jsonify({"user": serialize_user(user)})
