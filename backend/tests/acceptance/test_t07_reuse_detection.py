"""Refresh token reuse detection. Step 14; design section 4.

A rotated token coming back means it was copied between then and now. There is
no way to tell whether the request in hand is the thief or the victim, so both
lose: every session descended from that login is revoked.

The point being tested is that revocation reaches the *successor* -- the token
the attacker walked away with. Killing only the replayed row would leave that
one working, which is the failure mode rotation exists to close.
"""
from __future__ import annotations

import pytest

from app.auth.cookies import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE, REFRESH_PATH
from app.extensions import db
from app.models import RefreshSession, SecurityEvent
from app.services import security_events as events
from app.services.sessions import REUSE, ROTATED
from test_t07_refresh_rotation import KEY, csrf_headers, logged_in, refresh


@pytest.fixture()
def client(anonymous_client, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", KEY)
    return anonymous_client


def stolen(client):
    """Log in, keep a copy of the refresh token, then rotate it.

    Afterwards the client holds the successor and `copy` is the spent token --
    exactly what an attacker who read the cookie a moment before rotation has.
    """
    logged_in(client)
    copy = client.get_cookie(REFRESH_COOKIE, path=REFRESH_PATH).value
    assert refresh(client).status_code == 200
    return copy


def replay(client, token):
    """Send the spent token from a caller that has the current CSRF value.

    The CSRF cookie is not a credential and survives rotation, so an attacker
    holding a stolen refresh cookie holds a usable one too. Sending it here is
    what makes this a test of reuse detection rather than of CSRF.
    """
    csrf = client.get_cookie(CSRF_COOKIE).value
    client.set_cookie(REFRESH_COOKIE, token, path=REFRESH_PATH)
    return client.post("/api/auth/refresh", json={}, headers={"X-CSRF-Token": csrf})


def test_replaying_a_rotated_token_revokes_the_whole_family(client):
    copy = stolen(client)
    live_before = db.session.scalars(
        db.select(RefreshSession).where(RefreshSession.revoked_at.is_(None))
    ).all()
    assert len(live_before) == 1  # the successor

    assert replay(client, copy).status_code == 401

    db.session.expire_all()
    rows = db.session.scalars(db.select(RefreshSession)).all()
    assert len(rows) == 2
    # Nothing survives. The successor is revoked as `reuse` even though it was
    # never itself replayed -- it is the token the attacker is holding.
    assert all(row.revoked_at is not None for row in rows)
    assert sorted(row.revoked_reason for row in rows) == [REUSE, ROTATED]


def test_the_successor_stops_working_immediately(client):
    """The half of the family that matters, checked by using it rather than
    by reading a column."""
    copy = stolen(client)
    assert client.get("/api/auth/me").status_code == 200

    replay(client, copy)

    # The access token is still signed and unexpired. It gets nothing, because
    # the guard reads the session row its `sid` names (T07-C114).
    assert client.get("/api/auth/me").status_code == 401


def test_a_second_login_is_a_different_family_and_survives(client):
    """Revocation is per login, not per account.

    Signing in on a phone must not be ended by a replay against the laptop's
    family. Getting this wrong turns one stolen cookie into a logout for every
    device the user owns, which nothing in the criteria asks for.
    """
    copy = stolen(client)
    families_before = {
        row.family_id for row in db.session.scalars(db.select(RefreshSession)).all()
    }

    # A second, independent login for the same account.
    other = client.application.test_client()
    from test_t07_signup_login import login as sign_in

    assert sign_in(other).status_code == 200
    db.session.expire_all()
    second = db.session.scalars(
        db.select(RefreshSession).where(RefreshSession.family_id.not_in(families_before))
    ).all()
    assert len(second) == 1

    assert replay(client, copy).status_code == 401

    db.session.expire_all()
    assert db.session.get(RefreshSession, second[0].id).revoked_at is None
    assert other.get("/api/auth/me").status_code == 200


def test_an_unknown_token_revokes_nothing(client):
    """A random string is not evidence of anything.

    If it took the family down, anyone who could reach the endpoint could log
    out any account by guessing -- a denial of service built out of the defence.
    """
    logged_in(client)
    live = db.session.scalar(db.select(RefreshSession))

    assert replay(client, "synthetic-token-that-was-never-issued").status_code == 401

    db.session.expire_all()
    assert db.session.get(RefreshSession, live.id).revoked_at is None


def test_a_logout_race_is_not_treated_as_a_replay(client):
    """Logging out with a refresh in flight must not look like theft.

    The loser of the row claim reads *why* the row died. Only `rotated` means
    the token was spent for a successor; `logout` means someone deliberately
    ended the session, possibly in another tab a moment ago. Treating that as an
    attack would file a security event every time a user closes a tab.
    """
    logged_in(client)
    token = client.get_cookie(REFRESH_COOKIE, path=REFRESH_PATH).value
    csrf = client.get_cookie(CSRF_COOKIE).value
    assert client.post("/api/auth/logout", json={}, headers={"X-CSRF-Token": csrf}).status_code == 200

    client.set_cookie(REFRESH_COOKIE, token, path=REFRESH_PATH)
    client.set_cookie(CSRF_COOKIE, csrf)
    assert client.post("/api/auth/refresh", json={}, headers={"X-CSRF-Token": csrf}).status_code == 401

    db.session.expire_all()
    rows = db.session.scalars(db.select(RefreshSession)).all()
    assert [row.revoked_reason for row in rows] == ["logout"]
    assert _events_of(events.REFRESH_TOKEN_REUSE_DETECTED) == []


def _events_of(event_type: str) -> list[SecurityEvent]:
    return db.session.scalars(
        db.select(SecurityEvent).where(SecurityEvent.event_type == event_type)
    ).all()


def test_detection_is_recorded_without_naming_the_token(client):
    """T07-C127 wants the event; C115 and C131 want it to carry no secret."""
    copy = stolen(client)
    replay(client, copy)

    recorded = _events_of(events.REFRESH_TOKEN_REUSE_DETECTED)
    assert len(recorded) == 1
    row = recorded[0]
    assert row.result == events.DETECTED
    assert row.user_id is not None
    # The family, which is an internal id, and nothing else. Not the token, not
    # its digest, not the address.
    assert set(row.detail) == {"familyId"}
    assert copy not in str(row.detail)
    assert row.ip_hash is None or len(row.ip_hash) == 64
