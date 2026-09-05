"""Check the guide's verifiable claims, not the user's unwritten judgment."""
from importlib.metadata import version
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
GUIDE = ROOT / "docs" / "T07-AUTH-GUIDE.md"
T06_COMMIT = "4f3ed709d75c573beac7fc95e700c7719b53087c"


def test_c92_guide_versions_match_installed():
    content = GUIDE.read_text(encoding="utf-8")
    rows = dict(re.findall(r"^\| ([\w-]+) \| ([0-9][\w.]+) \|", content, re.M))
    expected = {"argon2-cffi", "PyJWT", "Flask", "Flask-SQLAlchemy", "SQLAlchemy",
                "Flask-Migrate", "alembic", "psycopg", "waitress"}
    assert expected <= rows.keys()
    for package in expected:
        assert rows[package] == version(package), package


def test_c127_guide_has_six_sections():
    content = GUIDE.read_text(encoding="utf-8")
    sections = re.findall(r"^## ([①②③④⑤⑥]) (.+)\n([\s\S]*?)(?=^## |\Z)", content, re.M)
    assert [item[0] for item in sections] == list("①②③④⑤⑥")
    assert all(body.strip() for _, _, body in sections)


def test_c77_c78_t06_commit_is_ancestor():
    for name in ("T07-AUTH-GUIDE.md", "T07-SUBMISSION.md"):
        assert T06_COMMIT in (ROOT / "docs" / name).read_text(encoding="utf-8")
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", T06_COMMIT, "HEAD"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
