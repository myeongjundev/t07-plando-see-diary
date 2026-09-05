"""What the evidence files must be true of. T07-C105, C106, C115, C129, C131.

These read `docs/T07-EVIDENCE/` rather than producing it. The producing is
`backend/scripts/collect_auth_evidence.py`, and the split is the point: a script
that also judged its own output would only ever agree with itself.

Two of these are absence checks, and absence is the kind of claim that is easy
to state and hard to hold. They are written to fail loudly on a file that
somebody edited by hand and forgot to mask, which is the realistic way a secret
gets into a submission.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs" / "T07-EVIDENCE"
DOCS = ROOT / "docs"

# The files design section 10 promises. `00-*` is the hash benchmark, which is
# measured on the deployed instance rather than produced by the script.
COLLECTED = sorted(EVIDENCE.glob("[01][0-9]-*.md")) if EVIDENCE.exists() else []
GENERATED = [path for path in COLLECTED if not path.name.startswith("00-")]

# Values the collector uses. They are synthetic and exist only to be refused --
# and none of them may survive into the output.
SYNTHETIC_SECRETS = (
    "합성-증거-계정A-7f21",
    "합성-증거-계정B-4c98",
    "합성-같은-비밀번호-9d33",
    "합성-틀린-비밀번호-0000",
)

# A JWT, a hex digest long enough to be a token or a hash, and an argon2 hash.
# Deliberately shape-based: this is the check that catches a value nobody
# thought to name.
TOKEN_SHAPES = (
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"\$argon2(?:id|i|d)\$[^\s`]{20,}"),
    re.compile(r"\b[0-9a-f]{32,}\b"),
    re.compile(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{20,}"),
)

skip_without_evidence = pytest.mark.skipif(
    not GENERATED,
    reason="run backend/scripts/collect_auth_evidence.py to produce docs/T07-EVIDENCE",
)


@skip_without_evidence
def test_c129_each_evidence_file_has_success_and_denial():
    """Every file shows the thing working and the thing refused.

    A file of refusals alone does not show the feature exists; a file of
    successes alone does not show anything is guarded. C129 asks for the pair,
    five confirmations over, so it is checked per file rather than in total --
    a run where one file carried both and another carried neither would pass a
    global count and fail the criterion.
    """
    for path in GENERATED:
        codes = [int(code) for code in re.findall(r"^(\d{3}) ", path.read_text(encoding="utf-8"), re.M)]
        successes = [code for code in codes if 200 <= code < 300]
        denials = [code for code in codes if 400 <= code < 500]
        assert successes, f"{path.name}: no success recorded"
        assert denials, f"{path.name}: no refusal recorded"


@skip_without_evidence
def test_c115_evidence_files_contain_no_token():
    """No token, session id, hash or digest survives into the evidence.

    Matched on shape, not on a list of known values. A check that only looked
    for the strings this run happened to use would pass a file carrying a token
    from some other run, which is exactly the file nobody would notice.
    """
    for path in GENERATED:
        text = path.read_text(encoding="utf-8")
        for shape in TOKEN_SHAPES:
            found = shape.findall(text)
            assert not found, f"{path.name}: token-shaped value ({shape.pattern})"
        # And the cookie values themselves are named but never shown.
        assert "pds_access=ey" not in text
        assert re.search(r"pds_\w+=(?!\[redacted\])[A-Za-z0-9_-]{8,}", text) is None, path.name


@skip_without_evidence
def test_c105_c106_no_plaintext_anywhere():
    """No password the collector typed comes back out of it.

    C105 is about the record of a login and C106 about logs, screens and
    responses. What is checkable here is the recorded half: the request bodies,
    the response bodies and the audit-trail summary all went through `redact`,
    and this is the check that says so about the actual bytes.
    """
    for path in GENERATED:
        text = path.read_text(encoding="utf-8")
        for secret in SYNTHETIC_SECRETS:
            assert secret not in text, f"{path.name}: plaintext password"


@skip_without_evidence
def test_the_password_field_is_masked_rather_than_omitted():
    """The masking has to be visible, or the check above passes on an empty file.

    An absence test alone cannot tell "we masked it" from "we never recorded a
    login at all". At least one file must show a password field, redacted.
    """
    signup = EVIDENCE / "01-signup-login-logout.md"
    text = signup.read_text(encoding="utf-8")
    assert '"password": "[redacted]"' in text


def test_c131_no_secret_in_docs():
    """Nothing in `docs/` carries a secret in plaintext, evidence or otherwise.

    Wider than the evidence folder on purpose: the submission is the whole
    directory, and a value pasted into a design note counts against C131 exactly
    as much as one in an evidence file.

    The runbook is excluded from the token-shape sweep for the one reason a
    document legitimately contains hash-shaped text: it documents the *format*
    of stored hashes. Its contents are checked for real secrets instead.
    """
    for path in sorted(DOCS.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for secret in SYNTHETIC_SECRETS:
            assert secret not in text, f"{path.relative_to(ROOT)}: plaintext password"
        assert "JWT_SECRET=" not in text.replace("JWT_SECRET=...", ""), path.name
        if "hash-bench" in path.name:
            continue
        for shape in TOKEN_SHAPES[:2]:  # JWT and argon2, which are unambiguous
            assert not shape.findall(text), f"{path.relative_to(ROOT)}: {shape.pattern}"


@skip_without_evidence
def test_every_promised_evidence_file_exists():
    """Design section 10 lists eleven. A missing one is a criterion with no record."""
    expected = {
        "01-signup-login-logout.md",
        "02-password-storage.md",
        "03-logout-replay-blocked.md",
        "04-refresh-rotation.md",
        "05-refresh-reuse-detected.md",
        "06-csrf-blocked.md",
        "07-bruteforce-blocked.md",
        "08-cross-user-access-blocked.md",
        "09-session-expiration.md",
        "10-security-events.md",
        "11-totals.md",
    }
    assert expected <= {path.name for path in GENERATED}


@skip_without_evidence
def test_logout_evidence_replays_credentials_instead_of_anonymous_request():
    text = (EVIDENCE / "03-logout-replay-blocked.md").read_text(encoding="utf-8")
    requests = re.findall(r"GET /api/auth/me\nCookie: ([^\n]+)", text)
    assert len(requests) == 2
    assert requests[0] == requests[1]
    assert "access=[redacted]" in requests[1]
    assert re.findall(r"^(\d{3}) [A-Z ]+$", text, re.M) == ["200", "200", "401"]


@skip_without_evidence
def test_cross_account_deletion_evidence_reaches_ownership_guard():
    text = (EVIDENCE / "08-cross-user-access-blocked.md").read_text(encoding="utf-8")
    sections = re.split(r"^### ", text, flags=re.M)
    deletes = [section for section in sections if "DELETE /api/tasks/" in section]
    assert len(deletes) == 2
    for section in deletes:
        assert "Content-Type: application/json" in section
        assert "X-CSRF-Token: [redacted]" in section
        assert "404 NOT FOUND" in section
        assert "415 UNSUPPORTED MEDIA TYPE" not in section
        assert "refresh=[redacted]" not in section  # Cookie Path excludes task routes.


@skip_without_evidence
def test_c132_screen_totals_match_hand_sum():
    """The totals file adds up, read back from what it wrote.

    Parsed rather than eyeballed: the file prints a per-day table and a pair of
    totals, and the criterion is that the second follows from the first. A
    summary that drifted from its own rows would still look right.
    """
    text = (EVIDENCE / "11-totals.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| +\d+ \| [\d-]+ \| +(\d+) \| +(\d+) \|", text, re.M)
    assert rows, "no day rows in 11-totals.md"
    estimated = sum(int(row[0]) for row in rows)
    actual = sum(int(row[1]) for row in rows)

    printed_actual = re.search(r"실제 합계: 손 \*\*(\d+)분\*\* · 화면 \*\*(\d+)분\*\*", text)
    printed_estimated = re.search(r"예상 합계: 손 \*\*(\d+)분\*\* · 화면 \*\*(\d+)분\*\*", text)
    assert printed_actual and printed_estimated

    assert int(printed_actual[1]) == int(printed_actual[2]) == actual
    assert int(printed_estimated[1]) == int(printed_estimated[2]) == estimated
