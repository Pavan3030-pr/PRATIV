#!/usr/bin/env python3
"""List seeded companies that the register gives a website for.

`db/profiles_1000.json` holds registry identity fields only, so the website is read from each company's
Enhetsregisteret entity. Output: one organisation number per line, largest employers first, plus the
website on stderr for inspection.

Usage: python3 scripts/discover_websites.py [limit] [scan]
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://data.brreg.no/enhetsregisteret/api/enheter"


def entity(number: str):
    req = urllib.request.Request(f"{API}/{number}", headers={"Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code == 429:
                time.sleep(2 + attempt * 2)
                continue
            return None
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1 + attempt)
    return None


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    scan = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    seeded = json.loads((ROOT / "db" / "profiles_1000.json").read_text(encoding="utf-8"))
    seeded.sort(key=lambda r: -(r.get("antallAnsatte") or 0))
    seeded = seeded[:scan]
    found = []
    for i, row in enumerate(seeded, 1):
        number = row["organisasjonsnummer"]
        data = entity(number) or {}
        site = (data.get("hjemmeside") or "").strip()
        if site:
            found.append((number, row.get("navn"), row.get("antallAnsatte") or 0, site))
        if i % 100 == 0:
            print(f"{i}/{len(seeded)} checked, {len(found)} with a website", file=sys.stderr)
        time.sleep(0.02)
    for number, name, employees, site in found:
        print(f"{number}\t{name}\t{employees}\t{site}", file=sys.stderr)
    chosen = found[:limit]
    for number, *_ in chosen:
        print(number)
    print(f"chose {len(chosen)} of {len(found)} companies with a website", file=sys.stderr)


if __name__ == "__main__":
    main()
