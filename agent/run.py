#!/usr/bin/env python3
"""Batch runner. Examples (from the repo root):
  ./run.sh                                  # 100 random companies from the 1,050-profile set
  ./run.sh --numbers 923609016 984851006    # specific companies
  ./run.sh --file numbers.txt               # one organization number per line
  ./run.sh --all                            # every seeded company; writes db/profiles_enriched.json
Writes output/results.jsonl, output/summary.json and output/state.json (update detection)."""
import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import core  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "db" / "profiles_1000.json"


def load_dataset_numbers():
    try:
        return [r["organisasjonsnummer"] for r in json.loads(DATASET.read_text(encoding="utf-8"))]
    except (OSError, ValueError, KeyError):
        return []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--numbers", nargs="*", default=[])
    ap.add_argument("--file")
    ap.add_argument("--random", type=int, metavar="N")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--cap", type=int, default=int(os.getenv("SIGNALPOST_REQUEST_CAP", core.DEFAULT_CAP)))
    ap.add_argument("--out-dir", default=str(ROOT / "output"))
    ap.add_argument("--no-baseline", action="store_true")
    args = ap.parse_args(argv)

    numbers = list(args.numbers)
    if args.file:
        numbers += [ln.strip() for ln in Path(args.file).read_text(encoding="utf-8").splitlines() if ln.strip()]
    pool = load_dataset_numbers()
    if args.all:
        numbers += pool
        args.cap = max(args.cap, 4 * len(pool) + 100)   # development run over the whole seed set
        print(f"--all: request cap raised to {args.cap} for this development run (judge runs keep the {core.DEFAULT_CAP} default).")
    if args.random:
        numbers += random.Random(args.seed).sample(pool, min(args.random, len(pool)))
    numbers = list(dict.fromkeys(numbers))
    if not numbers:
        ap.error("no companies given: use --random N, --numbers ..., --file or --all")

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    store = core.SnapshotStore(str(out / "state.json"), None if args.no_baseline else str(DATASET))
    budget = core.RequestBudget(args.cap)
    started = time.monotonic()

    def work(number):
        try:
            return core.crawl(number, store=store, budget=budget)
        except core.CrawlError as exc:
            return {"company_number": number, "error": exc.detail, "status": exc.status}

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        results = list(ex.map(work, numbers))
    store.save()

    ok = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]
    (out / "results.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in results) + "\n", encoding="utf-8")
    field_cov = {k: round(100 * sum(1 for r in ok if k in r["profile"]) / len(ok), 1) for k in core.EXPECTED} if ok else {}
    updates = {}
    for r in ok:
        updates[r["update"]["status"]] = updates.get(r["update"]["status"], 0) + 1
    summary = {
        "companies": len(results), "succeeded": len(ok), "failed": len(failed),
        "failures": [{"company_number": r["company_number"], "status": r["status"], "error": r["error"]} for r in failed],
        "elapsed_seconds": round(time.monotonic() - started, 1), "requests_used": budget.used, "request_cap": budget.cap,
        "average_fields_found": round(sum(r["coverage"]["found"] for r in ok) / len(ok), 2) if ok else 0,
        "expected_fields": len(core.EXPECTED), "field_coverage_percent": field_cov, "update_status_counts": updates,
        "wrong_company_checks_all_passed": sum(1 for r in ok if r["match_verified"]),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.all and ok:
        keep = ("company_number", "official_legal_name", "profile", "financials", "summary", "update", "delta_sync_hash",
                "content_hash", "missing_fields", "lineage_evidences")
        enriched = [{k: r[k] for k in keep} for r in ok]
        (ROOT / "db" / "profiles_enriched.json").write_text(json.dumps(enriched, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"Wrote {len(enriched)} enriched profiles to db/profiles_enriched.json")
    print(f"\nCompanies: {summary['companies']}  ok: {summary['succeeded']}  failed: {summary['failed']}  "
          f"time: {summary['elapsed_seconds']}s  requests: {budget.used}/{budget.cap}")
    print(f"Average fields found: {summary['average_fields_found']}/{summary['expected_fields']}   updates: {updates}")
    for k, v in field_cov.items():
        print(f"  {k:<22}{v:>6}%")
    print(f"Results: {out / 'results.jsonl'}\nSummary: {out / 'summary.json'}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
