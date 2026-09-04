#!/bin/sh
set -eu

MIGRATE="flask --app app:create_app db upgrade"

# The last revision at which `plans.user_id` may still be NULL. The migration
# after it (c48b1f60a2d7) makes the column NOT NULL and refuses to apply while
# any plan is unowned -- correctly, because a NOT NULL over unowned rows is a
# claim that never ran.
#
# The claim therefore has to happen *between* two migrations, and an unconditional
# `db upgrade` to head leaves nowhere to stand: the boot would reach the NOT NULL
# with every T06 row still ownerless and fail there, before BOOT_TASK ran at all.
# So the claim branch below upgrades to here, claims, and then finishes the
# upgrade -- one deploy, and the NOT NULL applies to rows that now have an owner.
PRE_OWNERSHIP_REVISION="a1c7d9e40b52"

# Render Free runs the web service and nothing else: the plan has no dashboard
# shell, no SSH, no one-off jobs and no cron jobs. So a one-off command -- the
# hashing benchmark, and the T06 data claim -- has no way onto the instance
# except by riding the boot of the service itself.
#
# BOOT_TASK is that door. Set it in render.yaml, push, read the bracketed block
# out of the Render log, set it back to `none`, push again.
#
# The name is matched against a fixed list. An environment variable is not a
# remote input -- only the repository owner can set one -- but a shell that runs
# whatever string it is handed is the kind of thing that outlives the reason for
# it, and this one is meant to be deleted.
case "${BOOT_TASK:-none}" in
  claim_t06_data)
    # Synchronous, and deliberately so. This one changes data, and every
    # request the server answers before it finishes would be answered against
    # half-owned rows -- the diary would look empty to its owner. It is a hash
    # and an UPDATE, not a benchmark, so the health check has time.
    #
    # A failure stops the boot: `set -e` is what makes an interrupted claim a
    # failed deploy rather than a running app with data in an unknown state.
    # It also stops the second upgrade, so the NOT NULL is never reached by a
    # claim that did not finish.
    $MIGRATE "$PRE_OWNERSHIP_REVISION"
    echo "===== BOOT_TASK ${BOOT_TASK} BEGIN ====="
    # shellcheck disable=SC2086 # deliberate word splitting: these are argv words
    python "scripts/${BOOT_TASK}.py" ${BOOT_TASK_ARGS:-}
    echo "===== BOOT_TASK ${BOOT_TASK} END ====="
    # Now that every plan has an owner, the rest of the chain can apply. Safe to
    # re-run: a database already at head takes neither of these anywhere, and
    # the claim itself is idempotent.
    $MIGRATE
    ;;
  bench_password_hashing)
    $MIGRATE
    # Backgrounded. On a tenth of a core the benchmark runs for minutes, and
    # holding the port shut that long fails the health check and the deploy.
    # It only measures, so nothing depends on it finishing first.
    (
      sleep 10
      echo "===== BOOT_TASK ${BOOT_TASK} BEGIN ====="
      # shellcheck disable=SC2086 # deliberate word splitting: these are argv words
      python "scripts/${BOOT_TASK}.py" ${BOOT_TASK_ARGS:-}  || echo "===== BOOT_TASK FAILED ====="
      echo "===== BOOT_TASK ${BOOT_TASK} END ====="
    ) &
    ;;
  none)
    $MIGRATE
    ;;
  *)
    echo "start.sh: BOOT_TASK '${BOOT_TASK}' is not a known task; ignoring" >&2
    $MIGRATE
    ;;
esac

exec waitress-serve --call --listen="0.0.0.0:${PORT:-8000}" app:create_app
