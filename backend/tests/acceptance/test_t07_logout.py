"""Logout and revocation. T07-C96, C109, C110, C114.

The scene the assignment wants is one request made twice: the same address, the
same method, the same cookie, succeeding before logout and refused after.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app import create_app
from app.auth.cookies import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE, REFRESH_PATH
from app.extensions import db
from app.models import RefreshSession
from app.services.sessions import LOGOUT, ROTATED
from test_t07_refresh_rotation import KEY, csrf_headers, logged_in
from test_t07_signup_login import login, signup


def logout(client, **kwargs):
    headers = kwargs.pop("headers", None)
    if headers is None:
        headers = csrf_headers(client)
    return client.post("/api/auth/logout", json={}, headers=headers, **kwargs)


def test_c96_logout_succeeds(client, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", KEY)
    logged_in(client)
    assert logout(client).status_code == 200


def test_c109_c110_same_request_before_and_after_logout(client, monkeypatch):
    """One address, one method, one cookie. The only difference is the logout.

    The access cookie is captured before and put back afterwards, so the second
    request really is the first one repeated -- not a different request that
    happens to also fail.
    """
    monkeypatch.setenv("JWT_SECRET", KEY)
    logged_in(client)
    access = client.get_cookie(ACCESS_COOKIE).value

    before = client.get("/api/auth/me")
    assert before.status_code == 200

    assert logout(client).status_code == 200

    client.set_cookie(ACCESS_COOKIE, access)
    after = client.get("/api/auth/me")

    assert after.status_code == 401
    assert after.get_json()["error"]["message"] == "로그인이 필요합니다."
    # Same method and path both times: nothing about the request changed.
    assert before.request.path == after.request.path == "/api/auth/me"
    assert before.request.method == after.request.method == "GET"


def test_logout_revokes_the_row_before_clearing_the_cookies(client, monkeypatch):
    """A lost response must not leave a live session behind."""
    monkeypatch.setenv("JWT_SECRET", KEY)
    logged_in(client)
    response = logout(client)

    row = db.session.scalar(db.select(RefreshSession))
    assert row.revoked_at is not None
    assert row.revoked_reason == LOGOUT
    cleared = [h.split("=", 1)[0] for h in response.headers.getlist("Set-Cookie")]
    assert set(cleared) == {ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE}


def test_the_refresh_cookie_is_cleared_at_the_path_it_was_set_on(client, monkeypatch):
    """A deletion at the wrong path leaves the real cookie in place.

    Browsers match a deletion by name and path, so clearing the refresh cookie
    at / would look successful and do nothing -- the logout would appear to work
    while the browser kept a usable credential.
    """
    monkeypatch.setenv("JWT_SECRET", KEY)
    logged_in(client)
    response = logout(client)
    refresh_header = next(
        h for h in response.headers.getlist("Set-Cookie") if h.startswith(REFRESH_COOKIE)
    )
    assert f"Path={REFRESH_PATH}" in refresh_header
    assert client.get_cookie(REFRESH_COOKIE, path=REFRESH_PATH) is None


def test_the_spent_refresh_token_is_dead_after_logout(client, monkeypatch):
    """Logging out has to kill both credentials, not just the one in hand."""
    monkeypatch.setenv("JWT_SECRET", KEY)
    logged_in(client)
    refresh_token = client.get_cookie(REFRESH_COOKIE, path=REFRESH_PATH).value
    csrf = client.get_cookie(CSRF_COOKIE).value
    assert logout(client).status_code == 200

    client.set_cookie(REFRESH_COOKIE, refresh_token, path=REFRESH_PATH)
    client.set_cookie(CSRF_COOKIE, csrf)
    assert client.post("/api/auth/refresh", json={}, headers={"X-CSRF-Token": csrf}).status_code == 401


def test_logout_is_idempotent_and_keeps_the_first_reason(client, monkeypatch):
    """The second call must not rewrite why the session ended."""
    monkeypatch.setenv("JWT_SECRET", KEY)
    logged_in(client)
    access = client.get_cookie(ACCESS_COOKIE).value
    csrf = client.get_cookie(CSRF_COOKIE).value
    assert logout(client).status_code == 200
    first_time = db.session.scalar(db.select(RefreshSession)).revoked_at

    client.set_cookie(ACCESS_COOKIE, access)
    client.set_cookie(CSRF_COOKIE, csrf)
    # The session is gone, so the guard refuses before anything is rewritten.
    assert logout(client).status_code == 401
    row = db.session.scalar(db.select(RefreshSession))
    assert row.revoked_at == first_time and row.revoked_reason == LOGOUT


def test_logout_needs_the_csrf_header(client, monkeypatch):
    """Otherwise any page could log the user out."""
    monkeypatch.setenv("JWT_SECRET", KEY)
    logged_in(client)
    assert logout(client, headers={}).status_code == 403
    assert db.session.scalar(db.select(RefreshSession)).revoked_at is None
    assert client.get("/api/auth/me").status_code == 200


def test_logout_without_a_session_is_401(client, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", KEY)
    assert client.post("/api/auth/logout", json={}).status_code == 401


def test_a_logout_racing_a_refresh_is_not_mistaken_for_a_replay(tmp_path, monkeypatch):
    """Logging out with a refresh in flight is ordinary, not an attack.

    Both operations claim the same row and exactly one wins. The loser has to
    read *why* the row died: only 'rotated' means the token was already spent
    for a successor, which is what a replayed copy looks like. If losing were
    reuse on its own, step 14 would revoke the whole family every time someone
    logged out from a second tab.
    """
    monkeypatch.setenv("JWT_SECRET", KEY)
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'race.db').as_posix()}",
    })
    try:
        with app.app_context():
            db.create_all()
        client = app.test_client()
        logged_in(client)
        access = client.get_cookie(ACCESS_COOKIE).value
        refresh_token = client.get_cookie(REFRESH_COOKIE, path=REFRESH_PATH).value
        csrf = client.get_cookie(CSRF_COOKIE).value

        barrier = Barrier(2)

        def run(path):
            with app.test_client() as worker:
                worker.set_cookie(ACCESS_COOKIE, access)
                worker.set_cookie(REFRESH_COOKIE, refresh_token, path=REFRESH_PATH)
                worker.set_cookie(CSRF_COOKIE, csrf)
                barrier.wait(timeout=10)
                return worker.post(path, json={}, headers={"X-CSRF-Token": csrf})

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, ["/api/auth/logout", "/api/auth/refresh"]))

        # Either order is legitimate: logout first refuses the refresh, refresh
        # first leaves the logout to end the successor. Neither is an attack.
        assert {r.status_code for r in results} <= {200, 401}
        with app.app_context():
            rows = db.session.scalars(db.select(RefreshSession)).all()
            reasons = {row.revoked_reason for row in rows if row.revoked_at}
            assert LOGOUT in reasons or ROTATED in reasons
            # Whatever happened, nothing was recorded as a replay.
            assert "reuse" not in reasons
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
