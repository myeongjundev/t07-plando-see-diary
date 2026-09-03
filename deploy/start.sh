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
  bench_password_hashing|claim_t06_data)
    (
      # Let waitress bind first, so the task is not racing the health check for
      # the tenth of a core we are given.
      sleep 10
      echo "===== BOOT_TASK ${BOOT_TASK} BEGIN ====="
      # shellcheck disable=SC2086 # deliberate word splitting: these are argv words
      python "scripts/${BOOT_TASK}.py" ${BOOT_TASK_ARGS:-} || echo "===== BOOT_TASK FAILED ====="
      echo "===== BOOT_TASK ${BOOT_TASK} END ====="
    ) &
    ;;
  *)
    echo "start.sh: BOOT_TASK '${BOOT_TASK}' is not a known task; ignoring" >&2
    ;;
esac

exec waitress-serve --call --listen="0.0.0.0:${PORT:-8000}" app:create_app
