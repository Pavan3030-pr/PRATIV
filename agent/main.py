import logging
import os
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import core

ROOT = Path(__file__).resolve().parent.parent
STORE = core.SnapshotStore(
    os.getenv("SIGNALPOST_STATE", str(Path(__file__).resolve().parent / "data" / "state.json")),
    os.getenv("SIGNALPOST_BASELINE", str(ROOT / "db" / "profiles_1000.json")),
)

log = logging.getLogger("signalpost.agent")

# Browsers may only call the agent cross-origin from explicitly configured origins. Server-to-server
# callers (the Spring Boot backend, run.sh, evaluators) are unaffected. Empty by default.
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("SIGNALPOST_ALLOWED_ORIGINS", "").split(",") if o.strip()]
RATE_LIMIT_PER_MIN = int(os.getenv("SIGNALPOST_RATE_LIMIT_PER_MIN", "300"))

app = FastAPI(
    title="SIGNALPOST Company Intelligence Agent",
    description="Finds Norwegian company facts from official Brreg registers, with per-fact evidence and update detection.",
    version="3.1.0",
)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=False,
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization", "X-Request-ID"])

_hits: Dict[str, Deque[float]] = {}


def _rate_limited(client: str) -> bool:
    now = time.monotonic()
    if len(_hits) > 2000:                     # bound memory under a wide scan of client addresses
        _hits.clear()
    q = _hits.setdefault(client, deque())
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT_PER_MIN:
        return True
    q.append(now)
    return False


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request id to every response and apply a simple per-client request budget."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    if request.url.path not in ("/health", "/ready") and _rate_limited(request.client.host if request.client else "unknown"):
        return JSONResponse({"error": "Rate limit exceeded. Try again in a minute.", "request_id": request_id},
                            status_code=429, headers={"Retry-After": "60", "X-Request-ID": request_id})
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


def _error(request: Request, status: int, detail: Any) -> JSONResponse:
    return JSONResponse({"error": detail, "request_id": getattr(request.state, "request_id", None)},
                        status_code=status)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return _error(request, exc.status_code, exc.detail)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    log.exception("Unhandled agent error for %s", request.url.path, exc_info=exc)
    return _error(request, 500, "Unexpected agent error. The request was not retried.")


class CrawlResponse(BaseModel):
    company_number: str
    official_legal_name: Optional[str] = None
    registered_address: Optional[str] = None
    incorporation_date: Optional[str] = None
    financial_revenue: Optional[str] = None
    net_profit: Optional[str] = None
    delta_sync_hash: str
    content_hash: str
    explainability_logs: List[str]
    lineage_evidences: List[Dict[str, Any]]
    profile: Dict[str, Any]
    financials: Optional[Dict[str, Any]] = None
    update: Dict[str, Any]
    match_checks: List[Dict[str, Any]]
    match_verified: bool
    missing_fields: Dict[str, str]
    coverage: Dict[str, Any]
    summary: str
    requests_used: int
    website: Dict[str, Any] = {}
    social_links: List[Dict[str, Any]] = []
    news: List[Dict[str, Any]] = []
    jobs: List[Dict[str, Any]] = []


class BatchRequest(BaseModel):
    company_numbers: List[str]


@app.post("/api/v1/crawl-batch")
def run_crawl_batch(request: BatchRequest):
    """One result per input number, in input order. A bad or missing company yields an error entry, never a failed request."""
    numbers = list(dict.fromkeys(n.strip() for n in request.company_numbers if isinstance(n, str) and n.strip()))
    if not numbers:
        raise HTTPException(status_code=400, detail="company_numbers must contain at least one organisation number.")
    if len(numbers) > 200:
        raise HTTPException(status_code=413, detail="At most 200 organisation numbers per batch.")
    results = []
    for number in numbers:
        try:
            results.append(core.crawl(number, store=STORE))
        except core.CrawlError as exc:
            results.append({"company_number": number, "error": exc.detail, "status": exc.status})
        except Exception as exc:  # one bad company must never lose the rest of the batch
            results.append({"company_number": number, "error": f"Unexpected error ({exc.__class__.__name__})", "status": 500})
    STORE.save()
    return {"count": len(results), "results": results}


@app.get("/health")
def health_check():
    return {"status": "HEALTHY", "service": "signalpost-agent", "version": "3.1.0",
            "requests_used": core.BUDGET.used, "request_cap": core.BUDGET.cap}


@app.get("/ready")
def readiness_check():
    return {"status": "READY", "service": "signalpost-agent", "version": "3.1.0"}


@app.post("/api/v1/crawl/{company_number}", response_model=CrawlResponse)
def run_crawl_pipeline(company_number: str):
    try:
        result = core.crawl(company_number, store=STORE)
    except core.CrawlError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    STORE.save()
    return result
