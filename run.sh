#!/usr/bin/env bash
# One command to run the agent:
#   ./run.sh                                   100 random companies from the 1,050-profile set
#   ./run.sh --numbers 923609016 984851006     specific companies
# Needs only Python 3 and internet access to data.brreg.no.
set -euo pipefail
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --disable-pip-version-check requests
[ "$#" -gt 0 ] || set -- --random 100
exec .venv/bin/python agent/run.py "$@"
