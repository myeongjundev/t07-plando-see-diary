"""Double-submit CSRF. Design section 5, layer three.

The value is generated at login, set in a readable `__Host-` cookie, and echoed
back in `X-CSRF-Token`. It matches or the request is refused.

It is not stored server-side, in plaintext or digest. Binding it to the session
row would add nothing: `__Host-` forces Secure, host-only and Path=/, and
onrender.com is on the Public Suffix List, so no sibling service can plant the
cookie. The case binding would cover -- same-origin XSS -- is one where the
attacker can simply read the real cookie and send the request itself. What
binding does add is three failure modes: bootstrapping a value for signup and
login, ordering the check on refresh when the access token has expired, and
racing an in-flight request against a rotation that replaced the value.

So the CSRF value survives rotation unchanged, and is replaced only by a new
login.
"""
from __future__ import annotations

import hmac

from flask import request

from app.auth.cookies import CSRF_COOKIE, CSRF_HEADER
from app.security.http import origin_is_allowed, wants_json

CSRF_FAILED = "요청을 확인할 수 없습니다."
NOT_JSON = "요청 형식이 올바르지 않습니다."


def csrf_matches() -> bool:
    """Whether the header echoes the cookie.

    Compared with compare_digest. The values are not secret in the way a
    password is, but a length-revealing early exit is free to avoid and the
    habit is worth more than the microsecond.
    """
    sent = request.headers.get(CSRF_HEADER)
    stored = request.cookies.get(CSRF_COOKIE)
    if not sent or not stored:
        return False
    return hmac.compare_digest(sent, stored)


def check_state_changing_request() -> tuple[str, int] | None:
    """All three layers, in the order they should fail.

    Returns (message, status) to refuse, or None to proceed.

    Shape before identity: a malformed request is malformed whether or not
    anyone is logged in, and answering it differently once a session exists
    would make the refusal itself a signal.
    """
    if not wants_json():
        return NOT_JSON, 415
    if not origin_is_allowed():
        return CSRF_FAILED, 403
    if not csrf_matches():
        return CSRF_FAILED, 403
    return None
