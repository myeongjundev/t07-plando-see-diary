"""@login_required -- one of the three places this application says no.

Design section 3. T07-C109, C110, C114, C121, C124.

The order is fixed and matters:

    signature and exp   -- is this a token we minted, and is it still in date
    sid -> session row  -- does the login behind it still exist
    revoked / expired / idle

A signed, unexpired token is not enough. Reading the row is what makes logout
and password change take effect on the next request rather than whenever the
token happens to run out, which is the difference between satisfying T07-C114
and merely describing it.
"""
from __future__ import annotations

from functools import wraps

from flask import g, jsonify, request

from app.auth.cookies import read_access_cookie
from app.security.tokens import InvalidAccessToken, read_access_token
from app.services.sessions import live_session

# One sentence for every way of not being logged in: no cookie, a forged one,
# an expired one, a revoked one. Distinguishing them tells an attacker which
# part of a stolen value is still good.
NOT_AUTHENTICATED = "로그인이 필요합니다."


def unauthenticated_response():
    return jsonify({"error": {"message": NOT_AUTHENTICATED, "details": {}}}), 401


def current_session():
    """The live session for this request, or None. Sets nothing."""
    token = read_access_cookie(request)
    if not token:
        return None
    try:
        claims = read_access_token(token)
    except InvalidAccessToken:
        return None
    session = live_session(claims.session_id)
    if session is None:
        return None
    # The token says who it is for; the row says who it belongs to. A mismatch
    # means one of them was tampered with, and neither can be trusted to say
    # which. Only reachable if the signing key leaked, and cheap to check.
    if session.user_id != claims.user_id:
        return None
    return session


def login_required(view):
    """Refuse the request unless a live session backs it.

    Fills `g.current_session` and `g.current_user` for the handler, so no
    endpoint has to repeat the lookup -- or get it subtly different.
    """

    @wraps(view)
    def wrapper(*args, **kwargs):
        session = current_session()
        if session is None:
            return unauthenticated_response()
        g.current_session = session
        g.current_user = session.user_id
        return view(*args, **kwargs)

    return wrapper
