"""Rehearse the boot that repoints the deployed service at T07.

The deploy is the one step in this project with no undo: it runs once, against
the real database, unattended, and the T06 diary is in there. Everything else
can be re-run.

What is checked here is the sequence `deploy/start.sh` performs, in the order it
performs it, starting from a database in the shape the deployed one is actually
in -- T06's last revision, with plans that have no owner. The commands are read
out of `start.sh` rather than restated, so a change to the script that this file
does not know about fails here instead of on the instance.

SQLite rather than PostgreSQL, so this proves the *ordering*, not the DDL. The
NOT NULL itself is PostgreSQL's to apply; what can go wrong in the ordering --
reaching the NOT NULL before the claim -- is engine-independent, and is exactly
what went wrong when this was written.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from flask_migrate import upgrade
from sqlalchemy import text

from app import create_app
from app.extensions import db
from legacy_rows import LEGACY_PLAN, LEGACY_TASK, seed_legacy_plan_and_task

ROOT = Path(__file__).resolve().parents[3]
START_SH = ROOT / "deploy" / "start.sh"
MIGRATIONS = str(ROOT / "backend" / "migrations")

# T06's last revision: reflections exist, accounts do not.
T06_REVISION = "b84587642a1b"
# Where the claim has to stand: `users` exists, `plans.user_id` is still nullable.
PRE_OWNERSHIP_REVISION = "a1c7d9e40b52"
# The migration that makes it NOT NULL, and refuses over unowned rows.
OWNERSHIP_REVISION = "c48b1f60a2d7"

CLAIM_EMAIL = "deploy-rehearsal@example.invalid"
CLAIM_PASSWORD = "합성-이관-비밀번호-6b2e"


def orphans() -> int:
    return db.session.execute(text("SELECT count(*) FROM plans WHERE user_id IS NULL")).scalar_one()


def current_revision() -> str:
    return db.session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


@pytest.fixture()
def deployed(tmp_path):
    """A database the shape the live one is in: T06's schema, unowned rows."""
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'deploy.db').as_posix()}",
    })
    with app.app_context():
        upgrade(directory=MIGRATIONS, revision=T06_REVISION)
        seed_legacy_plan_and_task()
        yield app
        db.session.remove()
        db.engine.dispose()


def test_start_sh_stops_short_of_the_not_null_before_claiming():
    """The script must name the pre-ownership revision, and only in that branch.

    Read out of the file rather than assumed. An unconditional `db upgrade` in
    the claim branch is the bug this whole file exists for: the boot reaches the
    NOT NULL with every T06 row still ownerless, the migration refuses, and the
    deploy dies before the claim it was supposed to run.
    """
    script = START_SH.read_text(encoding="utf-8")
    assert PRE_OWNERSHIP_REVISION in script, "start.sh no longer names the pre-ownership revision"

    claim_branch = script.split("claim_t06_data)", 1)[1].split(";;", 1)[0]
    assert "$MIGRATE \"$PRE_OWNERSHIP_REVISION\"" in claim_branch
    # And it finishes the chain afterwards, or the NOT NULL never applies at all.
    assert claim_branch.rstrip().endswith("$MIGRATE")


def test_upgrading_straight_to_head_over_unowned_rows_is_refused(deployed, capfd):
    """The failure the ordering avoids, demonstrated rather than described.

    This is what the deploy would have done: one `db upgrade`, no claim. It has
    to fail, and it has to fail saying what to do -- a bare NOT NULL error reads
    as a schema problem, and the next person goes looking in the wrong place.

    Flask-Migrate turns the migration's RuntimeError into a logged message and
    `sys.exit(1)`, which is what makes it a failed deploy: `set -e` in start.sh
    stops the boot there rather than serving an app over a half-migrated
    database.
    """
    with deployed.app_context():
        # `plans.user_id` does not exist yet at T06's revision, so there is
        # nothing to count until the accounts migration has run -- which is the
        # first thing this upgrade does before walking into the NOT NULL.
        with pytest.raises(SystemExit) as exit_code:
            upgrade(directory=MIGRATIONS)
        assert exit_code.value.code == 1
        # capfd, not caplog: Alembic configures logging itself, so the record
        # never reaches pytest's handler -- but it does reach the file
        # descriptor, which is also where Render will read it.
        assert "claim_t06_data --apply" in capfd.readouterr().err

        # It stopped at the refusal rather than half-applying past it.
        assert current_revision() == PRE_OWNERSHIP_REVISION
        assert orphans() == 1


