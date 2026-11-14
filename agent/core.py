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

try:
    import web
except ImportError:  # website enrichment needs beautifulsoup4; registry facts still work without it
    web = None

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
                 "accounts": ["financial_revenue", "operating_result", "net_profit"],
                 "website": ["website", "social_links", "news", "jobs", "website_verified_by"]}
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


def account_history(payload: Any, number: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Filed figures for up to `limit` financial years of THIS company (parent accounts preferred), newest first.
    Figures are copied as filed; a figure a filing does not report stays null."""
    rows = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
    own = [a for a in rows if isinstance(a, dict) and str(dig(a, "virksomhet", "organisasjonsnummer")) == number]
    pref = [a for a in own if a.get("regnskapstype") == "SELSKAP"] or own
    by_end: Dict[str, Dict[str, Any]] = {}
    for acc in pref:
        end = dig(acc, "regnskapsperiode", "tilDato")
        if isinstance(end, str) and end not in by_end:
            res = acc.get("resultatregnskapResultat")
            by_end[end] = {"period_start": dig(acc, "regnskapsperiode", "fraDato"), "period_end": end,
                           "currency": _text(acc.get("valuta")) or "NOK", "account_type": acc.get("regnskapstype") or "unspecified",
                           "revenue": to_number(dig(res, "driftsresultat", "driftsinntekter", "sumDriftsinntekter")),
                           "operating_result": to_number(dig(res, "driftsresultat", "driftsresultat")),
                           "net_result": to_number(dig(res, "aarsresultat"))}
    return [by_end[k] for k in sorted(by_end, reverse=True)[:limit]]


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
