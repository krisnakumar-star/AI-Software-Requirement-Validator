"""ReqValidator SRS analysis service.

All analysis runs locally in this process (deterministic NLP + rules, optional
local embedding model). No external AI inference service is called.
"""
import json
import logging
import os
import secrets
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, model_validator

from srs_engine import ENGINE_VERSION, analyze_batch as engine_batch, analyze_single, engine_status

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("srs-analyzer")

VERSION = ENGINE_VERSION
PROVIDER = "built-in NLP analysis engine"
SRS_API_KEY = os.getenv("SRS_API_KEY")  # internal Spring Boot <-> FastAPI key, not an AI-provider key
MAX_REQUIREMENT_CHARS = int(os.getenv("MAX_REQUIREMENT_CHARS", "5000"))
MAX_BATCH_REQUIREMENTS = int(os.getenv("MAX_BATCH_REQUIREMENTS", "500"))
MAX_BATCH_CHARS = int(os.getenv("MAX_BATCH_CHARS", "600000"))

app = FastAPI(
    title="SRS Requirement Analyzer",
    description="Local SRS intelligence engine: classification, defect detection, cross-requirement analysis and reports. No external AI APIs.",
    version=VERSION,
)


class AnalyzeRequest(BaseModel):
    requirement: str | None = None
    source: str | None = None
    section_number: str | None = None
    requirement_id: str | None = None
    requirements: Any = None
    text: str | None = None


class BatchAnalyzeRequest(BaseModel):
    requirements: list[str] = Field(min_length=1)
    records: list[dict] = Field(default_factory=list)
    project_name: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_batch_payload(cls, value):
        if isinstance(value, list):
            value = {"requirements": value}
        if not isinstance(value, dict):
            raise ValueError("Batch request must be a JSON object or array")
        items = value.get("requirements")
        if items is None:
            for key in ("items", "texts", "requirementTexts"):
                if value.get(key) is not None:
                    items = value[key]
                    break
        if not isinstance(items, list):
            raise ValueError("Provide requirements as a list")
        if not items:
            raise ValueError("Provide at least one requirement")
        if len(items) > MAX_BATCH_REQUIREMENTS:
            raise ValueError(f"A batch may contain at most {MAX_BATCH_REQUIREMENTS} requirements")
        texts, records, total = [], [], 0
        for index, item in enumerate(items):
            meta = {}
            if isinstance(item, str):
                text = item
            elif isinstance(item, dict):
                text = item.get("requirement") or item.get("text") or item.get("content") or item.get("description")
                meta = {
                    "requirement_id": item.get("requirement_id") or item.get("requirementId") or item.get("section_number"),
                    "section": item.get("section") or item.get("source_section"),
                    "source": item.get("source"),
                }
            else:
                raise ValueError(f"Requirement {index + 1} must be text or an object")
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"Requirement {index + 1} is empty or invalid")
            if len(text) > MAX_REQUIREMENT_CHARS:
                raise ValueError(f"Requirement {index + 1} exceeds {MAX_REQUIREMENT_CHARS} characters")
            total += len(text)
            texts.append(text.strip())
            records.append({"text": text.strip(), **{k: (str(v).strip() if v else None) for k, v in meta.items()}})
        if total > MAX_BATCH_CHARS:
            raise ValueError(f"The batch exceeds {MAX_BATCH_CHARS} characters; split it into smaller batches")
        project = value.get("project_name") or next((r.get("source") for r in records if r.get("source")), None)
        return {"requirements": texts, "records": records, "project_name": project}


def verify_api_key(x_api_key: str | None = Header(default=None)):
    if not SRS_API_KEY:
        raise HTTPException(status_code=503, detail="SRS API authentication is not configured")
    if not x_api_key or not secrets.compare_digest(x_api_key, SRS_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get("/")
def home():
    return {"message": "SRS Requirement Analyzer is running", "version": VERSION, "provider": PROVIDER,
            "mode": "local", "external_provider_required": False}


@app.get("/health")
def health():
    return {"status": "ok", "service": "SRS AI Analyzer", "version": VERSION, "provider": PROVIDER, "mode": "local",
            "external_provider_required": False, "internal_auth_configured": bool(SRS_API_KEY),
            "limits": {"max_batch_requirements": MAX_BATCH_REQUIREMENTS, "max_requirement_chars": MAX_REQUIREMENT_CHARS},
            **engine_status()}


@app.post("/analyze")
async def analyze(request: AnalyzeRequest, _: None = Depends(verify_api_key)):
    requirement = request.requirement or request.text
    if not requirement and request.requirements is not None:
        requirement = json.dumps(request.requirements) if isinstance(request.requirements, (dict, list)) else str(request.requirements)
    if not isinstance(requirement, str) or not requirement.strip():
        raise HTTPException(status_code=400, detail="Please provide requirement text")
    if len(requirement) > MAX_REQUIREMENT_CHARS:
        raise HTTPException(status_code=413, detail=f"Requirement exceeds {MAX_REQUIREMENT_CHARS} characters")
    requirement = requirement.strip()
    result = analyze_single(requirement, request.requirement_id, request.source, request.section_number)
    return {"status": "success", "provider": PROVIDER, "model": None, "requirement": requirement, "analysis": result}


@app.post("/analyze-batch")
async def analyze_batch(request: BatchAnalyzeRequest, _: None = Depends(verify_api_key)):
    records = request.records or [{"text": t} for t in request.requirements]
    result = engine_batch(records, request.project_name)
    analyses = [{"requirement_number": i + 1, "requirement": records[i]["text"], **a} for i, a in enumerate(result["analyses"])]
    report = result["document_report"]
    findings = report["project_findings"]
    legacy_cross = [
        {"type": "possible_duplicate", "severity": "medium", "requirements": d["requirements"], "message": d["explanation"],
         "recommendation": d["recommendation"]} for d in findings["duplicates"]
    ] + [
        {"type": "possible_conflict", "severity": c["severity"], "requirements": c["requirements"], "message": c["explanation"],
         "recommendation": c["recommendation"]} for c in findings["contradictions"]
    ]
    return {
        "status": "success",
        "provider": PROVIDER,
        "model": None,
        "engine_version": VERSION,
        "total_requirements": len(analyses),
        "average_quality_score": report["executive_summary"]["overall_score"],
        "category_summary": report["quality_assessment"]["category_distribution"],
        "cross_requirement_findings": legacy_cross,
        "document_report": report,
        "analyses": analyses,
    }
