
import os
import json
import logging
import secrets
import re
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel, Field, model_validator

load_dotenv()

# ==================================================
# APPLICATION CONFIGURATION
# ==================================================

app = FastAPI(
    title="AI Software Requirement Validator",
    description="AI-powered SRS analysis using JarvisClaw",
    version="6.0.0"
)

# ==================================================
# JARVISCLAW CONFIGURATION
# ==================================================

LLM_BASE_URL = "https://api.jarvisclaw.ai/v1/chat/completions"
LLM_MODEL = os.getenv("LLM_MODEL", "auto/free")
SRS_API_KEY = os.getenv("SRS_API_KEY")
LLM_TIMEOUT = 90.0
logger = logging.getLogger("requirement-validator.jarvisclaw")


# ==================================================
# REQUEST MODELS
# ==================================================

class AnalyzeRequest(BaseModel):
    requirement: str | None = None
    source: str | None = None
    section_number: str | None = None
    requirements: Any = None
    text: str | None = None


class BatchAnalyzeRequest(BaseModel):

    requirements: list[str] = Field(
        min_length=1,
        max_length=20
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_batch_payload(cls, value):

        if isinstance(value, list):
            value = {"requirements": value}

        if not isinstance(value, dict):
            raise ValueError(
                "Batch request must be a JSON object or array"
            )

        requirements = value.get("requirements")

        if requirements is None:
            for key in ("items", "texts", "requirementTexts"):
                if value.get(key) is not None:
                    requirements = value[key]
                    break

        if not isinstance(requirements, list):
            raise ValueError(
                "Provide requirements as a list"
            )

        normalized = []

        for index, item in enumerate(requirements):

            if isinstance(item, str):
                text = item

            elif isinstance(item, dict):
                text = (
                    item.get("requirement")
                    or item.get("text")
                    or item.get("content")
                    or item.get("description")
                )

            else:
                raise ValueError(
                    f"Requirement {index + 1} must be text or an object"
                )

            if not isinstance(text, str) or not text.strip():
                raise ValueError(
                    f"Requirement {index + 1} is empty or invalid"
                )

            normalized.append(text.strip())

        return {"requirements": normalized}


# ==================================================
# INTERNAL API AUTHENTICATION
# ==================================================

def verify_api_key(
    x_api_key: str | None = Header(default=None)
):

    if not SRS_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="SRS API authentication is not configured"
        )

    if not x_api_key or not secrets.compare_digest(
        x_api_key,
        SRS_API_KEY
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key"
        )


# ==================================================
# JSON RESPONSE PARSER
# ==================================================

def parse_json_response(content: str) -> dict:

    if not isinstance(content, str) or not content.strip():
        raise HTTPException(
            status_code=502,
            detail="AI returned empty content"
        )

    content = content.strip()

    # Remove Markdown code fences.
    content = re.sub(
        r"^```(?:json)?\s*",
        "",
        content,
        flags=re.IGNORECASE
    )

    content = re.sub(
        r"\s*```$",
        "",
        content
    ).strip()

    try:
        result = json.loads(content)

    except json.JSONDecodeError:

        # Recover a JSON object if the model added surrounding text.
        start = content.find("{")
        end = content.rfind("}")

        if start == -1 or end <= start:
            raise HTTPException(
                status_code=502,
                detail="AI returned invalid JSON"
            )

        try:
            result = json.loads(content[start:end + 1])

        except json.JSONDecodeError:
            raise HTTPException(
                status_code=502,
                detail="AI returned malformed JSON"
            )

    if not isinstance(result, dict):
        raise HTTPException(
            status_code=502,
            detail="AI response must be a JSON object"
        )

    return result


# ==================================================
# SRS ANALYSIS SYSTEM PROMPT
# ==================================================

SYSTEM_PROMPT = """
You are an expert Software Requirements Specification
(SRS) analyst.

Analyze the supplied software requirement objectively.

Evaluate:

1. Clarity
2. Completeness
3. Testability
4. Feasibility
5. Consistency
6. Ambiguity
7. Missing information
8. Requirement classification

Do not invent facts that are absent from the requirement.

If information is missing, identify it explicitly.

Do not mark a requirement incorrect merely because
implementation details are not provided.

Return ONLY one valid JSON object using this structure:

{
    "quality_score": 0,
    "classification": "Functional",
    "clarity": "Good",
    "completeness": "Complete",
    "testability": "Testable",
    "ambiguities": [],
    "missing_information": [],
    "issues": [],
    "suggested_rewrite": "",
    "explanation": ""
}

Rules:

- quality_score must be an integer from 0 to 100.
- classification must be Functional, Non-Functional or Constraint.
- clarity must be Good, Moderate or Poor.
- completeness must be Complete, Partial or Incomplete.
- testability must be Testable, Partially Testable or Not Testable.
- Findings must be supported by the supplied requirement.
- Suggested rewrites must preserve the original intent.
- Return all required fields.
- Do not include Markdown around the JSON.
- Analyze only the requirement provided in the current request.
"""


