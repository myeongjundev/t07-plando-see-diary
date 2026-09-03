"""The audit trail, and the promise that it holds no secrets. T07-C115, C131.

Two kinds of test here, and the second is the one that matters.

The first checks that events are written where the design says. The second
drives every path that writes one, then reads the *whole table* and asserts that
nothing in it is a password, a token, a hash, or an IP address. That sweep is
the check the design asks for, and it is written as a sweep on purpose: a
per-event assertion passes for the fourteen events someone remembered and says
nothing about the fifteenth.
"""
from __future__ import annotations

import json

import pytest

from app.auth.cookies import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE, REFRESH_PATH
from app.extensions import db
from app.models import SecurityEvent
from app.security import redact
from app.services import security_events as events
from test_t07_refresh_rotation import KEY, csrf_headers, refresh
from test_t07_signup_login import EMAIL, PASSWORD, login, signup


@pytest.fixture()
def client(anonymous_client, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", KEY)
    monkeypatch.setenv("IP_HASH_SECRET", "synthetic-ip-hash-key-not-a-real-secret")
    return anonymous_client


def recorded() -> list[SecurityEvent]:
    return db.session.scalars(db.select(SecurityEvent).order_by(SecurityEvent.id)).all()


def types() -> list[str]:
    return [row.event_type for row in recorded()]


# ---------------------------------------------------------------------------
# Where events are written
# ---------------------------------------------------------------------------

def test_signup_and_login_are_recorded(client):
    signup(client)
    login(client)
    assert types() == [events.SIGNUP_SUCCESS, events.LOGIN_SUCCESS]


def test_a_failed_login_is_recorded_without_saying_whose(client):
    """The row exists so the shape of the traffic is visible. It must not
    double as a list of addresses somebody tried."""
    signup(client)
    client.post("/api/auth/login", json={"email": EMAIL, "password": "wrong-" + PASSWORD})

    failures = [row for row in recorded() if row.event_type == events.LOGIN_FAILURE]
    assert len(failures) == 1
    assert failures[0].user_id is None
    assert failures[0].detail == {}


def test_a_duplicate_signup_is_recorded_without_the_address(client):
    signup(client)
    assert signup(client).status_code == 409
    assert types()[-1] == events.SIGNUP_DUPLICATE
    assert EMAIL not in json.dumps([row.detail for row in recorded()])


def test_logout_and_rotation_are_recorded(client):
    signup(client)
    login(client)
    refresh(client)
    client.post("/api/auth/logout", json={}, headers=csrf_headers(client))

    assert types() == [
        events.SIGNUP_SUCCESS,
        events.LOGIN_SUCCESS,
        events.REFRESH_TOKEN_ROTATED,
        events.LOGOUT,
    ]


def test_the_session_is_named_so_a_revocation_can_be_traced(client):
    """A logout row with no session id cannot answer "which one?" for an
    account signed in on three devices."""
    signup(client)
    login(client)
    client.post("/api/auth/logout", json={}, headers=csrf_headers(client))

    logout_row = recorded()[-1]
    assert logout_row.session_id is not None
    assert logout_row.user_id is not None


def test_an_audit_failure_does_not_fail_the_request(client, monkeypatch):
    """The trail is worth having and is not worth a 500.

    An audit write that can deny service is a denial-of-service switch wired to
    the least reliable part of the system. The request succeeds; the failure
    goes to the process log as text, without the row.
    """
    signup(client)

    def explode(*_args, **_kwargs):
        raise RuntimeError("synthetic audit failure")

    # Patched inside the event module rather than on the session, so the break
    # is the audit write and not every write the request makes.
    monkeypatch.setattr(events, "SecurityEvent", explode)

    assert login(client).status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    # And nothing was written, so this is not passing because the patch missed.
    assert types() == [events.SIGNUP_SUCCESS]


# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------

def _drive_every_path(client) -> dict[str, str]:
    """Walk every code path that writes an event. Returns the live secrets."""
    signup(client)
    signup(client)  # duplicate
    client.post("/api/auth/login", json={"email": EMAIL, "password": "wrong-" + PASSWORD})
    login(client)

    access = client.get_cookie(ACCESS_COOKIE).value
    csrf = client.get_cookie(CSRF_COOKIE).value
    stolen = client.get_cookie(REFRESH_COOKIE, path=REFRESH_PATH).value

    refresh(client)  # rotation
    successor = client.get_cookie(REFRESH_COOKIE, path=REFRESH_PATH).value

    # Replay the spent token: reuse detection.
    client.set_cookie(REFRESH_COOKIE, stolen, path=REFRESH_PATH)
    client.post("/api/auth/refresh", json={}, headers={"X-CSRF-Token": csrf})

    return {
        "password": PASSWORD,
        "email": EMAIL,
        "access token": access,
        "refresh token": stolen,
        "successor token": successor,
        "csrf token": csrf,
        "signing key": KEY,
    }


def test_no_secret_reaches_the_audit_trail(client):
    """The check the design asks for: drive everything, then read everything.

    Written as a sweep of the whole table rather than as an assertion per event.
    A per-event check passes for the events someone remembered to write it for,
    and the failure this is guarding against is the one nobody thought of.
    """
    secrets = _drive_every_path(client)
    rows = recorded()
    assert len(rows) >= 5, "the walk did not reach the paths this is meant to sweep"

    dumped = json.dumps(
        [
            {
                "type": row.event_type,
                "result": row.result,
                "userId": row.user_id,
                "sessionId": row.session_id,
                "ipHash": row.ip_hash,
                "detail": row.detail,
            }
            for row in rows
        ],
        ensure_ascii=False,
    )

    for name, value in secrets.items():
        assert value not in dumped, f"the audit trail contains the {name}"

    # And no password hash, under either spelling of the column.
    assert "$argon2" not in dumped
    for forbidden in ("password", "passwordHash", "token", "authorization", "cookie"):
        assert f'"{forbidden}"' not in dumped


def test_the_address_is_stored_only_as_a_hash(client):
    """C131. Recognising a repeat visitor does not require being able to name
    one, and a leaked table should not be a visitor log."""
    address = "203.0.113.77"
    client.environ_base["REMOTE_ADDR"] = address
    signup(client)

    row = recorded()[-1]
    assert row.ip_hash == redact.hash_ip(address)
    assert address not in json.dumps([row.ip_hash, row.detail], ensure_ascii=False)
    assert len(row.ip_hash) == 64


def test_a_forwarded_address_is_taken_from_the_right_end(client):
    """Behind Render's proxy the client address is in X-Forwarded-For.

    The rightmost entry is the one our proxy added; everything to its left was
    supplied by the caller. Trusting the leftmost lets anyone spread their
    attempts over unlimited fake addresses, which defeats the throttle this
    field feeds.
    """
    client.environ_base["REMOTE_ADDR"] = "10.0.0.1"
    signup(client, headers={"X-Forwarded-For": "198.51.100.9, 203.0.113.5"})

    assert recorded()[-1].ip_hash == redact.hash_ip("203.0.113.5")
