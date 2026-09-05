"""Regression checks for the T06-to-T07 production migration."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "a1c7d9e40b52_add_accounts_and_ownership.py"
)
SPEC = spec_from_file_location("t07_accounts_migration", MIGRATION_PATH)
MIGRATION = module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MIGRATION)


def test_reflection_foreign_keys_use_postgres_deployed_names():
    names = MIGRATION._reflection_foreign_key_names(
        [
            {
                "name": "reflections_plan_id_fkey",
                "constrained_columns": ["plan_id"],
            },
            {
                "name": "reflections_next_plan_id_fkey",
                "constrained_columns": ["next_plan_id"],
            },
        ]
    )

    assert names[("plan_id",)] == "reflections_plan_id_fkey"
    assert names[("next_plan_id",)] == "reflections_next_plan_id_fkey"


def test_reflection_foreign_keys_keep_sqlite_batch_fallbacks():
    names = MIGRATION._reflection_foreign_key_names(
        [
            {"name": None, "constrained_columns": ["plan_id"]},
            {"name": None, "constrained_columns": ["next_plan_id"]},
        ]
    )

    assert names[("plan_id",)] == "fk_reflections_plan_id_plans"
    assert names[("next_plan_id",)] == "fk_reflections_next_plan_id_plans"


def test_reflection_foreign_keys_fail_closed_when_legacy_shape_is_missing():
    with pytest.raises(RuntimeError, match="next_plan_id"):
        MIGRATION._reflection_foreign_key_names(
            [{"name": "reflections_plan_id_fkey", "constrained_columns": ["plan_id"]}]
        )
