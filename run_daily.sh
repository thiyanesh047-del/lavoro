#!/bin/sh
# Lavoro's daily run for macOS and Linux. Schedule it with cron, e.g. every day at 7:30:
#   30 7 * * * /path/to/lavoro/run_daily.sh
# Extra arguments are passed on, e.g. ./run_daily.sh --region europe
# The log goes to output/run.log. Run it as your own user, so the `claude` login is available.
cd "$(dirname "$0")" || exit 1
mkdir -p output
# cron starts with a short PATH: add the usual places for python and claude
PATH="$HOME/.local/bin:$HOME/.claude/local:/opt/homebrew/bin:/usr/local/bin:$PATH"
export PATH
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
{
  echo "=== $(date) ==="
  "$PY" -m lavoro run "$@"
} >> output/run.log 2>&1
