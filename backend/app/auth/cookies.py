"""The three cookies, and the attributes that make each one safe. Design section 4.

| cookie                  | HttpOnly | SameSite | Path       |
| ----------------------- | -------- | -------- | ---------- |
| `__Host-pds_access`     | yes      | Lax      | /          |
| `__Secure-pds_refresh`  | yes      | Strict   | /api/auth  |
| `__Host-pds_csrf`       | no       | Lax      | /          |

The access cookie goes everywhere, so it is Lax: arriving from an external link
should not look like being logged out. The refresh cookie is only ever sent by
this app's own script to one path, so Strict costs nothing and is stricter.

`__Host-` requires Path=/, which the refresh cookie cannot have without giving
up the narrow path -- the more valuable of the two here. The prefix's usual job
is stopping a sibling subdomain from overwriting the cookie, and onrender.com is
on the Public Suffix List, so browsers already refuse a Domain=.onrender.com
cookie. The prefix is still used where it is free, so that moving to a custom
domain later does not quietly remove a protection nobody noticed was load-bearing.

The CSRF cookie is deliberately readable: script has to copy it into a header.
It is a value to be echoed, not a credential -- holding it proves nothing
without the other two.
"""
from __future__ import annotations

from datetime import datetime

from flask import Request, Response, current_app

ACCESS_COOKIE = "__Host-pds_access"
REFRESH_COOKIE = "__Secure-pds_refresh"
CSRF_COOKIE = "__Host-pds_csrf"
CSRF_HEADER = "X-CSRF-Token"

REFRESH_PATH = "/api/auth"


def secure_cookies() -> bool:
    """Whether to set the Secure attribute. On everywhere except the test client.

    It used to be keyed to REQUIRE_POSTGRES, which meant local development ran
    without it -- and a browser rejects a `__Host-` cookie that has no Secure
    attribute, whatever the scheme. Every login in a real dev browser silently
    stored nothing. The test client is the only caller that needs it off, and
    it is off there because Werkzeug's cookie jar will not send a Secure cookie
    over the http:// the tests use.

    Browsers make an exception for http://localhost and accept Secure cookies
    there, so the dev server works with this on.
    """
    return not current_app.config.get("TESTING", False)


def _set(response: Response, name: str, value: str, *, http_only: bool, same_site: str,
         path: str, expires: datetime | None) -> None:
    response.set_cookie(
        name,
        value,
        httponly=http_only,
        secure=secure_cookies(),
        samesite=same_site,
        path=path,
        expires=expires,
    )


def attach_session(response: Response, *, access_token: str, refresh_token: str,
                   csrf_token: str, refresh_expires_at: datetime) -> Response:
    """Put a freshly issued session on the response.

    The access cookie is a session cookie -- no Expires. Its lifetime is the
    `exp` inside the token, which the server checks; a browser-side expiry would
    only decide when the cookie stops being sent, and a cookie that outlived its
    token would be indistinguishable from one that had not.
    """
    _set(response, ACCESS_COOKIE, access_token, http_only=True, same_site="Lax", path="/", expires=None)
    _set(response, REFRESH_COOKIE, refresh_token, http_only=True, same_site="Strict",
         path=REFRESH_PATH, expires=refresh_expires_at)
    _set(response, CSRF_COOKIE, csrf_token, http_only=False, same_site="Lax", path="/",
         expires=refresh_expires_at)
    return response


def attach_rotated_session(response: Response, *, access_token: str, refresh_token: str,
                           refresh_expires_at: datetime) -> Response:
    """Replace the two credentials after a rotation, leaving the CSRF value alone.

    Rewriting the CSRF cookie here would break the request that is in flight in
    another tab: it read the old value into a header before this response
    landed. The value is not a credential, and its lifetime is the login.
    """
    _set(response, ACCESS_COOKIE, access_token, http_only=True, same_site="Lax", path="/", expires=None)
    _set(response, REFRESH_COOKIE, refresh_token, http_only=True, same_site="Strict",
         path=REFRESH_PATH, expires=refresh_expires_at)
    return response


def clear_session(response: Response) -> Response:
    """Remove all three, with the attributes they were set with.

    A browser matches a deletion to an existing cookie by name, path and domain.
    Deleting the refresh cookie at Path=/ leaves the real one at /api/auth in
    place, which is how a logout ends up looking successful and doing nothing.
    """
    response.delete_cookie(ACCESS_COOKIE, path="/", samesite="Lax", secure=secure_cookies(), httponly=True)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH, samesite="Strict",
                           secure=secure_cookies(), httponly=True)
    response.delete_cookie(CSRF_COOKIE, path="/", samesite="Lax", secure=secure_cookies(), httponly=False)
    return response


def read_access_cookie(request: Request) -> str | None:
    return request.cookies.get(ACCESS_COOKIE)


def read_refresh_cookie(request: Request) -> str | None:
    return request.cookies.get(REFRESH_COOKIE)


def read_csrf_cookie(request: Request) -> str | None:
    return request.cookies.get(CSRF_COOKIE)
