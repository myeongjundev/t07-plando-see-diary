from __future__ import annotations

import os
from pathlib import Path


def normalize_database_url(configured: str) -> str:
    """Name the driver this project actually installs.

    Hosted providers hand out `postgres://` or `postgresql://`, and SQLAlchemy
    reads both as "use psycopg2" -- which is not what is in pyproject. The
    failure is a `ModuleNotFoundError` for a package nobody chose, which reads
    as a broken environment rather than as a URL that needs one word changed.

    Public because the tests take a connection string from their own variable
    and would otherwise need their own copy of this rule.
    """
    for prefix in ("postgres://", "postgresql://"):
        if configured.startswith(prefix):
            return "postgresql+psycopg://" + configured[len(prefix):]
    return configured


def database_url() -> str:
    configured = os.getenv("DATABASE_URL")
    if configured:
        return normalize_database_url(configured)

    instance_dir = Path(__file__).resolve().parents[1] / "instance"
    instance_dir.mkdir(exist_ok=True)
    return f"sqlite:///{(instance_dir / 't06.db').as_posix()}"


class Config:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Check cached connections on use, including after the hosted DB sleeps.
    # This does not issue any background queries.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    JSON_SORT_KEYS = False
    MAX_CONTENT_LENGTH = 1_048_576
    STATIC_DIST = str(Path(__file__).resolve().parents[2] / "frontend" / "dist")

