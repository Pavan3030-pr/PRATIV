#!/usr/bin/env python3
"""Judge-style check of an agent run.   python3 scripts/validate_output.py numbers.txt results.jsonl
Exit code 0 = every check passed. Prints one line per problem."""
import hashlib
import json
import re
import sys
from datetime import date
from urllib.parse import urlparse

TODAY = date.today()
SKIP_SHA = {"subunit_sample", "social_links", "news", "website_verified_by"}


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def numbers(path):
    out = []
    for i, line in enumerate(open(path, encoding="utf-8-sig").read().splitlines()):
        line = line.split("#", 1)[0].strip()
        tok = re.split(r"[,;\t]", line)[0].strip().strip("\"'") if line else ""
        if not tok or (i == 0 and re.fullmatch(r"[A-Za-z_ ]+", tok)):
            continue
        c = re.sub(r"[\s.]", "", tok)
        out.append(c if re.fullmatch(r"\d{9}", c) else tok)
    return out


def main(inp, res):
    problems = []
    bad = lambda n, msg: problems.append(f"{n}: {msg}")
    wanted = list(dict.fromkeys(numbers(inp)))
    rows = []
    for i, line in enumerate(open(res, encoding="utf-8"), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError:
                problems.append(f"line {i}: not valid JSON")
    got = [r.get("company_number") for r in rows]
    if got != wanted:
        problems.append(f"results do not match input: {len(got)} results for {len(wanted)} unique numbers (order or content differs)")
    ok = errs = 0
    for r in rows:
        n = r.get("company_number")
        if "error" in r:
            errs += 1
            if not isinstance(r.get("status"), int) or not r["error"]:
                bad(n, "error result without status/message")
            continue
        ok += 1
        for k in ("official_legal_name", "delta_sync_hash", "content_hash", "profile", "lineage_evidences", "missing_fields", "website", "social_links", "news"):
            if k not in r:
                bad(n, f"missing key {k}")
        if not r.get("match_verified"):
            bad(n, "match_verified is false (data from another company was discarded: check match_checks)")
        for h in ("delta_sync_hash", "content_hash"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(r.get(h, ""))):
                bad(n, f"{h} is not a SHA-256")
        ev = {}
        for e in r.get("lineage_evidences", []):
            ev.setdefault(e.get("target_metric_key"), e)
            if not (e.get("source_url_link", "").startswith("http") and e.get("crawl_timestamp") and e.get("explanation_chain") and e.get("extracted_text_snippet")):
                bad(n, f"evidence {e.get('target_metric_key')} lacks url/timestamp/explanation/snippet")
        for k, v in r.get("profile", {}).items():
            if k in SKIP_SHA:
                continue
            if k not in ev:
                bad(n, f"fact '{k}' has no evidence record")
            elif ev[k].get("value_sha256") != sha(v):
                bad(n, f"fact '{k}' does not match the hash in its evidence")
        for k in r.get("coverage", {}).get("missing", []):
            if k not in r.get("missing_fields", {}) and k not in r.get("profile", {}):
                bad(n, f"expected field '{k}' is empty with no stated reason")
        site = r.get("website", {})
        if site.get("verified") is not True and (r.get("social_links") or r.get("news")):
            bad(n, "social links or news published from a website that is not verified as the company's own")
        if site.get("verified") and not site.get("verified_by"):
            bad(n, "website marked verified without saying how")
        for it in r.get("news", []):
            d = it.get("published_at", "")
            try:
                dd = date.fromisoformat(d)
            except ValueError:
                bad(n, f"news date '{d}' is not a date")
                continue
            if dd > TODAY or dd.year < 2000:
                bad(n, f"news date {d} is in the future or implausible")
            if len(it.get("title", "").split()) < 3 or re.fullmatch(r"(?i)(see|read|view|les|vis|flere)?\s*(more|mer|news|nyheter|all)?\s*(news|nyheter)?", it.get("title", "").strip()):
                bad(n, f"news title looks like a menu label: {it.get('title')!r}")
            if urlparse(it.get("url", "")).scheme not in ("http", "https"):
                bad(n, "news item without a real URL")
        for s in r.get("social_links", []):
            if urlparse(s.get("url", "")).scheme != "https" or not s.get("found_on"):
                bad(n, f"social link {s.get('url')} lacks https or the page it was found on")
        fin = r.get("financials") or {}
        for y in fin.get("history", []):
            if y.get("period_end") and y.get("revenue") is not None and not isinstance(y["revenue"], (int, float)):
                bad(n, "financial history value is not numeric")
    print(f"{len(rows)} results ({ok} ok, {errs} error lines) for {len(wanted)} unique input numbers")
    for p in problems[:60]:
        print("PROBLEM", p)
    print("PASS" if not problems else f"FAIL ({len(problems)} problems)")
    return 0 if not problems else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
