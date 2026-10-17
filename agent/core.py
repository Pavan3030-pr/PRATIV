"""Signalpost agent core: validate a Norwegian org number, query official Brreg
registers, return facts with per-fact evidence, and detect changes between runs.

Sources (all official, free, public):
  Enhetsregisteret  https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}
  ... roles         https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}/roller
  ... sub-units     https://data.brreg.no/enhetsregisteret/api/underenheter?overordnetEnhet={orgnr}
  Regnskapsregisteret (annual accounts)
                    https://data.brreg.no/regnskapsregisteret/regnskap/{orgnr}

Rules: a value is published only if it is read directly from a source response that
belongs to the requested company. Anything absent stays null with a stated reason;
nothing is estimated or derived.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

ENHETER = "https://data.brreg.no/enhetsregisteret/api/enheter"
UNDERENHETER = "https://data.brreg.no/enhetsregisteret/api/underenheter"
REGNSKAP = "https://data.brreg.no/regnskapsregisteret/regnskap"
HEADERS = {"Accept": "application/json", "User-Agent": "signalpost-agent/3.0 (Builderr Signalpost entry)"}
TIMEOUT = 10
BACKOFF = (0.5, 1.5)      # seconds between retries on HTTP 429 / 5xx / network errors
MIN_INTERVAL = 0.08       # global politeness: at most ~12 requests per second
DEFAULT_CAP = 1900        # stay safely under the 2,000 outbound requests/day limit

REGISTRY_KEYS = ["organisasjonsnummer", "navn", "organisasjonsform_kode", "stiftelsesdato",
                 "antallAnsatte", "naeringskode1_beskrivelse", "forretningsadresse"]
SOURCE_GROUPS = {"roles": ["general_manager", "chair", "board_member_count"],
                 "subunits": ["subunit_count", "subunit_sample"],
                 "accounts": ["financial_revenue", "operating_result", "net_profit"]}
EXPECTED = ["official_legal_name", "organisation_form", "registered_address", "incorporation_date",
            "industry", "employees", "website", "vat_registered", "institutional_sector",
            "company_status", "general_manager", "chair", "board_member_count", "subunit_count",
            "financial_revenue", "operating_result", "net_profit"]


class CrawlError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class Unavailable(Exception):
    pass


class RequestBudget:
    def __init__(self, cap: int = DEFAULT_CAP):
        self.cap = cap
        self.used = 0
        self._lock = threading.Lock()

    def take(self) -> None:
        with self._lock:
            if self.used >= self.cap:
                raise CrawlError(429, f"Outbound request budget of {self.cap} is exhausted.")
            self.used += 1


BUDGET = RequestBudget(int(os.getenv("SIGNALPOST_REQUEST_CAP", DEFAULT_CAP)))
_throttle_lock = threading.Lock()
_last_request = [0.0]


class Session:
    def __init__(self, budget: RequestBudget):
        self.budget = budget
        self.calls = 0


def _throttle() -> None:
    with _throttle_lock:
        wait = _last_request[0] + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.monotonic()


def http_get(url: str, sess: Session, params: Optional[Dict[str, Any]] = None):
    """GET with budget accounting and bounded retries. Returns the response object."""
    last = "unknown error"
    for attempt in range(len(BACKOFF) + 1):
        sess.budget.take()
        sess.calls += 1
        _throttle()
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last = f"network error ({exc.__class__.__name__})"
        else:
            if resp.status_code == 429 or resp.status_code >= 500:
                last = f"HTTP {resp.status_code}"
            else:
                return resp
        if attempt < len(BACKOFF):
            time.sleep(BACKOFF[attempt])
    raise Unavailable(last)


def _json(resp) -> Any:
    try:
        return resp.json()
    except ValueError:
        return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def is_valid_norwegian_org_number(number: str) -> bool:
    if not isinstance(number, str) or not re.fullmatch(r"\d{9}", number):
        return False
    weights = (2, 3, 4, 5, 6, 7) * 2
    total = sum(int(d) * w for d, w in zip(reversed(number[:8]), weights))
    check = 11 - total % 11
    if check == 11:
        check = 0
    return check != 10 and check == int(number[8])


def registry_payload(e: Dict[str, Any]) -> Dict[str, Any]:
    """The 7 registry fields behind delta_sync_hash. Identical to scripts/fetch_1000_brreg.py
    and the browser fallback, so hashes stored in db/profiles_1000.json are comparable."""
    return {
        "organisasjonsnummer": e.get("organisasjonsnummer"),
        "navn": e.get("navn"),
        "organisasjonsform_kode": (e.get("organisasjonsform") or {}).get("kode"),
        "stiftelsesdato": e.get("stiftelsesdato"),
        "antallAnsatte": e.get("antallAnsatte"),
        "naeringskode1_beskrivelse": (e.get("naeringskode1") or {}).get("beskrivelse"),
        "forretningsadresse": e.get("forretningsadresse"),
    }


def dig(obj: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def to_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    return int(num) if num.is_integer() else round(num, 2)


def _text(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


def address_text(addr: Any) -> Optional[str]:
    if not isinstance(addr, dict):
        return None
    parts = [p.strip() for p in (addr.get("adresse") or []) if isinstance(p, str) and p.strip()]
    locality = " ".join(p.strip() for p in (addr.get("postnummer", ""), addr.get("poststed", ""))
                        if isinstance(p, str) and p.strip())
    if locality:
        parts.append(locality)
    if _text(addr.get("land")):
        parts.append(addr["land"].strip())
    return ", ".join(parts) or None


def _person_name(person: Dict[str, Any]) -> Optional[str]:
    n = person.get("navn") or {}
    parts = [n.get("fornavn"), n.get("mellomnavn"), n.get("etternavn")]
    return " ".join(p.strip() for p in parts if isinstance(p, str) and p.strip()) or None


def _holder(role: Dict[str, Any]) -> Optional[str]:
    person, unit = role.get("person"), role.get("enhet")
    if isinstance(person, dict):
        return None if person.get("erDoed") else _person_name(person)
    if isinstance(unit, dict):
        name = unit.get("navn")
        return _text(" ".join(name) if isinstance(name, list) else name)
    return None


def parse_roles(payload: Any) -> Tuple[Optional[str], Optional[str], int]:
    manager = chair = None
    board = 0
    groups = payload.get("rollegrupper") if isinstance(payload, dict) else None
    for group in groups or []:
        for role in (group or {}).get("roller") or []:
            if not isinstance(role, dict) or role.get("fratraadt"):
                continue
            code, holder = dig(role, "type", "kode"), _holder(role)
            if not holder:
                continue
            if code == "DAGL" and manager is None:
                manager = holder
            if code == "LEDE" and chair is None:
                chair = holder
            if code in ("LEDE", "NEST", "MEDL"):
                board += 1
    return manager, chair, board


def pick_accounts(payload: Any, number: str) -> Tuple[Optional[Dict[str, Any]], int]:
    rows = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
    own, foreign = [], 0
    for acc in rows:
        if not isinstance(acc, dict):
            continue
        if str(dig(acc, "virksomhet", "organisasjonsnummer")) == number:
            own.append(acc)
        else:
            foreign += 1
    parent = [a for a in own if a.get("regnskapstype") == "SELSKAP"] or own
    best = max(parent, key=lambda a: str(dig(a, "regnskapsperiode", "tilDato") or ""), default=None)
    return best, foreign


class SnapshotStore:
    """Remembers what each company looked like last time, to report updates correctly."""

    def __init__(self, path: Optional[str] = None, baseline_path: Optional[str] = None):
        self.path, self.data, self._lock = path, {}, threading.RLock()
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    self.data = json.load(fh).get("companies", {})
            except (OSError, ValueError):
                self.data = {}
        if baseline_path and os.path.exists(baseline_path):
            self._load_baseline(baseline_path)

    def _load_baseline(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as fh:
                rows = json.load(fh)
        except (OSError, ValueError):
            return
        for row in rows if isinstance(rows, list) else []:
            number = row.get("organisasjonsnummer")
            if not number or number in self.data:
                continue
            stamp = row.get("fetched_at")
            self.data[number] = {
                "registry_payload": {k: row.get(k) for k in REGISTRY_KEYS},
                "registry_hash": row.get("delta_sync_hash"), "facts": None, "content_hash": None,
                "first_seen_at": stamp, "last_checked_at": stamp, "last_changed_at": stamp,
                "checks": 0, "baseline": True,
            }

    def get(self, number: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self.data.get(number))

    def put(self, number: str, entry: Dict[str, Any]) -> None:
        with self._lock:
            self.data[number] = entry

    def save(self) -> None:
        if not self.path:
            return
        with self._lock:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "companies": self.data}, fh, ensure_ascii=False)
            os.replace(tmp, self.path)


def _diff(old: Dict[str, Any], new: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"field": k, "old": old.get(k), "new": new.get(k)}
            for k in sorted(set(old) | set(new)) if old.get(k) != new.get(k)]


def detect_update(prev, payload, reg_hash, facts, content_hash, ts) -> Dict[str, Any]:
    if prev is None:
        return {"status": "new", "compared_against": None, "previous_checked_at": None,
                "last_changed_at": ts, "registry_hash_changed": False, "changed_fields": []}
    if prev.get("facts") is None:  # seeded from db/profiles_1000.json: only the registry core is comparable
        changed = _diff(prev.get("registry_payload") or {}, payload)
        status, basis = ("unchanged" if prev.get("registry_hash") == reg_hash else "changed"), "seeded_registry_core"
    else:
        changed = _diff(prev["facts"], facts)
        status, basis = ("unchanged" if prev.get("content_hash") == content_hash else "changed"), "previous_run_full_profile"
    return {"status": status, "compared_against": basis, "previous_checked_at": prev.get("last_checked_at"),
            "last_changed_at": ts if status == "changed" else prev.get("last_changed_at"),
            "registry_hash_changed": prev.get("registry_hash") != reg_hash, "changed_fields": changed}


def _optional(url, sess, logs, label, params=None):
    """Fetch a secondary source. Failure never blocks the profile; it is reported instead."""
    try:
        resp = http_get(url, sess, params)
    except (Unavailable, CrawlError) as exc:
        reason = f"{label} unavailable ({getattr(exc, 'detail', exc)})"
        logs.append(f"{label}: {reason}; related fields left empty, nothing guessed.")
        return None, reason
    if resp.status_code == 404:
        logs.append(f"{label}: no record held by this register (HTTP 404).")
        return None, "not_found"
    if resp.status_code != 200:
        reason = f"{label} returned HTTP {resp.status_code}"
        logs.append(f"{label}: {reason}; related fields left empty.")
        return None, reason
    body = _json(resp)
    if body is None:
        logs.append(f"{label}: response was not valid JSON; related fields left empty.")
        return None, f"{label} returned invalid JSON"
    return body, None


def crawl(company_number: str, store: Optional[SnapshotStore] = None,
          budget: Optional[RequestBudget] = None, now: Optional[str] = None) -> Dict[str, Any]:
    n = company_number
    sess = Session(budget or BUDGET)
    ts = now or now_iso()
    logs = [f"STEP 1: Received organization number '{n}'."]
    if not is_valid_norwegian_org_number(n):
        raise CrawlError(400, f"Invalid company number '{n}'. Must be 9 digits with a valid Modulus 11 check digit.")
    checks = [{"check": "organisation_number_checksum", "passed": True,
               "detail": "9 digits and Modulus 11 check digit are valid."}]
    logs.append("STEP 1b: 9-digit format and Modulus 11 check digit validated.")

    src_main = f"{ENHETER}/{n}"
    logs.append(f"STEP 2: GET {src_main}")
    try:
        resp = http_get(src_main, sess)
    except Unavailable as exc:
        logs.append(f"STEP 2 (UNAVAILABLE): {exc}; no profile facts were generated.")
        raise CrawlError(503, "Brreg registry is temporarily unavailable.") from exc
    if resp.status_code == 404:
        raise CrawlError(404, "No Brreg company record exists for this organization number.")
    if resp.status_code == 410:
        raise CrawlError(410, "This organization has been removed from the Brreg register.")
    if resp.status_code != 200:
        raise CrawlError(503, "Brreg registry returned an unavailable response.")
    data = _json(resp)
    if not isinstance(data, dict):
        raise CrawlError(502, "Brreg returned an invalid company record.")
    if str(data.get("organisasjonsnummer")) != n:
        raise CrawlError(502, "Brreg response organization number did not match the request.")
    name = _text(data.get("navn"))
    if not name:
        raise CrawlError(502, "Brreg response did not include a legal name.")
    checks.append({"check": "enhetsregisteret_orgnr_matches_request", "passed": True,
                   "detail": "organisasjonsnummer in the registry response equals the requested number."})
    logs.append(f"STEP 3: Official record fetched for '{name}'; organization number matches the request.")

    items: List[Dict[str, Any]] = []
    missing: Dict[str, str] = {}
    stale: List[str] = []   # keys whose source was unreachable this run (not "no data"): never reported as changed
    unavailable: List[str] = []

    def add(key, value, snippet, url, path, why):
        items.append({"key": key, "value": value, "snippet": snippet, "url": url, "path": path, "why": why})

    base_why = f"Read '{{p}}' directly from the Enhetsregisteret response for {n}; its organisasjonsnummer matched the request."
    add("official_legal_name", name, f"Legal name '{name}' returned by Brreg for organization number {n}.",
        src_main, "navn", base_why.format(p="navn"))
    form_code, form_desc = dig(data, "organisasjonsform", "kode"), dig(data, "organisasjonsform", "beskrivelse")
    if form_code or form_desc:
        form = f"{form_desc} ({form_code})" if form_code and form_desc else str(form_code or form_desc)
        add("organisation_form", form, f"Organisation form: {form}", src_main, "organisasjonsform", base_why.format(p="organisasjonsform"))
    else:
        missing["organisation_form"] = "No organisation form in the registry response."
    addr_key = "forretningsadresse" if address_text(data.get("forretningsadresse")) else "postadresse"
    address = address_text(data.get(addr_key))
    if address:
        add("registered_address", address, address, src_main, addr_key, base_why.format(p=addr_key))
    else:
        missing["registered_address"] = "No business or postal address registered."
    if _text(data.get("stiftelsesdato")):
        add("incorporation_date", data["stiftelsesdato"], data["stiftelsesdato"], src_main, "stiftelsesdato", base_why.format(p="stiftelsesdato"))
    else:
        missing["incorporation_date"] = "No founding date registered in Enhetsregisteret."
    ind_code, ind_desc = dig(data, "naeringskode1", "kode"), dig(data, "naeringskode1", "beskrivelse")
    if ind_code or ind_desc:
        industry = " ".join(str(x) for x in (ind_code, ind_desc) if x)
        add("industry", industry, f"Industry (NACE): {industry}", src_main, "naeringskode1", base_why.format(p="naeringskode1"))
    else:
        missing["industry"] = "No industry code registered."
    if isinstance(data.get("antallAnsatte"), int) and not isinstance(data.get("antallAnsatte"), bool):
        add("employees", data["antallAnsatte"], f"Registered employees: {data['antallAnsatte']}", src_main, "antallAnsatte", base_why.format(p="antallAnsatte"))
    else:
        missing["employees"] = "No employee count registered in Enhetsregisteret."
    if _text(data.get("hjemmeside")):
        add("website", data["hjemmeside"].strip(), f"Website: {data['hjemmeside'].strip()}", src_main, "hjemmeside", base_why.format(p="hjemmeside"))
    else:
        missing["website"] = "No website registered in Enhetsregisteret."
    if isinstance(data.get("registrertIMvaregisteret"), bool):
        vat = data["registrertIMvaregisteret"]
        add("vat_registered", vat, f"Registered in the VAT register: {'yes' if vat else 'no'}", src_main, "registrertIMvaregisteret", base_why.format(p="registrertIMvaregisteret"))
    else:
        missing["vat_registered"] = "VAT registration status not stated."
    sec_code, sec_desc = dig(data, "institusjonellSektorkode", "kode"), dig(data, "institusjonellSektorkode", "beskrivelse")
    if sec_code or sec_desc:
        sector = " ".join(str(x) for x in (sec_code, sec_desc) if x)
        add("institutional_sector", sector, f"Institutional sector: {sector}", src_main, "institusjonellSektorkode", base_why.format(p="institusjonellSektorkode"))
    else:
        missing["institutional_sector"] = "No institutional sector code registered."
    flags = {k: data.get(k) for k in ("konkurs", "underAvvikling", "underTvangsavviklingEllerTvangsopplosning")}
    if _text(data.get("slettedato")):
        status = f"deleted {data['slettedato']}"
    elif flags["konkurs"]:
        status = "bankrupt"
    elif flags["underAvvikling"]:
        status = "under liquidation"
    elif flags["underTvangsavviklingEllerTvangsopplosning"]:
        status = "under forced dissolution"
    elif any(isinstance(v, bool) for v in flags.values()):
        status = "active (no bankruptcy or liquidation flags set)"
    else:
        status = None
    if status:
        add("company_status", status, f"Status: {status}", src_main, "konkurs,underAvvikling,underTvangsavviklingEllerTvangsopplosning,slettedato",
            f"Derived only from the registry's own boolean flags and deletion date for {n}.")
    else:
        missing["company_status"] = "The registry response carried no status flags."
    logs.append(f"STEP 4: Extracted {len(items)} registry fact(s) from Enhetsregisteret; {len(missing)} not registered.")

    src_roles = f"{ENHETER}/{n}/roller"
    roles, why = _optional(src_roles, sess, logs, "Roles register")
    if roles is not None:
        manager, chair, board = parse_roles(roles)
        rwhy = f"Read active (not resigned) roles from the roles endpoint scoped to {n}; person data limited to name."
        if manager:
            add("general_manager", manager, f"General manager (DAGL): {manager}", src_roles, "rollegrupper[].roller[type=DAGL]", rwhy)
        else:
            missing["general_manager"] = "No active general manager (DAGL) role is registered."
        if chair:
            add("chair", chair, f"Chair of the board (LEDE): {chair}", src_roles, "rollegrupper[].roller[type=LEDE]", rwhy)
        else:
            missing["chair"] = "No active board chair (LEDE) role is registered."
        if board:
            add("board_member_count", board, f"Active board members (chair, deputy, members): {board}", src_roles, "rollegrupper[].roller[type in LEDE,NEST,MEDL]", rwhy)
        else:
            missing["board_member_count"] = "No active board roles registered (e.g. sole proprietorships have none)."
        logs.append(f"STEP 5: Roles register read; manager={'yes' if manager else 'no'}, chair={'yes' if chair else 'no'}, board members={board}.")
    else:
        for k in SOURCE_GROUPS["roles"]:
            missing[k] = "No roles on record." if why == "not_found" else why
        if why != "not_found":
            stale += SOURCE_GROUPS["roles"]
            unavailable.append("roles")

    src_sub = f"{UNDERENHETER}?overordnetEnhet={n}"
    subs, why = _optional(UNDERENHETER, sess, logs, "Sub-unit register", params={"overordnetEnhet": n, "size": 5})
    sample: List[Dict[str, Any]] = []
    if subs is not None:
        listed = (subs.get("_embedded") or {}).get("underenheter") or [] if isinstance(subs, dict) else []
        own = [u for u in listed if isinstance(u, dict) and str(u.get("overordnetEnhet")) == n]
        foreign = len(listed) - len(own)
        checks.append({"check": "subunits_belong_to_requested_parent", "passed": foreign == 0,
                       "detail": f"{foreign} sub-unit(s) with a different parent were discarded, none published."})
        total = dig(subs, "page", "totalElements")
        count = total if isinstance(total, int) and foreign == 0 else len(own)
        sample = [{"organisasjonsnummer": u.get("organisasjonsnummer"), "navn": u.get("navn")} for u in own]
        add("subunit_count", count, f"Registered sub-units (underenheter): {count}", src_sub, "page.totalElements",
            f"Count returned by the sub-unit endpoint filtered on parent {n}; each listed unit's overordnetEnhet was checked.")
        logs.append(f"STEP 6: Sub-unit register read; {count} sub-unit(s).")
    else:
        missing["subunit_count"] = "No sub-unit data." if why == "not_found" else why
        if why != "not_found":
            stale += SOURCE_GROUPS["subunits"]
            unavailable.append("subunits")

    src_acc = f"{REGNSKAP}/{n}"
    accounts, why = _optional(src_acc, sess, logs, "Annual accounts register")
    financials = None
    if accounts is not None:
        best, foreign = pick_accounts(accounts, n)
        checks.append({"check": "accounts_belong_to_requested_company", "passed": foreign == 0,
                       "detail": f"{foreign} account record(s) for other organisations were discarded, none published."})
        if best is None:
            for k in ("financial_revenue", "operating_result", "net_profit"):
                missing[k] = "No annual accounts for this company in Regnskapsregisteret."
        else:
            period = best.get("regnskapsperiode") or {}
            cur = _text(best.get("valuta")) or "NOK"
            acct_type = best.get("regnskapstype") or "unspecified"
            res = best.get("resultatregnskapResultat")
            vals = {"financial_revenue": ("Operating revenue", to_number(dig(res, "driftsresultat", "driftsinntekter", "sumDriftsinntekter")), "resultatregnskapResultat.driftsresultat.driftsinntekter.sumDriftsinntekter"),
                    "operating_result": ("Operating result", to_number(dig(res, "driftsresultat", "driftsresultat")), "resultatregnskapResultat.driftsresultat.driftsresultat"),
                    "net_profit": ("Net result for the year", to_number(dig(res, "aarsresultat")), "resultatregnskapResultat.aarsresultat")}
            label = f"period {period.get('fraDato', '?')} to {period.get('tilDato', '?')}, {acct_type} accounts"
            financials = {"period_start": period.get("fraDato"), "period_end": period.get("tilDato"), "currency": cur,
                          "account_type": acct_type, "source_url": src_acc}
            for key, (title, num, path) in vals.items():
                if num is None:
                    missing[key] = f"The latest filed accounts ({label}) do not report this figure."
                    continue
                text = f"{cur} {num:,}".replace(",", " ")
                shown = f"{text} (FY ending {period.get('tilDato', 'unknown')})"
                financials[{"financial_revenue": "revenue", "operating_result": "operating_result", "net_profit": "net_result"}[key]] = num
                add(key, shown, f"{title}: {text} ({label})", src_acc, path,
                    f"Read '{path}' from the latest Regnskapsregisteret filing whose virksomhet.organisasjonsnummer equals {n}; reported as filed, not recalculated.")
            logs.append(f"STEP 7: Annual accounts read for period ending {period.get('tilDato', 'unknown')}.")
    else:
        for k in SOURCE_GROUPS["accounts"]:
            missing[k] = "No annual accounts filed in Regnskapsregisteret." if why == "not_found" else why
        if why != "not_found":
            stale += SOURCE_GROUPS["accounts"]
            unavailable.append("accounts")
    evidences = [{"target_metric_key": i["key"], "extracted_text_snippet": i["snippet"], "source_url_link": i["url"],
                  "crawl_timestamp": ts, "explanation_chain": i["why"], "field_path": i["path"],
                  "value_sha256": sha(i["value"])} for i in items]
    facts = {i["key"]: i["value"] for i in items}
    if sample:
        facts["subunit_sample"] = sample
    payload = registry_payload(data)
    prev = store.get(n) if store else None
    stored = dict(facts)   # what we compare and remember: fresh facts + last known values of unreachable sources
    for k in stale:
        if prev and prev.get("facts") and k in prev["facts"] and k not in stored:
            stored[k] = prev["facts"][k]
    reg_hash, content_hash = sha(payload), sha(stored)
    update = detect_update(prev, payload, reg_hash, stored, content_hash, ts)
    update["sources_unavailable"] = unavailable
    if store:
        store.put(n, {"registry_payload": payload, "registry_hash": reg_hash, "facts": stored, "content_hash": content_hash,
                      "first_seen_at": (prev or {}).get("first_seen_at") or ts, "last_checked_at": ts,
                      "last_changed_at": update["last_changed_at"], "checks": (prev or {}).get("checks", 0) + 1, "baseline": False})
    logs.append(f"STEP 8: registry hash {reg_hash[:12]}..., content hash {content_hash[:12]}...; update status: {update['status']}.")
    found = [k for k in EXPECTED if k in facts]
    logs.append(f"STEP 9: {len(found)}/{len(EXPECTED)} expected fields found with evidence; {sess.calls} outbound request(s).")
    return {
        "company_number": n, "official_legal_name": name, "registered_address": address,
        "incorporation_date": facts.get("incorporation_date"), "financial_revenue": facts.get("financial_revenue"),
        "net_profit": facts.get("net_profit"), "delta_sync_hash": reg_hash, "content_hash": content_hash,
        "explainability_logs": logs, "lineage_evidences": evidences, "profile": facts, "financials": financials,
        "update": update, "match_checks": checks, "match_verified": all(c["passed"] for c in checks),
        "missing_fields": missing,
        "coverage": {"found": len(found), "expected": len(EXPECTED), "missing": [k for k in EXPECTED if k not in facts]},
        "summary": build_summary(n, facts, financials, ts), "requests_used": sess.calls,
    }


def build_summary(n: str, f: Dict[str, Any], fin: Optional[Dict[str, Any]], ts: str) -> str:
    s = f"{f['official_legal_name']} (org. nr {n})"
    s += f" is registered as {f['organisation_form']}" if "organisation_form" in f else " is a registered Norwegian organisation"
    if "incorporation_date" in f:
        s += f", founded {f['incorporation_date']}"
    if "registered_address" in f:
        s += f", at {f['registered_address']}"
    parts = [s + "."]
    if "company_status" in f:
        parts.append(f"Status: {f['company_status']}.")
    if "industry" in f:
        parts.append(f"Industry: {f['industry']}.")
    if "employees" in f:
        parts.append(f"Registered employees: {f['employees']}.")
    lead = [x for x in (f"general manager {f['general_manager']}" if "general_manager" in f else None,
                        f"board chair {f['chair']}" if "chair" in f else None) if x]
    if lead:
        parts.append("Led by " + " and ".join(lead) + ".")
    if "subunit_count" in f:
        parts.append(f"Registered sub-units: {f['subunit_count']}.")
    if fin and "financial_revenue" in f:
        parts.append(f"Latest annual accounts ({fin.get('account_type')}, period ending {fin.get('period_end')}): revenue {f['financial_revenue'].split(' (')[0]}"
                     + (f", net result {f['net_profit'].split(' (')[0]}" if "net_profit" in f else "") + ".")
    else:
        parts.append("No annual accounts figures are published for this company; none are estimated.")
    parts.append(f"All facts come from the Brønnøysund Register Centre, retrieved {ts}, each with its own source link.")
    return " ".join(parts)
