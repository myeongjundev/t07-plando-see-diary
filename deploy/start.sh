#!/bin/sh
set -eu
flask --app app:create_app db upgrade

# Render Free runs the web service and nothing else: the plan has no dashboard
# shell, no SSH, no one-off jobs and no cron jobs. So a one-off command -- the
# hashing benchmark, later the T06 data claim -- has no way onto the instance
# except by riding the boot of the service itself.
#
# BOOT_TASK is that door. Set it in render.yaml, push, read the bracketed block
# out of the Render log, set it back to `none`, push again. It runs in the
# background so that a task measured in minutes on 0.1 CPU does not hold the
# port shut and fail the health check.
#
# The name is matched against a fixed list. An environment variable is not a
# remote input -- only the repository owner can set one -- but a shell that runs
# whatever string it is handed is the kind of thing that outlives the reason for
# it, and this one is meant to be deleted.
case "${BOOT_TASK:-none}" in
  none) ;;
  bench_password_hashing)
    # Backgrounded. On a tenth of a core the benchmark runs for minutes, and
    # holding the port shut that long fails the health check and the deploy.
    # It only measures, so nothing depends on it finishing first.
    (
      sleep 10
      echo "===== BOOT_TASK ${BOOT_TASK} BEGIN ====="
      # shellcheck disable=SC2086 # deliberate word splitting: these are argv words
      python "scripts/${BOOT_TASK}.py" ${BOOT_TASK_ARGS:-} || echo "===== BOOT_TASK FAILED ====="
      echo "===== BOOT_TASK ${BOOT_TASK} END ====="
    ) &
    ;;
  claim_t06_data)
    # Synchronous, and deliberately so. This one changes data, and every
    # request the server answers before it finishes would be answered against
    # half-owned rows -- the diary would look empty to its owner. It is a hash
    # and an UPDATE, not a benchmark, so the health check has time.
    #
    # A failure stops the boot: `set -e` is what makes an interrupted claim a
    # failed deploy rather than a running app with data in an unknown state.
    echo "===== BOOT_TASK ${BOOT_TASK} BEGIN ====="
    # shellcheck disable=SC2086 # deliberate word splitting: these are argv words
    python "scripts/${BOOT_TASK}.py" ${BOOT_TASK_ARGS:-}
    echo "===== BOOT_TASK ${BOOT_TASK} END ====="
    ;;
  *)
    echo "start.sh: BOOT_TASK '${BOOT_TASK}' is not a known task; ignoring" >&2
    ;;
esac

exec waitress-serve --call --listen="0.0.0.0:${PORT:-8000}" app:create_app
