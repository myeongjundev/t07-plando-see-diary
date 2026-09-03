"""Shared fixtures.

T07 locks the app, so the T06 acceptance tests -- which are about what the diary
does, not about who is asking -- now need an account. They get one here rather
than each learning to log in, and none of their expectations move.

`client` is signed in. `anonymous_client` is not, and is what the tests about
being refused use. Keeping both makes "this endpoint is protected" something a
test has to opt into demonstrating, instead of something that quietly stops
being true when a decorator goes missing.
"""
import pytest
from flask.testing import FlaskClient

from app import create_app
from app.auth.cookies import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER, REFRESH_COOKIE, REFRESH_PATH
from app.extensions import db

# Synthetic. The whole suite shares one account except where a test makes more.
TEST_EMAIL = "fixture-user@example.invalid"
TEST_PASSWORD = "합성-픽스처-비밀번호-7c1d"


class BrowserLikeClient(FlaskClient):
    """A client that echoes the CSRF cookie the way the frontend will.

    Double-submit means every state-changing request carries the cookie's value
    in a header. Doing it here keeps that detail out of sixty tests that are not
    about CSRF -- and the tests that *are* about it pass their own header, which
    this leaves alone.
    """

    UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    def open(self, *args, **kwargs):
        # csrf=False is how a test says "send this without the header" -- an
        # empty headers dict cannot mean that, because plenty of tests pass one
        # to set Origin and still want the header filled in.
        send_csrf = kwargs.pop("csrf", True)
        method = (kwargs.get("method") or (args[1] if len(args) > 1 else "GET")).upper()
        if send_csrf and method in self.UNSAFE:
            headers = dict(kwargs.get("headers") or {})
            if CSRF_HEADER not in headers:
                cookie = self.get_cookie(CSRF_COOKIE)
                if cookie is not None:
                    headers[CSRF_HEADER] = cookie.value
                    kwargs["headers"] = headers
        return super().open(*args, **kwargs)


def browser_for(app, *, email=TEST_EMAIL, password=TEST_PASSWORD, sign_in=True):
    """A signed-in client for a test that builds its own app.

    The concurrency and migration tests need a real file-backed database, so
    they cannot use the `app` fixture. They still need an account, and they
    still need the CSRF header echoed, and neither is what those tests are
    about.
    """
    app.test_client_class = BrowserLikeClient
    browser = app.test_client()
    if sign_in:
        credentials = {"email": email, "password": password}
        assert browser.post("/api/auth/signup", json=credentials).status_code == 201
        assert browser.post("/api/auth/login", json=credentials).status_code == 200
    return browser


def copy_session(source, target):
    """Give another client the same login, for tests that race two requests."""
    for name, path in ((ACCESS_COOKIE, "/"), (CSRF_COOKIE, "/"), (REFRESH_COOKIE, REFRESH_PATH)):
        cookie = source.get_cookie(name, path=path)
        if cookie is not None:
            target.set_cookie(name, cookie.value, path=path)


@pytest.fixture()
def app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        }
    )
    app.test_client_class = BrowserLikeClient
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture()
def anonymous_client(app):
    """No account, no cookies. For the tests that check the door is shut."""
    return app.test_client()


@pytest.fixture()
def client(app):
    """Signed in, so a test can be about the diary rather than about the lock."""
    browser = app.test_client()
    credentials = {"email": TEST_EMAIL, "password": TEST_PASSWORD}
    assert browser.post("/api/auth/signup", json=credentials).status_code == 201
    assert browser.post("/api/auth/login", json=credentials).status_code == 200
    return browser
