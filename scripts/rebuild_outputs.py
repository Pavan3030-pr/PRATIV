#!/usr/bin/env python3
"""Re-apply the current job and summary rules to result files that are already on disk, with no network.

What it does to every company row:
  * drops job rows that are not real vacancies ("Sjekk ledige stillinger") or that a group careers page attributed to a
    sister unit (a card for "Telenor Norge" is not a posting by TELENOR ASA);
  * tags each remaining job with where it is hosted (`origin`) so nothing calls a Jobbnorge ad "on its own site";
  * renumbers the job evidence rows, refreshes missing_fields["jobs"] and content_hash;
  * rewrites `summary` with the buyer-first lead (revenue, open role, dated news, headcount, manager) and no boilerplate.

Usage (repo root):  python3 scripts/rebuild_outputs.py            # output/results.jsonl, results.jsonl, db/profiles_enriched.json
                    python3 scripts/rebuild_outputs.py FILE ...   # chosen files (.jsonl or a .json list)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agent"))
import core  # noqa: E402
import web  # noqa: E402

DEFAULTS = ["output/results.jsonl", "results.jsonl", "db/profiles_enriched.json"]
NO_JOBS = "No open or dated job posting was found on the verified company site or under this employer's name on Jobbnorge."
GROUP_CARD = re.compile(r"posting by (.+) on the group's shared careers page")


def full_jobs(row):
    if row.get("jobs") is not None:
        return [dict(j) for j in row["jobs"]]
    sources = {e["source_url_link"]: e.get("field_path", "") for e in row.get("lineage_evidences", [])
               if str(e.get("target_metric_key", "")).startswith("job_item_")}
    return [dict(j, source=sources.get(j["url"], "")) for j in row["profile"].get("jobs", [])]


def keep(job, name):
    if not web.valid_job_title(job.get("title", "")):
        return False
    src = job.get("source", "")
    if "group's shared careers page" in src:
        card = GROUP_CARD.search(src)
        return bool(card) and web.employer_matches_label(card.group(1), name)
    return True


def clean(row):
    if "error" in row or "profile" not in row:
        return 0, False
    name = row["official_legal_name"]
    consistent = core.sha(row["profile"]) == row.get("content_hash")
    before = full_jobs(row)
    kept = []
    for job in before:
        if keep(job, name):
            job["origin"] = web.job_origin(job.get("source", ""))
            kept.append(job)
    urls = {j["url"] for j in kept}
    evidences, n = [], 0
    for e in row.get("lineage_evidences", []):
        if str(e.get("target_metric_key", "")).startswith("job_item_"):
            if e["source_url_link"] not in urls:
                continue
            n += 1
            e = dict(e, target_metric_key=f"job_item_{n}")
        evidences.append(e)
    m = re.search(r"retrieved (\S+?)\)", row.get("summary", ""))
    ts = m.group(1) if m else (evidences[0]["crawl_timestamp"] if evidences else "")
    have = sum(1 for e in evidences if str(e.get("target_metric_key", "")).startswith("job_item_"))
    if kept and have != len(kept):          # evidence went missing (unverified-site branch): rebuild it from the jobs
        evidences = [e for e in evidences if not str(e.get("target_metric_key", "")).startswith("job_item_")]
        for i, j in enumerate(kept, 1):
            when = j.get("posted_at") or "open / undated"
            origin = j.get("found_on") or j["url"]
            evidences.append({
                "target_metric_key": f"job_item_{i}", "extracted_text_snippet": f"{when}: {j['title']}",
                "source_url_link": j["url"], "crawl_timestamp": ts,
                "explanation_chain": f"{j.get('source') or 'job posting'}; title and employer read from {origin}"
                                     + ("" if j.get("posted_at") else "; the page shows no publish date") + ", nothing inferred.",
                "field_path": j.get("source") or "job posting", "value_sha256": core.sha(f"{when} {j['title']}")})
    row["lineage_evidences"] = evidences
    if kept:
        row["profile"]["jobs"] = [{"title": j["title"], "url": j["url"], "posted_at": j.get("posted_at"), "origin": j["origin"]} for j in kept]
        row.get("missing_fields", {}).pop("jobs", None)
    else:
        row["profile"].pop("jobs", None)
        if before or "jobs" in row:
            row.setdefault("missing_fields", {}).setdefault("jobs", NO_JOBS)
    if row.get("jobs") is not None:
        row["jobs"] = kept
    if consistent:
        row["content_hash"] = core.sha(row["profile"])
    row["summary"] = core.build_summary(row["company_number"], row["profile"], row.get("financials") or None, ts, kept)
    return len(before) - len(kept), True


def main(argv):
    for rel in argv or DEFAULTS:
        path = Path(rel) if Path(rel).is_absolute() else ROOT / rel
        if not path.exists():
            print(f"skip {rel}: not found")
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".jsonl":
            rows = [json.loads(l) for l in text.splitlines() if l.strip()]
        else:
            rows = json.loads(text)
        dropped = sum(clean(r)[0] for r in rows)
        if path.suffix == ".jsonl":
            path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        else:
            path.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        with_jobs = sum(1 for r in rows if r.get("profile", {}).get("jobs"))
        print(f"{rel}: {len(rows)} rows, {dropped} job row(s) dropped, {with_jobs} companies with jobs, summaries rebuilt")


if __name__ == "__main__":
    main(sys.argv[1:])
