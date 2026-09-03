"""Give the T06 rows an owner. T07-C100.

The diary predates accounts, so every plan in the deployed database has
`user_id IS NULL`. This creates the account and attaches them, which is the
whole of the "이어 붙였다" the criterion asks to be shown -- the rows are
already in the right database, because T07 continues on T06's (design 0).

Three things this refuses to do.

**Guess.** Every unowned plan must appear in exactly one of the two id lists.
A plan in neither stops the run, with its id printed, rather than being swept
into whichever bucket was convenient. Titles are never matched on: the synthetic
rows left over from T06's public demo are told apart by id, decided by a person
reading the table, not by a substring that could match something real.

**Delete quietly.** Excluded plans have to go, or `user_id` can never become NOT
NULL. That is destructive and irreversible on a live database, so a plain run
only reports; `--apply` is what acts.

**Talk.** The output is counts and ids. No titles, no diary text, no address,
and above all no password -- which arrives in its own environment variable
rather than on the command line, because `render.yaml` is committed and an
argument would also be in the process list and the log.

    BOOT_TASK=claim_t06_data
    BOOT_TASK_ARGS=--apply
    CLAIM_EMAIL=...            CLAIM_PASSWORD=...        (sync: false)
    CLAIM_PLAN_IDS=a,b,c       CLAIM_EXCLUDE_PLAN_IDS=d,e
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import select

# Runnable as `python scripts/claim_t06_data.py` from backend/, which is how
# deploy/start.sh invokes it.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Plan, User, normalize_email  # noqa: E402
from app.security.passwords import hash_password  # noqa: E402


class ClaimRefused(Exception):
    """Something was ambiguous or missing. Nothing has been changed."""


def id_list(name: str) -> list[str]:
    return [value.strip() for value in os.getenv(name, "").split(",") if value.strip()]


def find_or_create_user(email: str, password: str) -> tuple[User, bool]:
    """The account the rows will belong to. Safe to call twice.

    Re-running must not fail and must not make a second account, because the
    claim rides a deploy and a deploy can be retried -- by Render, or by
    somebody pushing again.
    """
    normalized = normalize_email(email)
    existing = db.session.scalar(select(User).where(User.email == normalized))
    if existing is not None:
        return existing, False
    user = User(email=normalized, password_hash=hash_password(password))
    db.session.add(user)
    db.session.flush()
    return user, True


def partition(unowned: list[str], claim: list[str], exclude: list[str]) -> tuple[list[str], list[str]]:
    """Split the unowned plans, or refuse because the lists do not cover them."""
    overlap = sorted(set(claim) & set(exclude))
    if overlap:
        raise ClaimRefused(f"these ids are in both lists: {overlap}")

    present = set(unowned)
    to_claim = [plan_id for plan_id in unowned if plan_id in set(claim)]
    to_delete = [plan_id for plan_id in unowned if plan_id in set(exclude)]
    undecided = sorted(present - set(claim) - set(exclude))
    if undecided:
        raise ClaimRefused(
            "these unowned plans are in neither list, so the run stopped before "
            f"changing anything: {undecided}"
        )

    # Ids named in a list but not present are not an error: a second run sees
    # the claimed ones already owned and the excluded ones already gone.
    return to_claim, to_delete


def run(email: str, password: str, claim: list[str], exclude: list[str], *, apply: bool) -> dict:
    unowned = list(db.session.scalars(select(Plan.id).where(Plan.user_id.is_(None))))
    to_claim, to_delete = partition(unowned, claim, exclude)

    report = {
        "unowned_before": len(unowned),
        "to_claim": len(to_claim),
        "to_delete": len(to_delete),
        "claim_ids": to_claim,
        "delete_ids": to_delete,
        "applied": apply,
        "account_created": False,
    }
    if not apply:
        report["unowned_after"] = len(unowned)
        return report

    user, created = find_or_create_user(email, password)
    report["account_created"] = created

    if to_claim:
        db.session.execute(
            db.update(Plan).where(Plan.id.in_(to_claim), Plan.user_id.is_(None))
            .values(user_id=user.id).execution_options(synchronize_session=False)
        )
    for plan_id in to_delete:
        # Through the ORM so the configured cascades run on SQLite too, where
        # foreign keys are not enforced unless asked.
        plan = db.session.get(Plan, plan_id)
        if plan is not None:
            db.session.delete(plan)

    # One transaction: an interrupted deploy leaves the database as it was,
    # rather than half-claimed with no record of where it stopped.
    db.session.commit()

    report["unowned_after"] = db.session.scalar(
        select(db.func.count()).select_from(Plan).where(Plan.user_id.is_(None))
    )
    return report


def render(report: dict) -> str:
    lines = [
        "----- claim_t06_data -----",
        f"mode                : {'APPLY' if report['applied'] else 'REPORT ONLY (pass --apply to act)'}",
        f"unowned plans before: {report['unowned_before']}",
        f"to claim            : {report['to_claim']}",
        f"to delete           : {report['to_delete']}",
        f"account created     : {report['account_created']}",
        f"unowned plans after : {report['unowned_after']}",
    ]
    # Ids only. A title here would be the user's own words in a log.
    for label, key in (("claimed", "claim_ids"), ("deleted", "delete_ids")):
        for plan_id in report[key]:
            lines.append(f"  {label}: {plan_id}")
    if report["applied"] and report["unowned_after"] == 0:
        lines.append("NULL=0 -- the NOT NULL migration can go in the next deploy.")
    elif report["applied"]:
        lines.append("NULL is not yet 0. Do NOT ship the NOT NULL migration.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="actually claim and delete; without it nothing changes")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    email = os.getenv("CLAIM_EMAIL", "")
    password = os.getenv("CLAIM_PASSWORD", "")
    if args.apply and not (email and password):
        print("CLAIM_EMAIL and CLAIM_PASSWORD must both be set to apply.", file=sys.stderr)
        return 2

    app = create_app()
    with app.app_context():
        try:
            report = run(email, password, id_list("CLAIM_PLAN_IDS"), id_list("CLAIM_EXCLUDE_PLAN_IDS"),
                         apply=args.apply)
        except ClaimRefused as refusal:
            db.session.rollback()
            print(f"claim_t06_data refused: {refusal}", file=sys.stderr)
            return 1
        print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
