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
- **Website rules** (`agent/web.py`): the registry website is only trusted for social links, news and jobs after the site both looks like this company's own domain and shows its organisation number or exact registered name; social handles must match the company name or its own domain (a parent's handle on a shared domain does not); news needs a real post page, a human title and a publish date (never modified/updated dates); jobs are read from schema.org JobPosting JSON-LD, same-site posting links, or employer-scoped FINN/Jobbnorge pages the company links to, and need a human role title. An unverified or unreachable site is reported in `missing_fields`, never asserted as the company's website.
- **Job boards are read from their data, not their JavaScript.** Jobbnorge postings come from `publicapi.jobbnorge.no/v3/jobs` (one cached request per run), matched to the employer by the `employer=` link on its site or by an exact registered-name match ignoring legal form and word order. Those postings are published even when the company's own site is unverified or unreachable, because the employer record on the board is the proof; every item states which match was used.
- **Buyer-first summary** (`build_summary`): opens with one sourced, buyer-relevant fact (filed revenue, an open role, or registered industry/employees) rather than repeating registry fields.
- **Budgeted and bounded.** Global request cap, per-company website cap (10), politeness throttle, retries, time deadline for website work, SSRF guard (public hosts only, redirects re-checked), size and type limits on fetched pages.
- **Robots.txt is honoured.** `agent/web.py` fetches `/robots.txt` once per host, caches it, and any URL whose path matches a `Disallow` rule (Allow wins when longer) is skipped and logged. An unreachable or missing robots.txt allows crawling, as the convention states.
- **Failure isolation.** A secondary source or website failing never costs the registry profile; one bad company never stops a run; a temporary outage is never reported as a data change.
- **Update detection.** `delta_sync_hash` covers seven core registry fields; `content_hash` covers the full profile; changed fields are listed old/new.

## Known limits (stated, not hidden)
- The registry lists a website for only a small share of companies; websites are never guessed.
- Sites that render content with JavaScript yield no news, jobs or social links from plain HTML.
- Jobbnorge is read through its public feed; **Workday, SuccessFactors and other ATS tenants that render only in the browser are still not read**, so employers such as Telenor, Hydro, Yara and Aker BP show zero postings even with a verified site.
- Accessibility is measured by axe on every explorer page in CI; serious and critical WCAG 2.1 AA violations fail the build, moderate ones are reported only.
- The public explorer ships a crawl of a seeded company list; a company outside it is still findable via the live register fallback, but shows register fields only until a crawler run enriches it.
- The agent uses no language model; the database has a `vector` column that is reserved for future embeddings and is not populated.
- Large companies' accounts can be temporarily unavailable from Regnskapsregisteret (HTTP 500); figures then stay empty with that reason.

## Verify it yourself
`./run.sh numbers.txt results.jsonl && python3 scripts/validate_output.py numbers.txt results.jsonl`
