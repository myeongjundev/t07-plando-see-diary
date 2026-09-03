"""The masking function, on its own. T07-C115, C131.

`test_t07_security_events.py` sweeps the audit trail for secrets, which is the
check that matters. This file is about the function that sweep depends on, so
that when it does fail there is something smaller to read than a whole request.

The rule the module follows, and the reason for it: a value is masked by the
name of its key, not by looking like a secret. Pattern-matching finds the values
that look the part and misses a four-character password, and a key called
`password` is a password whatever it happens to hold today.
"""
from __future__ import annotations

import pytest

from app.security import redact


@pytest.mark.parametrize(
    "key",
    [
        "password", "new_password", "currentPassword", "password_hash",
        "passwordHash", "token", "accessToken", "refresh_token", "csrfToken",
        "jwt", "jwt_secret", "Authorization", "cookie", "apiKey", "credentials",
    ],
)
def test_a_secret_key_never_keeps_its_value(key):
    assert redact.redact({key: "synthetic-secret-value"}) == {key: redact.MASK}


def test_masking_reaches_nested_values():
    """A secret one level down is still a secret.

    The thing being logged is usually a dict of dicts, and a masker that only
    looks at the top level is one that works until the first caller passes a
    request payload.
    """
    masked = redact.redact({
        "outer": {"inner": {"password": "synthetic", "keep": "visible"}},
        "list": [{"token": "synthetic"}, "plain"],
    })
    assert masked["outer"]["inner"] == {"password": redact.MASK, "keep": "visible"}
    assert masked["list"] == [{"token": redact.MASK}, "plain"]


def test_an_address_is_hashed_and_renamed():
    """Not masked -- hashed. "The same visitor as last time" is the whole point
    of recording it, and a constant string cannot say that.

    Renamed too, so nothing downstream reads a digest out of a field called `ip`
    and prints it as an address.
    """
    masked = redact.redact({"ip": "203.0.113.5"})
    assert "ip" not in masked
    assert masked["ipHash"] == redact.hash_ip("203.0.113.5")
    assert "203.0.113.5" not in str(masked)


def test_the_same_address_written_two_ways_hashes_the_same():
    """`::ffff:203.0.113.5` and `203.0.113.5` are one client.

    Without canonicalisation they hash differently, and anyone whose requests
    arrive both ways gets twice the rate limit.
    """
    assert redact.hash_ip("::ffff:203.0.113.5") == redact.hash_ip("203.0.113.5")
    assert redact.hash_ip(" 203.0.113.5 ") == redact.hash_ip("203.0.113.5")
    assert redact.hash_ip("2001:db8::1") != redact.hash_ip("203.0.113.5")


def test_an_unparseable_address_is_still_a_stable_key(monkeypatch):
    """A malformed value keys consistently rather than merging with others.

    Mapping everything unparseable onto one value would let a caller sending
    junk share a throttle bucket with every other caller sending junk -- and
    with each other, which is worse than useless.
    """
    monkeypatch.setenv("IP_HASH_SECRET", "synthetic-ip-hash-key")
    assert redact.hash_ip("not-an-address") == redact.hash_ip("not-an-address")
    assert redact.hash_ip("not-an-address") != redact.hash_ip("also-not-an-address")


def test_the_key_is_what_makes_the_hash_unguessable(monkeypatch):
    """IPv4 is 2^32 values: an unkeyed digest of an address is reversible by
    brute force in seconds, so a plain SHA-256 would not protect anything."""
    monkeypatch.setenv("IP_HASH_SECRET", "synthetic-key-one")
    first = redact.hash_ip("203.0.113.5")
    monkeypatch.setenv("IP_HASH_SECRET", "synthetic-key-two")
    assert redact.hash_ip("203.0.113.5") != first


def test_production_refuses_a_per_process_key(monkeypatch):
    """A fallback key makes the throttle look like it works.

    It counts, it locks, and then Render Free wakes the instance and every
    counter is a stranger again -- which is the memory-based throttle the design
    rejected, wearing a database's clothes.
    """
    monkeypatch.delenv("IP_HASH_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="IP_HASH_SECRET"):
        redact.require_ip_secret()


def test_an_object_is_described_rather_than_serialised():
    """repr() of a model instance is how a password hash reaches a log."""

    class Account:
        def __repr__(self):  # pragma: no cover - must never be called
            return "Account(password_hash='$argon2id$synthetic')"

    assert redact.redact({"user": Account()}) == {"user": "[Account]"}


def test_deep_and_long_values_are_cut_off():
    """An audit row describes an event. Something needing six levels or five
    hundred characters to describe is a payload about to be stored by accident.
    """
    deep = current = {}
    for _ in range(10):
        current["next"] = {}
        current = current["next"]
    assert "[truncated]" in str(redact.redact(deep))

    long_value = redact.redact({"note": "x" * 900})["note"]
    assert len(long_value) == redact.MAX_STRING + 1
    assert long_value.endswith("…")
