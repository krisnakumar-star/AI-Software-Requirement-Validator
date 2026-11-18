import json
import logging
import os
import re
import secrets
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, model_validator

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("srs-analyzer")

VERSION = "7.0.0"
SRS_API_KEY = os.getenv("SRS_API_KEY")
app = FastAPI(
    title="SRS Requirement Analyzer",
    description="Lightweight, model-free software requirement analysis service",
    version=VERSION,
)

class AnalyzeRequest(BaseModel):
    requirement: str | None = None
    source: str | None = None
    section_number: str | None = None
    requirements: Any = None
    text: str | None = None

class BatchAnalyzeRequest(BaseModel):
    requirements: list[str] = Field(min_length=1, max_length=20)

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
        normalized = []
        for index, item in enumerate(items):
            if isinstance(item, str):
                text = item
            elif isinstance(item, dict):
                text = item.get("requirement") or item.get("text") or item.get("content") or item.get("description")
            else:
                raise ValueError(f"Requirement {index + 1} must be text or an object")
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"Requirement {index + 1} is empty or invalid")
            normalized.append(text.strip())
        return {"requirements": normalized}

def verify_api_key(x_api_key: str | None = Header(default=None)):
    if not SRS_API_KEY:
        raise HTTPException(status_code=503, detail="SRS API authentication is not configured")
    if not x_api_key or not secrets.compare_digest(x_api_key, SRS_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

# This is a transparent NLP/heuristic analyzer, not a generative LLM.
# Findings are derived from the submitted text; no external AI provider is called.
ACTION_VERBS = {
    "create", "add", "update", "delete", "remove", "submit", "display", "show",
    "send", "receive", "generate", "calculate", "search", "filter", "export",
    "import", "upload", "download", "authenticate", "authorize", "validate",
    "store", "save", "retrieve", "notify", "track", "manage", "process",
    "allow", "prevent", "support", "provide", "record", "approve", "reject",
}
VAGUE_TERMS = {
    "fast": "Define a measurable response-time target and the conditions under which it applies.",
    "quick": "Replace 'quick' with a measurable completion or response-time limit.",
    "user-friendly": "Specify the usability outcomes or acceptance criteria expected from users.",
    "easy": "Describe the task users must complete and how successful completion is measured.",
    "efficient": "Specify the resource or performance metric and its acceptable threshold.",
    "secure": "Identify the security controls, protected assets and expected threat conditions.",
    "reliable": "Specify availability, failure-rate or recovery-time expectations.",
    "scalable": "Specify expected users, workload, data volume and growth target.",
    "appropriate": "State the exact condition or rule that determines what is appropriate.",
    "soon": "Replace 'soon' with a measurable time limit.",
    "as needed": "Define the event or condition that triggers this behavior.",
    "etc": "List the remaining in-scope items explicitly or define the scope boundary.",
    "and so on": "List the remaining in-scope items explicitly or define the scope boundary.",
}
ABSOLUTE_TERMS = {"always", "never", "all", "any", "every", "none", "only"}
NON_FUNCTIONAL = {
    "performance": ["performance", "response time", "latency", "throughput", "concurrent", "load time"],
    "security": ["security", "encrypt", "encryption", "password", "authentication", "authorization", "access control", "audit"],
    "availability": ["availability", "uptime", "downtime", "available", "recovery time"],
    "usability": ["usability", "accessible", "accessibility", "easy to use", "user friendly"],
    "reliability": ["reliability", "failure rate", "fault tolerant", "recover"],
    "compatibility": ["compatible", "browser", "operating system", "platform", "device"],
    "maintainability": ["maintainable", "modular", "logging", "monitoring", "diagnostic"],
}
CONSTRAINT_TERMS = [
    "must use", "shall use", "technology", "framework", "database", "platform",
    "regulation", "compliance", "standard", "legal", "constraint", "budget",
]
ACTOR_PATTERNS = [
    r"\bthe system\b", r"\bthe user\b", r"\badministrator\b",
    r"\badmin\b", r"\bcustomer\b", r"\bmanager\b", r"\boperator\b",
    r"\bservice\b", r"\bapplication\b",
]
MODAL_RE = re.compile(r"\b(shall|must|will|should|may|can)\b", re.I)
MEASURE_RE = re.compile(r"\b(\d+(?:\.\d+)?\s*(?:ms|milliseconds?|seconds?|minutes?|hours?|days?|%|percent|users?|requests?/second|mb|gb))\b", re.I)
BOUNDARY_WORDS = ("when", "if", "unless", "after", "before", "during", "within", "provided that")
TEST_WORDS = ("verify", "confirm", "test", "display", "return", "reject", "accept", "within", "equal", "greater than", "less than")
STOP = {"the","a","an","and","or","to","of","in","on","for","by","with","from","at","is","are","be","as","it","its","this","that","shall","must","will","should","can","may","system","user"}

def words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9]+(?:[-'][a-zA-Z0-9]+)*", text.lower())

def classify(text: str) -> str:
    lower = text.lower()
    if any(term in lower for term in CONSTRAINT_TERMS) and not any(v in words(text) for v in ACTION_VERBS):
        return "Constraint"
    if any(term in lower for terms in NON_FUNCTIONAL.values() for term in terms):
        return "Non-Functional"
    if any(v in words(text) for v in ACTION_VERBS):
        return "Functional"
    if any(term in lower for term in CONSTRAINT_TERMS):
        return "Constraint"
    return "Functional"

def analyze_text(requirement: str, source: str | None = None, section_number: str | None = None) -> dict:
    text = re.sub(r"\s+", " ", requirement).strip()
    lower = text.lower()
    tokens = words(text)
    token_set = set(tokens)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    findings: list[str] = []
    ambiguities: list[str] = []
    missing: list[str] = []
    score = 100

    if len(tokens) < 5:
        findings.append("The statement is very short and provides limited context for validation.")
        missing.append("Add the responsible actor, expected behavior and relevant outcome.")
        score -= 22
    elif len(tokens) < 9:
        findings.append("The requirement contains limited detail.")
        score -= 8

    if not MODAL_RE.search(text):
        findings.append("No explicit obligation or permission term (such as shall, must, or may) is present.")
        missing.append("Clarify whether this behavior is mandatory, optional or prohibited.")
        score -= 10

    has_actor = any(re.search(pattern, lower) for pattern in ACTOR_PATTERNS)
    if not has_actor:
        ambiguities.append("The responsible actor or system component is not explicitly identified.")
        missing.append("Identify the actor or system component responsible for the behavior.")
        score -= 10

    action_hits = sorted(token_set.intersection(ACTION_VERBS))
    if not action_hits:
        ambiguities.append("The expected action or observable system behavior is not explicit.")
        missing.append("State the action the system or actor must perform.")
        score -= 14

    vague_found = []
    for phrase, recommendation in VAGUE_TERMS.items():
        if re.search(r"\b" + re.escape(phrase) + r"\b", lower):
            vague_found.append((phrase, recommendation))
            ambiguities.append(f"The term '{phrase}' is subjective or insufficiently measurable.")
            missing.append(recommendation)
            score -= 7

    if any(term in token_set for term in ABSOLUTE_TERMS) and not MEASURE_RE.search(text):
        ambiguities.append("Absolute wording may create an overly broad obligation; confirm its intended scope.")
        score -= 4

    if not any(word in lower for word in BOUNDARY_WORDS) and len(tokens) > 12:
        missing.append("Consider documenting relevant preconditions, triggering events or exception conditions.")
        score -= 4

    has_measure = bool(MEASURE_RE.search(text))
    is_quality_requirement = any(term in lower for terms in NON_FUNCTIONAL.values() for term in terms)
    if is_quality_requirement and not has_measure:
        missing.append("Add a measurable acceptance threshold for the stated quality attribute.")
        score -= 12

    if len(sentences) > 2:
        ambiguities.append("The statement combines multiple clauses; consider separating independently testable obligations.")
        score -= min(8, (len(sentences) - 2) * 3)

    conjunctions = len(re.findall(r"\b(and|or)\b", lower))
    if conjunctions >= 3:
        ambiguities.append("Several conditions or actions are joined together, which may make verification difficult.")
        score -= 5

    if len(text) > 500:
        findings.append("The requirement is lengthy; consider splitting it into smaller independently verifiable statements.")
        score -= 4

    if not any(term in lower for term in TEST_WORDS) and not has_measure and len(tokens) > 8:
        missing.append("Define an observable pass/fail outcome so a tester can verify compliance.")
        score -= 5

    # Deduplicate while preserving order.
    ambiguities = list(dict.fromkeys(ambiguities))
    missing = list(dict.fromkeys(missing))
    findings = list(dict.fromkeys(findings))

    score = max(0, min(100, score))
    if score >= 85:
        clarity, completeness, testability = "Good", "Complete" if not missing else "Partial", "Testable" if not missing else "Partially Testable"
    elif score >= 65:
        clarity, completeness, testability = "Moderate", "Partial", "Partially Testable"
    else:
        clarity, completeness, testability = "Poor", "Incomplete", "Not Testable" if not action_hits else "Partially Testable"

    classification = classify(text)
    if not findings and not ambiguities and not missing:
        findings.append("No major textual quality issue was detected by the analyzer; validate the requirement against stakeholder needs and related requirements.")

    issues = findings + [f"Ambiguity: {item}" for item in ambiguities]
    if not issues:
        issues = ["No significant issue was detected by the configured textual checks."]

    rewrite = text
    if missing or ambiguities:
        actor = "The system"
        if re.search(r"\buser\b", lower):
            actor = "The user"
        elif re.search(r"\badministrator\b|\badmin\b", lower):
            actor = "The administrator"
        modal = "shall"
        action = " ".join(sentences)
        if not MODAL_RE.search(text):
            rewrite = f"{actor} shall {action[0].lower() + action[1:] if action else text}"
        elif not has_actor and action_hits:
            rewrite = f"{actor} {action}"
        # Preserve original meaning; do not invent numeric thresholds or business rules.
        if rewrite == text:
            rewrite = text + " [Add explicit acceptance criteria for the identified missing details.]"

    explanation_parts = [
        f"Classified as {classification.lower()} based on the requirement's wording and detected subject matter.",
        f"Text length: {len(tokens)} words across {len(sentences)} sentence(s).",
        f"Detected {len(action_hits)} action verb(s)" + (f" ({', '.join(action_hits[:5])})" if action_hits else "") + ".",
        "A measurable value is present." if has_measure else "No explicit numeric performance or quantity threshold was detected.",
        f"Quality score: {score}/100. This score reflects textual clarity, completeness and testability signals, not proof of implementation correctness.",
    ]
    if source or section_number:
        explanation_parts.append(f"Document context: source={source or 'not supplied'}, section={section_number or 'not supplied'}.")

    return {
        "quality_score": score,
        "classification": classification,
        "clarity": clarity,
        "completeness": completeness,
        "testability": testability,
        "ambiguities": ambiguities,
        "missing_information": missing,
        "issues": issues,
        "suggested_rewrite": rewrite,
        "explanation": " ".join(explanation_parts),
    }

@app.get("/")
def home():
    return {
        "message": "SRS Requirement Analyzer is running",
        "version": VERSION,
        "provider": "built-in NLP analysis engine",
        "mode": "model-free",
    }

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "SRS AI Analyzer",
        "version": VERSION,
        "provider": "built-in NLP analysis engine",
        "mode": "model-free",
        "internal_auth_configured": bool(SRS_API_KEY),
    }

@app.post("/analyze")
async def analyze(request: AnalyzeRequest, _: None = Depends(verify_api_key)):
    requirement = request.requirement or request.text
    if not requirement and request.requirements is not None:
        requirement = json.dumps(request.requirements) if isinstance(request.requirements, (dict, list)) else str(request.requirements)
    if not isinstance(requirement, str) or not requirement.strip():
        raise HTTPException(status_code=400, detail="Please provide requirement text")
    requirement = requirement.strip()
    result = analyze_text(requirement, request.source, request.section_number)
    return {
        "status": "success",
        "provider": "built-in NLP analysis engine",
        "model": None,
        "requirement": requirement,
        "analysis": result,
    }

@app.post("/analyze-batch")
async def analyze_batch(request: BatchAnalyzeRequest, _: None = Depends(verify_api_key)):
    analyses = []
    for index, requirement in enumerate(request.requirements):
        result = analyze_text(requirement)
        analyses.append({
            "requirement_number": index + 1,
            "requirement": requirement,
            **result,
        })
    return {
        "status": "success",
        "provider": "built-in NLP analysis engine",
        "model": None,
        "total_requirements": len(request.requirements),
        "analyses": analyses,
    }
