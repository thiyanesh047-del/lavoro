#!/bin/sh
# Double-click to open Lavoro on macOS (Linux: run ./lavoro.command). It starts the site in the background and
# opens it in your browser; if the site is already running, it just opens the browser.
# The first time, make it runnable:  chmod +x lavoro.command
# To close the site later:  python3 -m lavoro stop
cd "$(dirname "$0")" || exit 1
mkdir -p output
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
nohup "$PY" -m lavoro serve --open >> output/site.log 2>&1 &
