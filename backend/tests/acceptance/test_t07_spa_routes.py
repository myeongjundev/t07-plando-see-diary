"""The server's half of client routing. T07-C03, C97.

The gate that decides who sees the diary is in the browser, and the browser only
gets to run it if the server hands back the bundle. A reload on /app, or a
reviewer typing /login, is a plain GET that Flask would otherwise answer with
the API's 404 -- so the screens the criteria ask to be visited would only work
if you arrived by clicking.

What is being checked here is narrow on purpose: the shell is served at the
client routes, it is not served anywhere else, and it is never cached. Whether
/app then shows the diary or a redirect is the frontend's test.
"""
from __future__ import annotations

import pytest

from app import SPA_ROUTES, create_app

SHELL = "<html>synthetic build</html>"


@pytest.fixture()
def served(tmp_path):
    (tmp_path / "index.html").write_text(SHELL, encoding="utf-8")
    app = create_app({
        "TESTING": True,
        "STATIC_DIST": str(tmp_path),
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
    })
    return app.test_client()


@pytest.mark.parametrize("path", SPA_ROUTES)
def test_every_client_route_serves_the_app_shell(served, path):
    response = served.get(path)
    assert response.status_code == 200
    assert SHELL in response.text


@pytest.mark.parametrize("path", SPA_ROUTES)
def test_the_shell_is_never_cached(served, path):
    """index.html is where the session check starts.

    A cached copy is served to whoever opens the browser next, and on a shared
    machine that is a different person seeing the last one's starting state.
    """
    assert served.get(path).headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("path", ["/api/plnas", "/nope", "/app/settings", "/login/"])
def test_an_unknown_path_is_still_a_404(served, path):
    """The fallback is a list, not a catch-all.

    A catch-all would answer a mistyped API path with the shell and a 200, and
    the caller would parse HTML looking for JSON. Sub-paths of the client routes
    are included because none exist yet: the day one does, it gets added here
    deliberately rather than having always silently worked.
    """
    response = served.get(path)
    assert response.status_code == 404
    assert SHELL not in response.text


def test_login_and_signup_need_no_session(served):
    """T07-C03: a reviewer with no account gets this far and no further."""
    for path in ("/login", "/signup"):
        assert served.get(path).status_code == 200
    # And the data behind the shell is still refused.
    assert served.get("/api/plans").status_code == 401