# ==================================================
# JARVISCLAW API REQUEST
# ==================================================

def safe_upstream_error(response: httpx.Response) -> str:
    """Extract a concise provider error without logging credentials or prompts."""
    try:
        payload = response.json()
    except ValueError:
        payload = None

    error = payload.get("error", payload) if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = error.get("message") or error.get("detail") or error.get("error_description")
        code = error.get("code") or error.get("type")
        detail = str(message) if message else ""
        if code:
            detail = f"{detail} ({code})" if detail else str(code)
    elif isinstance(error, str):
        detail = error
    else:
        detail = " ".join((response.text or "").split())

    detail = detail or "No error detail was returned by the provider."
    detail = re.sub(r"(?i)bearer\s+[^\s,;]+", "Bearer [REDACTED]", detail)
    detail = re.sub(
        r"(?i)((?:api[_ -]?key|access[_ -]?token|authorization)\s*[:=]\s*)[^\s,;]+",
        r"\1[REDACTED]",
        detail,
    )
    for name, value in os.environ.items():
        if value and len(value) >= 8 and any(term in name.upper() for term in ("KEY", "TOKEN", "SECRET", "AUTH")):
            detail = detail.replace(value, "[REDACTED]")
    return detail[:600]

async def call_llm(
    system_prompt: str,
    user_prompt: str
) -> dict:

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        "max_tokens": 2500
    }

    try:

        async with httpx.AsyncClient(
            timeout=LLM_TIMEOUT
        ) as client:

            response = await client.post(
                LLM_BASE_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json"
                }
            )

            logger.info("JarvisClaw returned HTTP %s", response.status_code)

            if response.status_code != 200:
                upstream_detail = safe_upstream_error(response)
                logger.error(
                    "JarvisClaw request failed (HTTP %s): %s",
                    response.status_code,
                    upstream_detail,
                )

                if response.status_code == 401:
                    category = "JarvisClaw rejected the request"

                elif response.status_code == 403:
                    category = "JarvisClaw denied access"

                elif response.status_code == 404:
                    category = "JarvisClaw endpoint or model not found"

                elif response.status_code == 429:
                    category = "JarvisClaw rate limit reached"

                elif response.status_code == 402:
                    category = "JarvisClaw requires payment or credits"

                elif response.status_code >= 500:
                    category = "JarvisClaw is temporarily unavailable"

                else:
                    category = f"JarvisClaw returned HTTP {response.status_code}"

                raise HTTPException(
                    status_code=502,
                    detail=f"{category}: {upstream_detail}"
                )

            try:
                data = response.json()

            except ValueError:
                raise HTTPException(
                    status_code=502,
                    detail="JarvisClaw returned invalid response JSON"
                )

        choices = data.get("choices", [])

        if not choices:
            raise HTTPException(
                status_code=502,
                detail="JarvisClaw returned no response choices"
            )

        content = (
            choices[0]
            .get("message", {})
            .get("content")
        )

        if not isinstance(content, str) or not content.strip():
            raise HTTPException(
                status_code=502,
                detail="JarvisClaw returned empty AI content"
            )

        try:
            result = parse_json_response(content)

            print("JarvisClaw response parsed successfully")

            return result

        except HTTPException as exc:

            print(
                "AI RESPONSE PARSING ERROR:",
                exc.detail
            )

            # Do not print full requirement or potentially sensitive AI output.
            raise

    except HTTPException:
        raise

    except httpx.TimeoutException:

        print("JarvisClaw request timed out")

        raise HTTPException(
            status_code=504,
            detail="AI gateway request timed out"
        )

    except httpx.RequestError as exc:

        print(
            "JarvisClaw connection error:",
            type(exc).__name__
        )

        raise HTTPException(
            status_code=502,
            detail="Could not connect to JarvisClaw"
        )

    except Exception as exc:

        print(
            "Unexpected AI processing error:",
            type(exc).__name__
        )

        raise HTTPException(
            status_code=502,
            detail="AI analysis failed"
        )


# ==================================================
# VALIDATE ANALYSIS RESULT
# ==================================================

