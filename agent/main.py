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
    version="3.0.0",
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


@app.get("/health")
def health_check():
    return {"status": "HEALTHY", "service": "signalpost-agent", "version": "3.0.0",
            "requests_used": core.BUDGET.used, "request_cap": core.BUDGET.cap}


@app.post("/api/v1/crawl/{company_number}", response_model=CrawlResponse)
def run_crawl_pipeline(company_number: str):
    try:
        result = core.crawl(company_number, store=STORE)
    except core.CrawlError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    STORE.save()
    return result
