"""Access tokens and the sid-bound guard. T07-C111, C112, C114.

The claim this file has to hold up is the expensive one from design section 1:
a token that is still signed and still in date gets nothing once the session
behind it is gone.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.auth.cookies import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE
from app.extensions import db
from app.models import RefreshSession
from app.security import tokens
from app.security.tokens import InvalidAccessToken, issue_access_token, read_access_token
from app.services.sessions import LOGOUT, PASSWORD_CHANGE, revoke, revoke_all_for_user
from test_t07_signup_login import EMAIL, PASSWORD, login, signup

USER_ID = "00000000-0000-4000-8000-0000000000u1".replace("0u1", "0c1")
SESSION_ID = "00000000-0000-4000-8000-0000000000d1"


@pytest.fixture(autouse=True)
def _fixed_key(monkeypatch):
    # Synthetic, and only ever in this process.
    monkeypatch.setenv("JWT_SECRET", "synthetic-test-signing-key-not-a-real-secret-long-enough-for-hs256")


def test_issued_token_round_trips():
    token, claims = issue_access_token(USER_ID, SESSION_ID)
    read = read_access_token(token)
    assert (read.user_id, read.session_id) == (USER_ID, SESSION_ID)
    assert read.token_id == claims.token_id


def test_payload_carries_nothing_beyond_the_five_claims():
    """A JWT payload is base64, not ciphertext. Whoever holds it reads it."""
    token, _ = issue_access_token(USER_ID, SESSION_ID)
    payload = jwt.decode(token, options={"verify_signature": False})
    assert set(payload) == {"sub", "sid", "jti", "iat", "exp"}
    body = token.split(".")[1]
    for secret in ("password", "hash", "refresh", "csrf", "secret", EMAIL):
        assert secret not in jwt.utils.base64url_decode(body + "=" * (-len(body) % 4)).decode()


def test_a_token_signed_with_another_key_is_refused(monkeypatch):
    token, _ = issue_access_token(USER_ID, SESSION_ID)
    monkeypatch.setenv("JWT_SECRET", "a-different-synthetic-key-also-long-enough-for-hs256-abcdefgh")
    with pytest.raises(InvalidAccessToken):
        read_access_token(token)


def test_an_unsigned_token_is_refused():
    """`alg: none` must not be an option the token gets to choose.

    The algorithm list passed to decode is fixed, so the header cannot nominate
    one. This is the confusion attack the library exists to have already thought
    about, and the test is here to catch anyone loosening it later.
    """
    forged = jwt.encode(
        {"sub": USER_ID, "sid": SESSION_ID, "jti": "x", "iat": 0, "exp": 9999999999},
        key="",
        algorithm="none",
    )
    with pytest.raises(InvalidAccessToken):
        read_access_token(forged)


def test_a_token_without_an_expiry_is_refused():
    """Otherwise it would verify forever."""
    forged = jwt.encode(
        {"sub": USER_ID, "sid": SESSION_ID, "jti": "x", "iat": 0},
        tokens.signing_key(),
        algorithm="HS256",
    )
    with pytest.raises(InvalidAccessToken):
        read_access_token(forged)


def test_c111_access_expires(monkeypatch):
    monkeypatch.setenv("ACCESS_TTL_SECONDS", "1")
    past = datetime.now(timezone.utc) - timedelta(seconds=30)
    token, _ = issue_access_token(USER_ID, SESSION_ID, now=past)
    with pytest.raises(InvalidAccessToken):
        read_access_token(token)


def test_c112_no_token_in_any_url(client):
    """The values that identify a person travel in cookies and nowhere else."""
    signup(client)
    response = login(client)
    assert response.status_code == 200
    cookies = {name: value for name, value in (
        (header.split("=", 1)[0], header.split("=", 1)[1].split(";", 1)[0])
        for header in response.headers.getlist("Set-Cookie")
    )}
    assert set(cookies) == {ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE}
    for value in cookies.values():
        assert value not in response.headers.get("Location", "")
        assert value not in response.request.query_string.decode()
    # And none of them are handed back in the body either.
    body = response.get_data(as_text=True)
    for name, value in cookies.items():
        assert value not in body, name


def test_login_sets_the_three_cookies_with_their_attributes(client):
    signup(client)
    response = login(client)
    headers = {h.split("=", 1)[0]: h for h in response.headers.getlist("Set-Cookie")}

    access = headers[ACCESS_COOKIE]
    assert "HttpOnly" in access and "SameSite=Lax" in access and "Path=/;" in access + ";"

    refresh = headers[REFRESH_COOKIE]
    assert "HttpOnly" in refresh and "SameSite=Strict" in refresh
    # The narrow path is the point of giving up the __Host- prefix here.
    assert "Path=/api/auth" in refresh

    csrf = headers[CSRF_COOKIE]
    # Script has to read this one to echo it in a header.
    assert "HttpOnly" not in csrf


def test_me_requires_a_session(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_answers_for_a_logged_in_browser(client):
    signup(client)
    login(client)
    response = client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.get_json()["user"]["email"] == EMAIL


def test_c114_logout_kills_access_immediately(client, app):
    """The expensive claim: a still-valid token stops working when the row does.

    No logout endpoint yet -- that is step 6 -- so the row is revoked directly.
    What is being tested is the guard, not the endpoint: the access cookie is
    untouched and still inside its ten minutes, and the next request must fail
    anyway.
    """
    signup(client)
    login(client)
    assert client.get("/api/auth/me").status_code == 200

    # The fixture's app context is already pushed and the test client reuses it,
    # so this is the same session the request will read through. Opening a
    # nested one instead would commit in a second session and leave a stale copy
    # of the row in the first, and the guard would look correct while reading
    # the version from before the revocation.
    session = db.session.scalar(db.select(RefreshSession))
    revoke(session, LOGOUT)
    db.session.commit()

    assert client.get("/api/auth/me").status_code == 401
    # The token itself is still perfectly valid; only the row changed.
    assert read_access_token(client.get_cookie(ACCESS_COOKIE).value).session_id == session.id


def test_c114_password_change_revokes_all_sessions(client, app):
    signup(client)
    login(client)
    assert client.get("/api/auth/me").status_code == 200
    user_id = db.session.scalar(db.select(RefreshSession)).user_id
    assert revoke_all_for_user(user_id, PASSWORD_CHANGE) == 1
    db.session.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_a_session_that_never_existed_is_refused(client):
    """A signed token naming an unknown row gets nothing.

    Only reachable if the signing key leaked, but that is the case where the
    row lookup is the last thing standing.
    """
    signup(client)
    login(client)
    forged, _ = issue_access_token(USER_ID, SESSION_ID)
    client.set_cookie(ACCESS_COOKIE, forged)
    assert client.get("/api/auth/me").status_code == 401


def test_a_token_naming_someone_elses_session_is_refused(client, app):
    signup(client)
    login(client)
    session_id = db.session.scalar(db.select(RefreshSession)).id
    mismatched, _ = issue_access_token(USER_ID, session_id)
    client.set_cookie(ACCESS_COOKIE, mismatched)
    assert client.get("/api/auth/me").status_code == 401


def test_every_rejection_says_the_same_thing(client, app):
    """No cookie, a forged one, an expired one, a revoked one: one sentence.

    Telling them apart would say which half of a stolen value is still good.
    """
    bodies = [client.get("/api/auth/me").get_json()]

    client.set_cookie(ACCESS_COOKIE, "not-a-token")
    bodies.append(client.get("/api/auth/me").get_json())

    signup(client)
    login(client)
    session = db.session.scalar(db.select(RefreshSession))
    revoke(session, LOGOUT)
    db.session.commit()
    bodies.append(client.get("/api/auth/me").get_json())

    assert bodies[0] == bodies[1] == bodies[2]
    assert bodies[0]["error"]["message"] == "로그인이 필요합니다."


def test_production_refuses_to_start_without_a_signing_key(monkeypatch):
    """A per-process fallback key logs everyone out on the next wake.

    Render Free restarts whenever it sleeps, so the fallback would not be a
    quiet degradation -- it would be sessions ending several times a day for no
    reason visible anywhere.
    """
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        tokens.require_signing_key()


def test_production_refuses_a_signing_key_short_enough_to_brute_force(monkeypatch):
    """PyJWT only warns about a short HMAC key, and a warning is not a check."""
    monkeypatch.setenv("JWT_SECRET", "tooshort")
    with pytest.raises(RuntimeError, match="at least"):
        tokens.require_signing_key()


def test_bad_ttl_settings_fail_loudly(monkeypatch):
    monkeypatch.setenv("ACCESS_TTL_SECONDS", "ten minutes")
    with pytest.raises(RuntimeError):
        tokens.access_ttl()
    monkeypatch.setenv("ACCESS_TTL_SECONDS", "0")
    with pytest.raises(RuntimeError):
        tokens.access_ttl()
