import sqlite3

from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
migrate = Migrate()


@event.listens_for(Engine, "connect")
def _enforce_sqlite_foreign_keys(connection, _record):
    """Make SQLite behave like the engine that is deployed.

    SQLite parses `ON DELETE CASCADE` and then ignores it unless
    `PRAGMA foreign_keys` is on, which is off by default. Without this the whole
    test suite runs against a database that silently permits what PostgreSQL
    refuses: account deletion leaves every plan behind, `SET NULL` on
    `security_events.user_id` never fires, and a missing or wrong `ondelete`
    would first be seen in production.

    Production is PostgreSQL and never reaches this branch. The pragma is
    per-connection, so it is set on connect rather than once at startup.
    """
    if isinstance(connection, sqlite3.Connection):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
