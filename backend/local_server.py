"""Run the whole app locally: API and the built frontend from one origin.

The Vite dev server proxies /api and is the right tool while writing a
component. It is the wrong tool for checking anything about sessions: cookies,
SameSite and the `__Host-` prefix all depend on the origin, and two origins
behind a proxy are not the shape the deployed app has. This serves the built
bundle and the API together, the way Render does.

    backend/.venv/Scripts/python.exe backend/local_server.py

Local only. Nothing imports it, `deploy/start.sh` does not use it, and the
signing key below is a fixed development string -- it is not a secret, and it
is not read anywhere a real one would be.
"""
from __future__ import annotations

import os
from pathlib import Path

# Set before importing the app: create_app reads them at import and build time.
os.environ.setdefault("JWT_SECRET", "local-development-signing-key-not-a-secret")
os.environ.setdefault(
    "ALLOWED_ORIGINS", "http://localhost:5099,http://127.0.0.1:5099"
)

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        # No migrations here on purpose: this is a scratch database for looking
        # at screens, and `flask db upgrade` is what the deploy runs.
        db.create_all()
    dist = Path(app.config["STATIC_DIST"])
    if not (dist / "index.html").is_file():
        raise SystemExit(f"Build the frontend first (npm run build); {dist} has no index.html.")
    app.run(host="127.0.0.1", port=5099, debug=False)
