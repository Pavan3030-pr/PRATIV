# SIGNALPOST architecture

```
 numbers.txt ──► run.sh ──► agent/run.py ─┐                 ┌─► output/results.jsonl (one result per company)
                                          ├─► agent/core.py ─┤
 HTTP  POST /api/v1/crawl/{n}, /crawl-batch ┘      │          └─► output/state.json (update detection)
                                                   ├─► Brreg Enhetsregisteret / roller / underenheter / Regnskapsregisteret
                                                   └─► agent/web.py  (company website: ownership, social, news)

 Browser (Vercel) ──► Spring Boot API (OAuth, JWT, PostgreSQL audit store) ──► agent
        └─ if no backend: reads Brreg directly and hashes in the browser
```

## Decisions
- **Evidence first.** A value is published only when read from a response that belongs to the requested company. Each fact has an evidence record: source URL, field path, SHA-256 of the value, timestamp, explanation. Anything missing stays null with a reason in `missing_fields`.
- **Wrong-company guards.** Modulus-11 check digit, response org number must equal the request, accounts and sub-units must belong to the company; foreign records are discarded and reported in `match_checks`.
- **Website rules** (`agent/web.py`): the registry website is only trusted for social links and news after the site shows the company's organisation number or exact registered name; social handles must match the company name or its own domain (a parent's handle on a shared domain does not); news needs a real post page, a human title and a publish date (never modified/updated dates).
- **Budgeted and bounded.** Global request cap, per-company website cap (10), politeness throttle, retries, time deadline for website work, SSRF guard (public hosts only, redirects re-checked), size and type limits on fetched pages.
- **Failure isolation.** A secondary source or website failing never costs the registry profile; one bad company never stops a run; a temporary outage is never reported as a data change.
- **Update detection.** `delta_sync_hash` covers seven core registry fields; `content_hash` covers the full profile; changed fields are listed old/new.

## Known limits (stated, not hidden)
- The registry lists a website for only a small share of companies; websites are never guessed.
- Sites that render content with JavaScript yield no news or social links from plain HTML.
- The agent uses no language model; the database has a `vector` column that is reserved for future embeddings and is not populated.
- Large companies' accounts can be temporarily unavailable from Regnskapsregisteret (HTTP 500); figures then stay empty with that reason.

## Verify it yourself
`./run.sh numbers.txt results.jsonl && python3 scripts/validate_output.py numbers.txt results.jsonl`