def validate_analysis(result: dict) -> dict:

    required_fields = [
        "quality_score",
        "classification",
        "clarity",
        "completeness",
        "testability",
        "ambiguities",
        "missing_information",
        "issues",
        "suggested_rewrite",
        "explanation"
    ]

    missing_fields = [
        field
        for field in required_fields
        if field not in result
    ]

    if missing_fields:
        raise HTTPException(
            status_code=502,
            detail=(
                "AI response is missing required fields: "
                + ", ".join(missing_fields)
            )
        )

    score = result["quality_score"]

    if (
        isinstance(score, bool)
        or not isinstance(score, int)
        or not 0 <= score <= 100
    ):
        raise HTTPException(
            status_code=502,
            detail="AI returned an invalid quality score"
        )

    classifications = [
        "Functional",
        "Non-Functional",
        "Constraint"
    ]

    if result["classification"] not in classifications:
        raise HTTPException(
            status_code=502,
            detail="AI returned an invalid classification"
        )

    allowed_clarity = ["Good", "Moderate", "Poor"]

    if result["clarity"] not in allowed_clarity:
        raise HTTPException(
            status_code=502,
            detail="AI returned invalid clarity"
        )

    allowed_completeness = [
        "Complete",
        "Partial",
        "Incomplete"
    ]

    if result["completeness"] not in allowed_completeness:
        raise HTTPException(
            status_code=502,
            detail="AI returned invalid completeness"
        )

    allowed_testability = [
        "Testable",
        "Partially Testable",
        "Not Testable"
    ]

    if result["testability"] not in allowed_testability:
        raise HTTPException(
            status_code=502,
            detail="AI returned invalid testability"
        )

    for field in [
        "ambiguities",
        "missing_information",
        "issues"
    ]:
        values = result[field]
        if not isinstance(values, list) or any(
            not isinstance(value, str) for value in values
        ):
            raise HTTPException(
                status_code=502,
                detail=f"AI returned invalid {field}: expected a list of strings"
            )

    for field in [
        "suggested_rewrite",
        "explanation"
    ]:
        if not isinstance(result[field], str):
            raise HTTPException(
                status_code=502,
                detail=f"AI returned invalid {field}"
            )

    return result


# ==================================================
# ANALYZE ONE REQUIREMENT
# ==================================================

async def analyze_requirement(
    requirement: str,
    source: str | None = None,
    section_number: str | None = None
) -> dict:

    user_prompt = f"""
Analyze the following software requirement.

Requirement:
{requirement}

Source:
{source or "Not provided"}

Section:
{section_number or "Not provided"}

Return one complete analysis using the required JSON structure.
"""

    result = await call_llm(
        SYSTEM_PROMPT,
        user_prompt
    )

    return validate_analysis(result)


# ==================================================
# HOME ENDPOINT
# ==================================================

@app.get("/")
def home():

    return {
        "message": "AI Requirement Validator is running",
        "version": "6.0.0",
        "provider": "JarvisClaw",
        "model": LLM_MODEL
    }


# ==================================================
# HEALTH ENDPOINT
# ==================================================

@app.get("/health")
def health():

    return {
        "status": "ok",
        "service": "SRS AI Analyzer",
        "provider": "JarvisClaw",
        "model": LLM_MODEL,
        "internal_auth_configured": bool(SRS_API_KEY)
    }


# ==================================================
# SINGLE REQUIREMENT ANALYSIS
# ==================================================

@app.post("/analyze")
async def analyze(
    request: AnalyzeRequest,
    _: None = Depends(verify_api_key)
):

    requirement = request.requirement or request.text

    if not requirement and request.requirements is not None:

        if isinstance(request.requirements, (dict, list)):
            requirement = json.dumps(request.requirements)

        else:
            requirement = str(request.requirements)

    if not isinstance(requirement, str) or not requirement.strip():
        raise HTTPException(
            status_code=400,
            detail="Please provide requirement text"
        )

    requirement = requirement.strip()

    result = await analyze_requirement(
        requirement,
        request.source,
        request.section_number
    )

    return {
        "status": "success",
        "provider": "JarvisClaw",
        "model": LLM_MODEL,
        "requirement": requirement,
        "analysis": result
    }


# ==================================================
# BATCH REQUIREMENT ANALYSIS
# ==================================================

@app.post("/analyze-batch")
async def analyze_batch(
    request: BatchAnalyzeRequest,
    _: None = Depends(verify_api_key)
):

    requirements = request.requirements

    print(
        f"Starting batch analysis: {len(requirements)} requirements"
    )

    analyses = []

    # Analyze each requirement independently.
    # This avoids malformed or incomplete batch JSON from the LLM.

    for index, requirement in enumerate(requirements):

        print(
            f"Analyzing requirement {index + 1}/{len(requirements)}"
        )

        try:

            analysis = await analyze_requirement(
                requirement
            )

            analyses.append({
                "requirement_number": index + 1,
                "requirement": requirement,
                **analysis
            })

        except HTTPException as exc:

            print(
                f"Batch analysis failed at item {index + 1}:",
                exc.detail
            )

            raise HTTPException(
                status_code=exc.status_code,
                detail={
                    "message": "Batch analysis failed",
                    "failed_requirement": index + 1,
                    "total_requirements": len(requirements),
                    "reason": exc.detail
                }
            )

    print(
        f"Batch analysis completed: {len(analyses)} requirements"
    )

    return {
        "status": "success",
        "provider": "JarvisClaw",
        "model": LLM_MODEL,
        "total_requirements": len(requirements),
        "analyses": analyses
    }


# ==================================================
# SHUTDOWN
# ==================================================

@app.on_event("shutdown")
async def shutdown_event():

    print("SRS AI Analyzer shutting down")
