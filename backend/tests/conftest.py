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


# ---------------------------------------------------------------------------
# The PostgreSQL-only tests drop every table on the database TEST_DATABASE_URL
# names. That variable is typed by a person at a keyboard, usually while looking
# at a dashboard that has the production connection string on it -- and the
# deployed database holds the diary this project exists to keep.
#
# So it is checked rather than trusted. Three ways a target is refused, cheapest
# first, and any one of them is enough.
# ---------------------------------------------------------------------------

import os  # noqa: E402

from sqlalchemy import create_engine, inspect, text  # noqa: E402

from app.config import normalize_database_url  # noqa: E402

# Names that mean "this is the real one" -- used only when the database cannot be
# read. Neon child branches keep the parent's database name (`neondb`), so the
# name alone must never be the thing that refuses a legitimate scratch branch.
PRODUCTION_NAMES = frozenset({"neondb", "production", "prod", "main", "t06", "t07"})


def refuse_production(url: str) -> None:
    """Raise unless `url` is safe to drop every table on.

    Not a fixture, so it can be called from module scope as well as a test, and
    it raises rather than skipping: a skip here would read as "PostgreSQL not
    configured" when what actually happened is "you pointed this at the diary".

    **Emptiness is the authority, not the name.** A database with no diary in it
    is safe to drop whatever it is called, and one with a diary in it is not
    safe however harmless the name looks. The name is only consulted when the
    rows cannot be counted -- an unreachable database is exactly when a guess is
    all that is left, and the guess should be the cautious one.
    """
    if os.getenv("ALLOW_DESTRUCTIVE_TEST_DATABASE") == "1":
        # The escape hatch exists so this file is never the reason a real check
        # cannot run. Spelled out in full, so nobody sets it by reflex.
        return

    deployed = os.getenv("DATABASE_URL")
    if deployed and url.strip() == deployed.strip():
        raise RuntimeError(
            "TEST_DATABASE_URL is the same as DATABASE_URL. These tests drop every "
            "table; point them at a scratch database or a Neon child branch."
        )

    name = url.rsplit("/", 1)[-1].split("?")[0].lower()
    engine = create_engine(normalize_database_url(url))
    try:
        tables = set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            for table in ("plans", "users"):
                if table not in tables:
                    continue
                rows = connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
                if rows:
                    raise RuntimeError(
                        f"TEST_DATABASE_URL has {rows} rows in {table!r}. These tests drop "
                        "every table, and that is somebody's diary. Use a Neon branch made "
                        "with 'Branch schema only', or an empty database."
                    )
    except RuntimeError:
        raise
    except Exception as unreachable:
        # Could not look. Fall back to the name, and prefer refusing.
        if name in PRODUCTION_NAMES:
            raise RuntimeError(
                f"TEST_DATABASE_URL names {name!r} and could not be read to check whether "
                f"it is empty ({unreachable.__class__.__name__}). These tests drop every "
                "table, so this is refused rather than guessed at."
            ) from None
        raise
    finally:
        engine.dispose()


def postgres_url_or_skip(raw: str | None) -> str:
    """The PostgreSQL target, spelled for the driver this project installs.

    Callers pass `os.getenv("TEST_DATABASE_URL")` -- a value copied from a
    provider's dashboard, which will say `postgresql://`. Rewriting it here
    means a person setting the variable gets the tests they asked for rather
    than an import error naming a package they never chose.
    """
    return normalize_database_url(raw) if raw else ""
