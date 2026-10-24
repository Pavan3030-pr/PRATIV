#!/usr/bin/env bash
# THE ONE COMMAND:   ./run.sh numbers.txt [results.jsonl]
#   numbers.txt   one Norwegian organisation number per line (blank lines, # comments, a header row are fine)
#   results.jsonl optional output file; default output/results.jsonl. One JSON result per company, in input order.
# Other uses:
#   ./run.sh                                   100 random companies from the 1,050-profile set
#   ./run.sh --numbers 923609016 984851006     specific companies
#   ./run.sh numbers.txt --no-web              registry only (skip website / social / news)
# Needs only Python 3 and internet access.
set -euo pipefail
export SIGNALPOST_CALLER_DIR="$PWD"   # so relative input/output paths mean what the user typed
cd "$(dirname "$0")"
# a virtualenv copied from another machine (e.g. committed by accident) points at that machine's Python: rebuild it
if ! .venv/bin/python -c "import sys" >/dev/null 2>&1; then
  rm -rf .venv
  python3 -m venv .venv
fi
.venv/bin/pip install -q --disable-pip-version-check requests beautifulsoup4 defusedxml
[ "$#" -gt 0 ] || set -- --random 100
exec .venv/bin/python agent/run.py "$@"
