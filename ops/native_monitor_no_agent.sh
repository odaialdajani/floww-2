#!/bin/bash
# Native cron passes a script path, not arbitrary command arguments.
exec /usr/bin/python3 -I "$(dirname -- "$0")/native_monitor.py" --mode no-agent
