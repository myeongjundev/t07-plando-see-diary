"""Argon2id password storage. T07-C101 through T07-C107.

The scenes these have to produce are in docs/T07-ACCEPTANCE-MATRIX.md: a stored
value that is not the password, two accounts with one password stored
differently, and no plaintext anywhere a record is kept.
"""
from __future__ import annotations

import re

import pytest
from argon2 import PasswordHasher

from app.security import passwords
from app.security.passwords import (
    MAX_PASSWORD_BYTES,
    PasswordTooLong,
    hash_password,
    needs_rehash,
    verify_password,
)

# Synthetic throughout. Nothing here is or resembles a credential in use.
PASSWORD = "합성-비밀번호-테스트-9f2a"
OTHER = "다른-합성-비밀번호-1b7c"


@pytest.fixture(autouse=True)
def _fresh_hasher():
    """Settings are read once and cached, so a test that changes them must reset."""
    passwords.reset_hasher()
    yield
    passwords.reset_hasher()


def test_c103_stored_hash_is_not_the_password():
    stored = hash_password(PASSWORD)
    assert PASSWORD not in stored
    # Not a case or encoding trick either.
    assert PASSWORD.lower() not in stored.lower()
    assert stored.startswith("$argon2id$")
    assert verify_password(stored, PASSWORD)


def test_c104_same_password_two_accounts_differ():
    """Two accounts choosing the same password must not look the same in the table.

    Nothing in this project arranges that; the salt inside the encoded string
    does. The test is here because the property is what C104 asks to be shown,
    and because it would break silently if anyone ever pinned the salt.
    """
    first = hash_password(PASSWORD)
    second = hash_password(PASSWORD)
    assert first != second
    assert verify_password(first, PASSWORD)
    assert verify_password(second, PASSWORD)


def test_wrong_password_is_rejected():
    stored = hash_password(PASSWORD)
    assert not verify_password(stored, OTHER)
    assert not verify_password(stored, PASSWORD + " ")
    assert not verify_password(stored, "")


def test_c107_only_library_hashing_is_used():
    """The stored form must be argon2-cffi's, not something assembled here.

    Parsing it with a bare library hasher proves the encoded string is the
    library's own and carries its own parameters -- which is the difference
    between using the library and using a library-shaped wrapper around a
    hand-rolled scheme.
    """
    stored = hash_password(PASSWORD)
    assert PasswordHasher().verify(stored, PASSWORD)
    fields = stored.split("$")
    assert fields[1] == "argon2id"
    assert re.fullmatch(r"m=\d+,t=\d+,p=\d+", fields[3])


def test_parameters_come_from_settings_not_from_code(monkeypatch):
    """The deployed measurement must land as configuration, not as an edit.

    The cost is still unmeasured on the instance that matters. When the number
    arrives it changes a setting; if that stopped working, the change would have
    to be made in code and the default would silently stay.
    """
    monkeypatch.setenv("ARGON2_TIME_COST", "3")
    monkeypatch.setenv("ARGON2_MEMORY_KIB", "20480")
    monkeypatch.setenv("ARGON2_PARALLELISM", "2")
    passwords.reset_hasher()
    assert passwords.current_parameters() == {"time_cost": 3, "memory_cost": 20480, "parallelism": 2}
    assert "m=20480,t=3,p=2" in hash_password(PASSWORD)


def test_defaults_are_the_owasp_minimum_until_the_instance_is_measured(monkeypatch):
    for name in ("ARGON2_TIME_COST", "ARGON2_MEMORY_KIB", "ARGON2_PARALLELISM"):
        monkeypatch.delenv(name, raising=False)
    passwords.reset_hasher()
    assert passwords.current_parameters() == {"time_cost": 2, "memory_cost": 19456, "parallelism": 1}


def test_nonsense_settings_fail_loudly(monkeypatch):
    """A typo must stop the process, not silently hash at the default cost."""
    monkeypatch.setenv("ARGON2_MEMORY_KIB", "lots")
    passwords.reset_hasher()
    with pytest.raises(RuntimeError):
        passwords.current_parameters()
    monkeypatch.setenv("ARGON2_MEMORY_KIB", "0")
    with pytest.raises(RuntimeError):
        passwords.current_parameters()


def test_hash_from_older_parameters_still_verifies_and_asks_to_be_redone(monkeypatch):
    """Raising the cost must not lock out the accounts created before it.

    Login is the only moment the plaintext exists to redo the hash with, so the
    old hash has to keep verifying and has to be recognisable as outdated.
    """
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    passwords.reset_hasher()
    old = hash_password(PASSWORD)

    monkeypatch.setenv("ARGON2_TIME_COST", "3")
    passwords.reset_hasher()
    assert verify_password(old, PASSWORD)
    assert needs_rehash(old)
    assert not needs_rehash(hash_password(PASSWORD))


def test_a_corrupt_stored_value_is_a_failure_not_a_crash():
    """A damaged row must reject the login, not return a 500 naming the column."""
    for damaged in ("", "not-a-hash", "$argon2id$broken", PASSWORD):
        assert not verify_password(damaged, PASSWORD)
    assert not needs_rehash("not-a-hash")


def test_absurdly_long_passwords_are_refused_before_any_hashing():
    """Hashing is expensive on purpose, which makes unbounded input a weapon.

    Argon2 has no 72-byte cliff to work around, so nothing is truncated -- the
    input is refused, and refused before the cost is paid.
    """
    too_long = "가" * (MAX_PASSWORD_BYTES // 3 + 1)
    assert len(too_long.encode("utf-8")) > MAX_PASSWORD_BYTES
    with pytest.raises(PasswordTooLong):
        hash_password(too_long)
    # On the verify side it is simply not a match: no stored hash was ever made
    # from an input this long, so there is nothing for it to equal.
    assert not verify_password(hash_password(PASSWORD), too_long)


def test_a_long_but_reasonable_passphrase_is_accepted():
    """The cap must sit far above anything a person would actually type."""
    passphrase = "긴 암호문 " * 20
    assert len(passphrase.encode("utf-8")) < MAX_PASSWORD_BYTES
    assert verify_password(hash_password(passphrase), passphrase)


def test_c99_timing_does_not_leak_existence():
    """The unknown-address path must spend what the wrong-password path spends.

    Timed comparison is left out on purpose: on a shared runner it is flaky, and
    a flaky security test gets muted. What is checked is that the dummy runs a
    real verification at the current parameters -- the property the equal timing
    follows from -- rather than returning early.
    """
    passwords.warm()
    dummy = passwords._dummy_hash
    assert dummy is not None
    assert dummy.startswith("$argon2id$")
    expected = passwords.current_parameters()
    assert f"m={expected['memory_cost']},t={expected['time_cost']},p={expected['parallelism']}" in dummy
    # And it stays in step when the parameters move, which a baked-in constant
    # would not: that is the whole reason it is computed rather than hardcoded.
    assert not needs_rehash(dummy)


def test_dummy_hash_tracks_a_parameter_change(monkeypatch):
    monkeypatch.setenv("ARGON2_TIME_COST", "1")
    passwords.reset_hasher()
    passwords.warm()
    assert "t=1" in passwords._dummy_hash

    monkeypatch.setenv("ARGON2_TIME_COST", "3")
    passwords.reset_hasher()
    passwords.warm()
    assert "t=3" in passwords._dummy_hash


def test_creating_the_app_warms_the_dummy_hash():
    """Otherwise the very first unknown-address login is measurably slower."""
    passwords.reset_hasher()
    assert passwords._dummy_hash is None
    from app import create_app

    create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    assert passwords._dummy_hash is not None
