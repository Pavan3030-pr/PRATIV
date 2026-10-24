import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import core

ROOT = Path(__file__).resolve().parent.parent
STORE = core.SnapshotStore(
    os.getenv("SIGNALPOST_STATE", str(Path(__file__).resolve().parent / "data" / "state.json")),
    os.getenv("SIGNALPOST_BASELINE", str(ROOT / "db" / "profiles_1000.json")),
)

app = FastAPI(
    title="SIGNALPOST Company Intelligence Agent",
    description="Finds Norwegian company facts from official Brreg registers, with per-fact evidence and update detection.",
    version="3.1.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])


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


@app.post("/api/v1/crawl/{company_number}", response_model=CrawlResponse)
def run_crawl_pipeline(company_number: str):
    try:
        result = core.crawl(company_number, store=STORE)
    except core.CrawlError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    STORE.save()
    return result
