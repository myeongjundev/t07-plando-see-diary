"""Signup and login. T07-C94, C95, C98, C99.

Session cookies arrive in step 4; what is fixed here is who may create an
account, and that a failed login says the same thing however it failed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from app import create_app
from app.extensions import db
from app.models import User

EMAIL = "synthetic-user@example.invalid"
PASSWORD = "합성-비밀번호-9f2a"
JSON = {"Content-Type": "application/json"}


def signup(client, email=EMAIL, password=PASSWORD, **kwargs):
    return client.post("/api/auth/signup", json={"email": email, "password": password}, **kwargs)


def login(client, email=EMAIL, password=PASSWORD, **kwargs):
    return client.post("/api/auth/login", json={"email": email, "password": password}, **kwargs)


def test_c94_signup_creates_account(client, app):
    response = signup(client)
    assert response.status_code == 201
    body = response.get_json()["user"]
    assert body["email"] == EMAIL
    assert "id" in body
    # Nothing secret comes back, under any spelling.
    assert set(body) == {"id", "email", "createdAt"}
    with app.app_context():
        stored = db.session.scalar(db.select(User).where(User.email == EMAIL))
        assert stored is not None
        assert stored.password_hash.startswith("$argon2id$")
        assert PASSWORD not in stored.password_hash


def test_c95_login_with_created_account(client):
    signup(client)
    response = login(client)
    assert response.status_code == 200
    assert response.get_json()["user"]["email"] == EMAIL


def test_c98_duplicate_signup_rejected(client, app):
    assert signup(client).status_code == 201
    again = signup(client)
    assert again.status_code == 409
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(User)) == 1


def test_c98_duplicate_is_decided_by_the_database_not_a_prior_read(tmp_path):
    """Two simultaneous signups for one address must produce one account.

    A SELECT-then-INSERT passes the single-threaded test above and still creates
    both rows here, because both reads happen before either write. The unique
    index is the only thing that can decide it.

    A file-backed database, not the in-memory one the other tests use: SQLite
    in memory is served from a single shared connection, so four threads on it
    measure the pool rather than the constraint.
    """
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'signup.db').as_posix()}",
    })
    try:
        with app.app_context():
            db.create_all()
        barrier = Barrier(4)

        def attempt(_):
            with app.test_client() as worker:
                barrier.wait(timeout=10)
                return worker.post("/api/auth/signup", json={"email": EMAIL, "password": PASSWORD})

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(attempt, range(4)))

        assert sorted(r.status_code for r in results) == [201, 409, 409, 409]
        with app.app_context():
            assert db.session.scalar(db.select(db.func.count()).select_from(User)) == 1
    finally:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()


def test_address_is_stored_and_matched_in_one_normalized_form(client, app):
    """Uniqueness is only as good as there being one spelling in the column."""
    assert signup(client, email="Mixed.Case@Example.Invalid").status_code == 201
    with app.app_context():
        stored = db.session.scalar(db.select(User))
        assert stored.email == "mixed.case@example.invalid"
    # The same address in another casing is the same account, on both paths.
    assert signup(client, email="MIXED.CASE@example.invalid").status_code == 409
    assert login(client, email="mixed.CASE@Example.Invalid").status_code == 200


def test_c99_same_message_and_status_for_both(client):
    """A wrong password and an unregistered address are one answer.

    Compared field by field rather than eyeballed: a difference in the details
    object or the status is the same leak as a difference in the sentence.
    """
    signup(client)
    wrong_password = login(client, password="틀린-비밀번호-1234")
    no_such_account = login(client, email="absent@example.invalid")

    assert wrong_password.status_code == no_such_account.status_code == 401
    assert wrong_password.get_json() == no_such_account.get_json()
    assert wrong_password.get_json()["error"]["message"] == "이메일 또는 비밀번호가 올바르지 않습니다."
    # A malformed address must not be distinguishable from an unregistered one
    # either, or the same list can be built one rejection at a time.
    malformed = login(client, email="not-an-address")
    assert malformed.status_code == 401
    assert malformed.get_json() == no_such_account.get_json()


def test_login_failure_never_echoes_the_password(client):
    signup(client)
    response = login(client, password="틀린-비밀번호-1234")
    assert "틀린-비밀번호-1234" not in response.get_data(as_text=True)


def test_signup_rejects_a_password_below_the_floor(client):
    response = signup(client, password="짧다")
    assert response.status_code == 400
    assert "password" in response.get_json()["error"]["details"]


def test_signup_rejects_a_malformed_address(client):
    for bad in ("no-at-sign", "two@@example.invalid", "spaced out@example.invalid", ""):
        assert signup(client, email=bad).status_code == 400


def test_signup_and_login_require_a_json_content_type(client):
    """A cross-site form POST cannot set this header without a preflight."""
    for path in ("/api/auth/signup", "/api/auth/login"):
        response = client.post(path, data="email=a@b.co&password=12345678",
                               content_type="application/x-www-form-urlencoded")
        assert response.status_code == 415


def test_a_foreign_origin_is_refused(client):
    response = client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403


def test_the_deployments_own_origin_is_accepted(client):
    signup(client)
    response = client.post(
        "/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers={"Origin": "http://localhost"},
    )
    assert response.status_code == 200


def test_an_extra_origin_can_be_configured_for_the_dev_server(monkeypatch):
    """The Vite dev server runs on another port and must be able to log in."""
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:5173")
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context():
        db.create_all()
        client = app.test_client()
        try:
            assert signup(client).status_code == 201
            response = client.post(
                "/api/auth/login",
                json={"email": EMAIL, "password": PASSWORD},
                headers={"Origin": "http://localhost:5173"},
            )
            assert response.status_code == 200
        finally:
            db.session.remove()
            db.drop_all()
            db.engine.dispose()


def test_a_request_without_an_origin_is_allowed(client):
    """curl and the evidence script have to keep working.

    Browsers attach Origin to every cross-site state-changing request, so its
    absence is not the case CSRF defence is aimed at -- and T07-C129 needs a
    recorded request-and-response pair that something has to be able to make.
    """
    signup(client)
    assert login(client).status_code == 200
