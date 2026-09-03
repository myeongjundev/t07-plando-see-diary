"""Request-shape checks that stand in front of the endpoints without a session.

Signup and login cannot use the CSRF token in `app/security/csrf.py`: there is
no session yet to bind one to. What they get instead is the first two of the
three layers in design section 5 -- a JSON body, and an Origin that belongs to
this deployment.

Together those stop the shape of cross-site request that matters here. A form on
another site can POST without script, but it can only send
application/x-www-form-urlencoded, multipart, or text/plain; asking for JSON
forces a preflight, and no CORS headers are served, so the preflight fails. The
Origin check is the second layer because a Content-Type requirement is one
misconfigured CORS policy away from being nothing at all.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

from flask import request

# Methods that change something. GET and HEAD are not checked: they are supposed
# to be safe, and if one of them is not, the fix is that endpoint, not a header.
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def allowed_origins() -> set[str]:
    """Origins permitted to send a state-changing request.

    Defaults to this deployment's own origin, which is the only one the app is
    ever served from -- Flask serves the built SPA itself, so the browser's
    Origin on a real request is always the request's own host. ALLOWED_ORIGINS
    exists for the development server, which runs the frontend on another port.
    """
    configured = os.getenv("ALLOWED_ORIGINS", "")
    extra = {value.strip() for value in configured.split(",") if value.strip()}
    parts = urlsplit(request.host_url)
    return {f"{parts.scheme}://{parts.netloc}"} | extra


def origin_is_allowed() -> bool:
    """Whether this request's Origin belongs to the deployment.

    A missing Origin passes. Browsers attach one to every cross-site
    state-changing request, so its absence means the caller is not a browser
    acting for a third-party page -- curl, the evidence script, a health probe.
    Rejecting those would break the record this assignment has to produce
    (T07-C129) without closing anything: an attacker who can set headers freely
    is not the attacker CSRF defence is about.
    """
    origin = request.headers.get("Origin")
    if origin is None:
        return True
    return origin in allowed_origins()


def wants_json() -> bool:
    """Whether the body is declared as JSON.

    Checked on the declaration rather than the content: the point is to force a
    preflight on cross-site requests, and it is the header that does that.
    """
    return (request.mimetype or "") == "application/json"


def check_unauthenticated_request() -> tuple[str, int] | None:
    """Reject a malformed or cross-origin request before anything else happens.

    Returns (message, status) to refuse, or None to proceed. Deliberately runs
    before the address is looked at, so that neither outcome depends on whether
    an account exists.
    """
    if request.method not in UNSAFE_METHODS:
        return None
    if not wants_json():
        return "요청 형식이 올바르지 않습니다.", 415
    if not origin_is_allowed():
        return "요청을 확인할 수 없습니다.", 403
    return None