def test_the_boot_sequence_claims_and_then_requires_an_owner(deployed, monkeypatch, capsys):
    """The three steps start.sh runs, in order, on a T06-shaped database."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "claim_t06_data", ROOT / "backend" / "scripts" / "claim_t06_data.py"
    )
    claim = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(claim)

    monkeypatch.setenv("CLAIM_PLAN_IDS", LEGACY_PLAN["id"])
    monkeypatch.setenv("CLAIM_EXCLUDE_PLAN_IDS", "")
    monkeypatch.setenv("CLAIM_EXCLUDE_TASK_IDS", "")

    with deployed.app_context():
        # 1. Up to the last revision that tolerates an unowned plan.
        upgrade(directory=MIGRATIONS, revision=PRE_OWNERSHIP_REVISION)
        assert current_revision() == PRE_OWNERSHIP_REVISION
        assert orphans() == 1

        # 2. The claim, which is what gives them an owner.
        report = claim.run(
            CLAIM_EMAIL, CLAIM_PASSWORD, [LEGACY_PLAN["id"]], [], [], apply=True
        )
        assert orphans() == 0

        # 3. The rest of the chain, including the NOT NULL that would have
        #    refused a moment ago.
        upgrade(directory=MIGRATIONS)
        assert orphans() == 0

        # The diary survived the whole thing, which is the actual point of C100.
        kept = db.session.execute(
            text("SELECT title FROM plans WHERE id = :id"), {"id": LEGACY_PLAN["id"]}
        ).scalar_one()
        assert kept == LEGACY_PLAN["title"]
        task_count = db.session.execute(
            text("SELECT count(*) FROM tasks WHERE plan_id = :id"), {"id": LEGACY_PLAN["id"]}
        ).scalar_one()
        assert task_count == 1
        assert report is not None


def test_running_the_boot_task_twice_changes_nothing(deployed, monkeypatch):
    """A redeploy with BOOT_TASK still set must be safe.

    It is one dashboard edit away from happening, and the person doing it will
    be watching a log rather than reading this. Both upgrades are no-ops on a
    database already at head, and the claim finds nothing left to claim.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "claim_t06_data", ROOT / "backend" / "scripts" / "claim_t06_data.py"
    )
    claim = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(claim)

    with deployed.app_context():
        upgrade(directory=MIGRATIONS, revision=PRE_OWNERSHIP_REVISION)
        claim.run(CLAIM_EMAIL, CLAIM_PASSWORD, [LEGACY_PLAN["id"]], [], [], apply=True)
        upgrade(directory=MIGRATIONS)
        head = current_revision()
        users = db.session.execute(text("SELECT count(*) FROM users")).scalar_one()

        # Second boot, same environment.
        upgrade(directory=MIGRATIONS, revision=PRE_OWNERSHIP_REVISION)
        claim.run(CLAIM_EMAIL, CLAIM_PASSWORD, [LEGACY_PLAN["id"]], [], [], apply=True)
        upgrade(directory=MIGRATIONS)

        assert current_revision() == head
        # One account, not two: re-running must not fork the owner.
        assert db.session.execute(text("SELECT count(*) FROM users")).scalar_one() == users
        assert orphans() == 0


def test_render_yaml_carries_the_claim_configuration():
    """The ids the claim will act on, and the secrets it must not carry.

    `render.yaml` is committed, so the two id lists are reviewable and the two
    values that must never be committed are declared `sync: false` instead. A
    password moved into this file would be a secret in Git history, which is
    the one mistake T07-C113 and C46 cannot forgive.
    """
    manifest = (ROOT / "render.yaml").read_text(encoding="utf-8")
    for key in ("CLAIM_PLAN_IDS", "CLAIM_EXCLUDE_PLAN_IDS", "CLAIM_EXCLUDE_TASK_IDS"):
        assert re.search(rf"key: {key}\s*\n\s*value:", manifest), key
    for key in ("DATABASE_URL", "CLAIM_EMAIL", "CLAIM_PASSWORD", "OBSERVATION_PLAN_ID"):
        assert re.search(rf"key: {key}\s*\n(\s*#.*\n)*\s*sync: false", manifest), key
    for key in ("JWT_SECRET", "IP_HASH_SECRET"):
        assert re.search(rf"key: {key}\s*\n(\s*#.*\n)*\s*generateValue: true", manifest), key

    # The two id lists must not overlap: a plan in both would be claimed and
    # deleted, and which one won would depend on the order of two loops.
    claimed = set(re.search(r"key: CLAIM_PLAN_IDS\s*\n\s*value: \"([^\"]*)\"", manifest)[1].split(","))
    excluded = set(
        re.search(r"key: CLAIM_EXCLUDE_PLAN_IDS\s*\n\s*value: \"([^\"]*)\"", manifest)[1].split(",")
    )
    assert not (claimed & excluded), sorted(claimed & excluded)
    assert len(claimed) == 3 and len(excluded) == 4, "the deployed snapshot had 7 plans"
