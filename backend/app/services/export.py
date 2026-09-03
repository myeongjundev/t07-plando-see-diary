from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.extensions import db
from app.models import CompletionEvent, ExecutionLog, Plan, PlanRevision, Reflection, Task, TaskTag
from app.models.plan import utc_now
from app.services.executions import serialize_completion, serialize_execution
from app.services.plans import serialize_plan, serialize_revision
from app.services.ownership import owned_plan_ids
from app.services.reflections import serialize_reflection
from app.services.tasks import serialize_task
from app.time import utc_iso


def export_all(user_id: str) -> dict:
    """Everything belonging to one account, in one snapshot.

    Every table is scoped by joining back to that user's plans. An export takes
    no id, so there is nothing a per-row ownership check could be applied to
    afterwards: if the scope is not inside these queries it is nowhere at all
    (T07-C125, T07-C133).

    The plan and task id sets are read once inside the snapshot and reused,
    rather than re-derived per table. Two subqueries evaluated separately could
    disagree, and an export that half-contains a plan is worse than one that
    leaves it out.
    """
    # A dedicated read transaction gives every exported table the same snapshot.
    with db.engine.connect() as connection:
        if connection.dialect.name == "postgresql":
            connection = connection.execution_options(isolation_level="REPEATABLE READ")
        elif connection.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN")
        with Session(connection) as snapshot:
            plan_ids = snapshot.scalars(owned_plan_ids(user_id)).all()
            task_ids = snapshot.scalars(select(Task.id).where(Task.plan_id.in_(plan_ids))).all()

            def owned(model, column, ids, key):
                return snapshot.scalars(select(model).where(column.in_(ids)).order_by(key)).all()

            tasks = []
            task_rows = snapshot.scalars(
                select(Task).options(selectinload(Task.tags))
                .where(Task.plan_id.in_(plan_ids)).order_by(Task.id)
            )
            for task in task_rows:
                item = serialize_task(task)
                del item["tags"]  # Export retains normalized tag IDs in taskTags.
                tasks.append(item)
            return {
                "schemaVersion": 2, "exportedAt": utc_iso(utc_now()),
                "plans": [serialize_plan(row)
                          for row in owned(Plan, Plan.id, plan_ids, Plan.id)],
                "planRevisions": [serialize_revision(row)
                                  for row in owned(PlanRevision, PlanRevision.plan_id, plan_ids,
                                                   PlanRevision.revision_id)],
                "tasks": tasks,
                "taskTags": [{"id": row.id, "taskId": row.task_id, "value": row.value}
                             for row in owned(TaskTag, TaskTag.task_id, task_ids, TaskTag.id)],
                "completionEvents": [serialize_completion(row)
                                     for row in owned(CompletionEvent, CompletionEvent.task_id, task_ids,
                                                      CompletionEvent.id)],
                "executionLogs": [serialize_execution(row)
                                  for row in owned(ExecutionLog, ExecutionLog.task_id, task_ids,
                                                   ExecutionLog.id)],
                "reflections": [serialize_reflection(row)
                                for row in owned(Reflection, Reflection.plan_id, plan_ids, Reflection.id)],
            }
