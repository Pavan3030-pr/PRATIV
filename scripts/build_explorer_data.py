#!/usr/bin/env python3
"""Build the static data behind the public explorer (frontend/public/explore).

index.json      small search index (one row per company)
c/<orgnr>.json  full source-backed profile: every fact with URL, date, field path, SHA-256 and explanation

Reads db/profiles_enriched.json (all seeded companies) and overlays any fuller agent results found in
output/results.jsonl and results.jsonl (website / social / news).  Run:  python3 scripts/build_explorer_data.py
"""
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend" / "public" / "explore"

LABELS = {
    "official_legal_name": "Legal name", "organisation_form": "Organisation form",
    "registered_address": "Registered address", "incorporation_date": "Founded",
    "industry": "Industry (NACE)", "employees": "Employees", "website": "Website",
    "vat_registered": "VAT registered", "institutional_sector": "Institutional sector",
    "company_status": "Status", "general_manager": "General manager", "chair": "Board chair",
    "board_member_count": "Board size", "subunit_count": "Sub-units",
    "financial_revenue": "Revenue", "operating_result": "Operating result", "net_profit": "Net result",
}
ORDER = list(LABELS)


def load_jsonl(path):
    rows = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    return rows


def city(addr):
    m = re.search(r"\b\d{4}\s+([^,]+)", addr or "")
    return m.group(1).strip().title() if m else ""


def display(key, ev, profile):
    v = profile.get(key)
    if v is not None and key not in ("financial_revenue", "operating_result", "net_profit"):
        if isinstance(v, bool):
            return "Yes" if v else "No"
        return str(v)
    snip = ev.get("extracted_text_snippet") or ""
    return snip.split(": ", 1)[1] if ": " in snip and key in ("financial_revenue", "operating_result", "net_profit", "employees") else snip


def last_crawl(row):
    """Newest evidence timestamp in a result row, so an older run file never overwrites a fresher crawl."""
    return max((ev.get("crawl_timestamp") or "" for ev in row.get("lineage_evidences") or []), default="")


def main():
    rows = {r["company_number"]: r for r in json.loads((ROOT / "db" / "profiles_enriched.json").read_text(encoding="utf-8"))}
    for extra in (ROOT / "results.jsonl", ROOT / "output" / "results.jsonl"):
        for r in load_jsonl(extra):
            org = r.get("company_number")
            if not org:
                continue
            current = rows.get(org)
            if current is None or last_crawl(r) > last_crawl(current):
                rows[org] = {**current, **r} if current else r

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "c").mkdir(parents=True)
    index = []
    for org, r in sorted(rows.items()):
        profile = r.get("profile") or {}
        evs = r.get("lineage_evidences") or []
        base = f"https://data.brreg.no/enhetsregisteret/api/enheter/{org}"
        facts = []
        for ev in evs:
            key = ev.get("target_metric_key", "")
            url = ev.get("source_url_link") or base
            facts.append({
                "k": key, "l": LABELS.get(key) or ("Job posting" if key.startswith("job_item_") else key.replace("_", " ").capitalize()),
                "v": display(key, ev, profile), "t": ev.get("crawl_timestamp", ""),
                "p": ev.get("field_path", ""), "s": ev.get("value_sha256", ""),
                "e": ev.get("explanation_chain", ""), **({"u": url} if url != base else {}),
            })
        facts.sort(key=lambda f: ORDER.index(f["k"]) if f["k"] in ORDER else 99)
        fin = r.get("financials") or {}
        news = [{"title": n.get("title"), "url": n.get("url"), "at": n.get("published_at")} for n in (r.get("news") or [])]
        jobs = [{"title": j.get("title"), "url": j.get("url"), "at": j.get("posted_at")} for j in (r.get("jobs") or [])]
        social = [{"platform": s.get("platform"), "url": s.get("url")} for s in (r.get("social_links") or [])]
        web = r.get("website") or {}
        upd = r.get("update") or {}
        doc = {
            "n": org, "name": r.get("official_legal_name") or org, "base": base,
            "summary": r.get("summary") or "", "hash": r.get("delta_sync_hash") or "",
            "content_hash": r.get("content_hash") or "",
            "update": {"status": upd.get("status", ""), "changed": [c.get("field") for c in upd.get("changed_fields", [])]},
            "missing": r.get("missing_fields") or {}, "facts": facts,
            "fin": {k: fin.get(k) for k in ("period_start", "period_end", "currency", "account_type", "source_url", "revenue", "operating_result", "net_result")} if fin else None,
            "web": {"url": web.get("url"), "verified": bool(web.get("verified")), "by": web.get("verified_by")} if web else None,
            "news": news, "jobs": jobs, "social": social,
        }
        (OUT / "c" / f"{org}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        addr = profile.get("registered_address", "")
        index.append([org, doc["name"], city(addr), (profile.get("organisation_form") or "").split("(")[-1].rstrip(")"),
                      profile.get("industry") or "", 1 if fin else 0, 1 if profile.get("website") else 0,
                      profile.get("employees") if isinstance(profile.get("employees"), int) else 0])
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(index)} companies to {OUT}")


if __name__ == "__main__":
    main()
