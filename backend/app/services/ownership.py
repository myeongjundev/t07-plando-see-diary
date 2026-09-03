"""Whose row is this. Design section 2 and 3. T07-C116 through C126.

Every lookup of a plan, task or reflection goes through here, and every one of
them joins to `plans.user_id`. There is no second copy of the owner to disagree
with the first.

Four shapes, because a decorator only covers the first:

    single      owned_plan / owned_task / owned_reflection -- missing is 404
    list        plans_for / owned_plan_ids -- scoped in the query
    creation    owner_for_new_plan -- a new row without an owner is an orphan
    export      the whole subtree, joined to that user's plans

Lists and exports take no id, so nothing about them can be checked by looking at
one. Scoping has to be inside the query or it is not there at all.

Missing and not-yours are the same answer, 404. 403 would confirm the id exists,
and walking a range of ids to learn which are real is the enumeration the
uniform answer prevents. T07-C121 allows exactly this.
"""
from __future__ import annotations

from flask import g
from sqlalchemy import Select, select

from app.extensions import db
from app.models import Plan, Reflection, Task


def current_user_id() -> str:
    """The authenticated user for this request.

    Read from `g`, which only `@login_required` writes, after it has confirmed
    the session row is live. Nothing here trusts a value from the request.
    """
    return g.current_user


def current_session_id() -> str:
    """The live refresh session backing this request, by id.

    Here rather than read from `g` at the call site for the same reason as
    current_user_id: one module touches the request context, so there is one
    place to look when asking how identity enters the application.
    """
    return g.current_session.id


def plans_for(user_id: str | None = None) -> Select:
    """Base query for one user's plans. The root every other scope hangs from."""
    return select(Plan).where(Plan.user_id == (user_id or current_user_id()))


def owned_plan_ids(user_id: str | None = None) -> Select:
    """Subquery of this user's plan ids, for scoping the tables that hang off them."""
    return select(Plan.id).where(Plan.user_id == (user_id or current_user_id()))


def owned_plan(plan_id: str) -> Plan | None:
    return db.session.scalar(plans_for().where(Plan.id == plan_id))


def owned_task(task_id: str, *, include_deleted: bool = False) -> Task | None:
    """A task of this user's, found through its plan.

    Tasks carry no `user_id` of their own. The join is the point: one place
    records who owns what, so there is never a second answer that has drifted.
    """
    statement = select(Task).join(Plan, Task.plan_id == Plan.id).where(
        Task.id == task_id,
        Plan.user_id == current_user_id(),
    )
    if not include_deleted:
        statement = statement.where(Task.deleted_at.is_(None))
    return db.session.scalar(statement)


def owned_reflection(reflection_id: str) -> Reflection | None:
    return db.session.scalar(
        select(Reflection).join(Plan, Reflection.plan_id == Plan.id).where(
            Reflection.id == reflection_id,
            Plan.user_id == current_user_id(),
        )
    )


def owner_for_new_plan() -> str:
    """The owner to stamp on a plan being created.

    Separate from current_user_id only to make the creation path findable: a new
    plan with no owner is invisible to every query above, which reads as data
    loss rather than as the bug it is.
    """
    return current_user_id()
