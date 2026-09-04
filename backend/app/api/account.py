"""Deleting an account, and everything it wrote. T07-C134.

One endpoint, and almost all of its weight is in the foreign keys rather than
here: `DELETE /api/account` removes the `users` row and the database follows it
down through plans, tasks, executions, reflections, rule changes and sessions.
The actions that make that work are asserted from the metadata in
`test_t07_ownership_cascade.py`, on every run and on any engine, because SQLite
does not enforce foreign keys unless asked and a missing action would otherwise
first be seen in production.

`security_events` is the one exception, and deliberately: its `user_id` is SET
NULL rather than CASCADE. C134 wants the account's data gone; an audit log that
deletes itself with the account is no use after a breach. Cutting the column
that names the person satisfies both.
"""
from flask import jsonify, request

from app.api import api
from app.api.plans import error_response
from app.auth.cookies import clear_session
from app.auth.csrf import check_state_changing_request
from app.auth.guards import login_required
from app.extensions import db
from app.models import User
from app.services import security_events as events
from app.security.passwords import verify_password
from app.services.ownership import current_user_id


@api.delete("/account")
@login_required
def delete_account():
    """Remove the account and its data, then clear the browser's cookies.

    The password is required again, for the same reason it is on the change
    endpoint and more so: this is the one action in the application that cannot
    be undone, and a session found unattended must not be enough to take it.

    The audit row is written *before* the delete and inside the same
    transaction. Written after, it would have no user to name at all; written
    before, the SET NULL on `security_events.user_id` empties that column as the
    delete cascades, which is the intended end state -- the event survives, the
    name does not.
    """
    refusal = check_state_changing_request()
    if refusal:
        return error_response(refusal[0], status=refusal[1])

    payload = request.get_json(silent=True)
    data = payload if isinstance(payload, dict) else {}
    password = data.get("password")
    if not isinstance(password, str) or not password:
        return error_response(
            "계정을 삭제할 수 없습니다.",
            details={"password": "비밀번호를 입력해 주세요."},
        )

    user_id = current_user_id()
    user = db.session.get(User, user_id)
    if user is None or not verify_password(user.password_hash, password):
        events.record(events.LOGIN_FAILURE, events.FAILURE, user_id=user_id)
        return error_response(
            "비밀번호가 올바르지 않습니다.",
            details={"password": "비밀번호가 올바르지 않습니다."},
            status=401,
        )

    events.record(events.ACCOUNT_DELETED, events.SUCCESS, user_id=user_id, commit=False)
    # ORM delete rather than a bulk statement: the cascades are declared on the
    # foreign keys and run in the database, and a bulk delete would still work
    # -- but this way the session does not hold rows that no longer exist.
    db.session.delete(user)
    db.session.commit()

    # Cookies last. The rows are already gone, so a lost response leaves a
    # browser holding three values that name nothing rather than a live session.
    return clear_session(jsonify({"ok": True}))
