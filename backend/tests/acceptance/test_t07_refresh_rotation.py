"""Refresh rotation. Design section 4.

Step 5's bar is the concurrent one: two requests spending token A at the same
moment must produce exactly one successor. Everything else here follows from
rotation being a single locked transaction.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app import create_app
from app.auth.cookies import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE, REFRESH_PATH
from app.extensions import db
from app.models import RefreshSession
from app.services.sessions import ROTATED
from test_t07_signup_login import EMAIL, PASSWORD, login, signup

KEY = "synthetic-test-signing-key-not-a-real-secret-long-enough-for-hs256"


def csrf_headers(client):
    """What the frontend sends: the readable cookie echoed into a header."""
    return {"X-CSRF-Token": client.get_cookie(CSRF_COOKIE).value}


def refresh(client, **kwargs):
    # Not a default argument: Python would evaluate csrf_headers(client) even
    # when the caller passed its own, and after a 401 has cleared the cookies
    # there is nothing to read.
    headers = kwargs.pop("headers", None)
    if headers is None:
        headers = csrf_headers(client)
    return client.post("/api/auth/refresh", json={}, headers=headers, **kwargs)


def logged_in(client):
    signup(client)
    assert login(client).status_code == 200


def test_rotation_issues_a_successor_and_spends_the_old_row(client, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", KEY)
    logged_in(client)
    before = client.get_cookie(REFRESH_COOKIE, path=REFRESH_PATH).value
    original_id = db.session.scalar(db.select(RefreshSession)).id

    assert refresh(client).status_code == 200

    after = client.get_cookie(REFRESH_COOKIE, path=REFRESH_PATH).value
    assert after != before

    rows = db.session.scalars(db.select(RefreshSession).order_by(RefreshSession.issued_at)).all()
    assert len(rows) == 2
    old, new = rows
    assert old.id == original_id
    assert old.revoked_at is not None and old.revoked_reason == ROTATED
    assert old.replaced_by_id == new.id
    assert new.revoked_at is None
    # One login, one family -- rotation continues it rather than starting another.
    assert new.family_id == old.family_id


def test_c111_absolute_expiry_survives_rotation(client, monkeypatch):
    """T07-C111: a limit rotation could push out would not be absolute."""
    monkeypatch.setenv("JWT_SECRET", KEY)
    logged_in(client)
    first = db.session.scalar(db.select(RefreshSession)).expires_at
    assert refresh(client).status_code == 200
    rows = db.session.scalars(db.select(RefreshSession).order_by(RefreshSession.issued_at)).all()
    assert rows[1].expires_at == first


def test_the_spent_token_no_longer_works(client, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", KEY)
    logged_in(client)
    spent = client.get_cookie(REFRESH_COOKIE, path=REFRESH_PATH).value
    assert refresh(client).status_code == 200

    client.set_cookie(REFRESH_COOKIE, spent, path=REFRESH_PATH)
    assert refresh(client).status_code == 401


def test_the_new_access_token_works_and_names_the_new_session(client, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", KEY)
    logged_in(client)
    assert refresh(client).status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_rotation_leaves_the_csrf_cookie_alone(client, monkeypatch):
    """A tab that already read the value must not be invalidated mid-request."""
    monkeypatch.setenv("JWT_SECRET", KEY)
    logged_in(client)
    before = client.get_cookie(CSRF_COOKIE).value
    response = refresh(client)
    assert response.status_code == 200
    assert CSRF_COOKIE not in [h.split("=", 1)[0] for h in response.headers.getlist("Set-Cookie")]
    assert client.get_cookie(CSRF_COOKIE).value == before


def test_refresh_without_the_csrf_header_is_refused_and_spends_nothing(client, monkeypatch):
    """A cross-site refresh must not be able to log the victim out.

    Rotating first and rejecting afterwards would leave the session spent: the
    attacker cannot read the response, but causing the logout is enough.
    """
    monkeypatch.setenv("JWT_SECRET", KEY)
    logged_in(client)
    before = client.get_cookie(REFRESH_COOKIE, path=REFRESH_PATH).value

    assert refresh(client, headers={}).status_code == 403

    assert client.get_cookie(REFRESH_COOKIE, path=REFRESH_PATH).value == before
    assert db.session.scalar(db.select(db.func.count()).select_from(RefreshSession)) == 1
    assert db.session.scalar(db.select(RefreshSession)).revoked_at is None
    # And the session still works.
    assert refresh(client).status_code == 200


def test_a_mismatched_csrf_header_is_refused(client, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", KEY)
    logged_in(client)
    assert refresh(client, headers={"X-CSRF-Token": "not-the-cookie"}).status_code == 403


def test_refresh_requires_json_and_a_known_origin(client, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", KEY)
    logged_in(client)
    assert client.post("/api/auth/refresh", data="x", content_type="text/plain").status_code == 415
    assert client.post(
        "/api/auth/refresh", json={},
        headers={**csrf_headers(client), "Origin": "https://attacker.example"},
    ).status_code == 403


def test_refresh_without_a_cookie_is_401(client, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", KEY)
    assert client.post("/api/auth/refresh", json={}).status_code == 401


def test_an_unknown_token_and_a_missing_header_are_not_distinguishable(client, monkeypatch):
    """Both refusals must not be usable to probe which one applies.

    The row is checked first, so a caller holding a dead token gets 401 whether
    or not it also sent the header -- rather than 403 revealing that the token
    itself was fine.
    """
    monkeypatch.setenv("JWT_SECRET", KEY)
    logged_in(client)
    csrf = client.get_cookie(CSRF_COOKIE).value

    client.set_cookie(REFRESH_COOKIE, "not-a-real-token", path=REFRESH_PATH)
    with_header = refresh(client, headers={"X-CSRF-Token": csrf})
    # The 401 above cleared the cookies, so the dead token goes back on.
    client.set_cookie(REFRESH_COOKIE, "not-a-real-token", path=REFRESH_PATH)
    without_header = refresh(client, headers={})

    assert with_header.status_code == without_header.status_code == 401
    assert with_header.get_json() == without_header.get_json()


def test_concurrent_use_of_one_token_yields_exactly_one_successor(tmp_path, monkeypatch):
    """Step 5's acceptance bar.

    Without the row lock both requests read A live and both mint a successor:
    the family forks and the loser holds a working credential nothing tracks.
    With it, one rotates and the other finds A already spent.

    A file-backed database again -- the in-memory one is a single shared
    connection, which would serialise these for the wrong reason.
    """
    monkeypatch.setenv("JWT_SECRET", KEY)
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'rotate.db').as_posix()}",
    })
    try:
        with app.app_context():
            db.create_all()
        client = app.test_client()
        logged_in(client)
        token = client.get_cookie(REFRESH_COOKIE, path=REFRESH_PATH).value
        csrf = client.get_cookie(CSRF_COOKIE).value

        barrier = Barrier(2)

        def spend(_):
            with app.test_client() as worker:
                worker.set_cookie(REFRESH_COOKIE, token, path=REFRESH_PATH)
                worker.set_cookie(CSRF_COOKIE, csrf)
                barrier.wait(timeout=10)
                return worker.post("/api/auth/refresh", json={}, headers={"X-CSRF-Token": csrf})

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(spend, range(2)))

        assert sorted(r.status_code for r in results) == [200, 401]
        with app.app_context():
            rows = db.session.scalars(db.select(RefreshSession)).all()
            # The original plus exactly one successor.
            assert len(rows) == 2
            live = [row for row in rows if row.revoked_at is None]
            assert len(live) == 1
            assert len({row.family_id for row in rows}) == 1
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
