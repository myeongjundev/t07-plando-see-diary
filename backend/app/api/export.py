from flask import jsonify

from app.api import api
from app.auth.guards import login_required
from app.services.export import export_all
from app.services.ownership import current_user_id


@api.get("/export")
@login_required
def download_export():
    # The user id comes from the session, never from the request. An export that
    # took a parameter would be one guessed id away from being someone else's
    # diary in a file (T07-C123, T07-C133).
    response = jsonify(export_all(current_user_id()))
    response.headers["Content-Disposition"] = 'attachment; filename="t06-diary-v2.json"'
    response.headers["Cache-Control"] = "no-store"
    return response
