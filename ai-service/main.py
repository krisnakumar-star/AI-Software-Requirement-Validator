import json
import logging
import os
import re
import secrets
from collections import Counter
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, model_validator

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("srs-analyzer")

VERSION = "9.0.0"
SRS_API_KEY = os.getenv("SRS_API_KEY")
app = FastAPI(
    title="SRS Requirement Analyzer",
    description="Multi-dimensional, model-free software requirement analysis service",
    version=VERSION,
)

class AnalyzeRequest(BaseModel):
    requirement: str | None = None
    source: str | None = None
    section_number: str | None = None
    requirements: Any = None
    text: str | None = None

class BatchAnalyzeRequest(BaseModel):
    requirements: list[str] = Field(min_length=1, max_length=100)

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

# Transparent deterministic NLP/rule engine. It is not a trained or generative LLM.
ACTION_VERBS = {
    "create", "add", "update", "delete", "remove", "submit", "display", "show", "send",
    "receive", "generate", "calculate", "search", "filter", "export", "import", "upload",
    "download", "authenticate", "authorize", "validate", "store", "save", "retrieve",
    "notify", "track", "manage", "process", "allow", "prevent", "support", "provide",
    "record", "approve", "reject", " encrypt", "encrypt", "backup", "restore", "synchronize",
    "sync", "monitor", "log", "respond", "return", "route", "verify", "assign", "configure",
    "cancel", "schedule", "pay", "calculate", "convert", "lock", "unlock", "archive",
}
VAGUE = {
    "fast": "Replace 'fast' with a response-time or throughput threshold and test conditions.",
    "quick": "Specify the maximum completion time instead of 'quick'.",
    "user-friendly": "Define usability outcomes, target users and task-completion criteria.",
    "easy": "Name the user task and define how successful completion is measured.",
    "efficient": "Name the resource/performance metric and its acceptable threshold.",
    "secure": "Specify controls, protected assets, threat assumptions and verification criteria.",
    "reliable": "Define an availability, failure-rate, or recovery objective.",
    "scalable": "Specify expected users, workload, data volume and growth.",
    "appropriate": "Replace 'appropriate' with an explicit rule or condition.",
    "soon": "Replace 'soon' with a measurable time limit.",
    "as needed": "Define the event or condition that triggers the behavior.",
    "etc": "Enumerate the remaining in-scope items or define a clear scope boundary.",
    "and so on": "Enumerate the remaining in-scope items or define a clear scope boundary.",
    "minimal": "Define the maximum/minimum acceptable value.",
    "maximum": "Specify the numeric maximum and its unit.",
    "minimum": "Specify the numeric minimum and its unit.",
    "normally": "Define the exact conditions and behavior for each relevant case.",
    "user-friendly": "Define measurable usability criteria for the target user group.",
}
CATEGORY_RULES = {
    "Security": ["security", "encrypt", "encryption", "password", "authentication", "authorization", "access control", "role-based", "multi-factor", "mfa", "audit log", "session"],
    "Performance": ["performance", "response time", "latency", "throughput", "load time", "concurrent", "requests per second", "milliseconds", "seconds"],
    "Availability": ["availability", "uptime", "downtime", "available", "service level", "failover"],
    "Reliability": ["reliability", "failure rate", "fault tolerant", "recover", "retry", "data loss", "recovery point", "recovery time"],
    "Usability": ["usability", "accessible", "accessibility", "easy to use", "user friendly", "learnability", "screen reader"],
    "Compatibility": ["compatible", "browser", "operating system", "platform", "device", "ios", "android", "windows", "linux"],
    "Maintainability": ["maintainable", "modular", "logging", "monitoring", "diagnostic", "code quality", "deployment"],
    "Privacy": ["privacy", "personal data", "sensitive data", "consent", "data retention", "erase personal", "anonymize", "gdpr"],
    "Interface / Integration": ["api", "interface", "integration", "webhook", "json", "xml", "http", "endpoint", "third-party", "external system"],
    "Data": ["database", "data", "record", "field", "schema", "backup", "restore", "import", "export", "validation"],
    "Regulatory / Compliance": ["compliance", "regulation", "regulatory", "standard", "iso ", "pci", "hipaa", "gdpr", "legal"],
}
CONSTRAINT_TERMS = ["must use", "shall use", "technology", "framework", "database", "platform", "regulation", "compliance", "standard", "legal", "constraint", "budget", "shall be developed using"]
ACTOR_PATTERNS = [
    r"\bthe system\b", r"\bthe application\b", r"\bthe platform\b", r"\bthe service\b",
    r"\bthe user\b", r"\ban? administrator\b", r"\badmin\b", r"\bcustomer\b",
    r"\bmanager\b", r"\boperator\b", r"\bclient\b", r"\bserver\b", r"\bapi\b",
    r"\b[\w-]+ service\b",
]
MODAL_RE = re.compile(r"\b(shall|must|will|should|may|can|cannot|must not|shall not)\b", re.I)
NUMBER_UNIT_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:ms|milliseconds?|seconds?|minutes?|hours?|days?|weeks?|months?|%|percent|users?|requests?\s*/\s*second|req/s|mb|gb|tb|records?|items?)\b", re.I)
BOUNDARIES = ("when", "if", "unless", "after", "before", "during", "within", "provided that", "once", "until")
PRONOUNS = {"it", "they", "them", "this", "that", "these", "those"}
STOP = {"the","a","an","and","or","to","of","in","on","for","by","with","from","at","is","are","be","as","it","its","this","that","shall","must","will","should","can","may","system","user"}

def words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9]+(?:[-'][a-zA-Z0-9]+)*", text.lower())

def unique(items):
    return list(dict.fromkeys(items))

def classify(text: str) -> tuple[str, list[str]]:
    lower = text.lower()
    categories = [name for name, terms in CATEGORY_RULES.items() if any(term in lower for term in terms)]
    if any(term in lower for term in ("shall use", "must use", "technology stack", "framework", "database platform", "budget constraint")):
        categories.append("Technical Constraint")
    if re.search(r"\b(as a|i want|so that)\b", lower):
        categories.append("User Story")
    if re.search(r"\b(if|when|unless)\b", lower) and re.search(r"\b(then|otherwise)\b", lower):
        categories.append("Business Rule")
    if not categories:
        categories.append("Functional" if set(words(text)) & ACTION_VERBS else "Unclassified")
    primary = categories[0]
    if primary in {"Security","Performance","Availability","Reliability","Usability","Compatibility","Maintainability","Privacy","Interface / Integration","Data","Regulatory / Compliance"}:
        primary = "Non-Functional"
    return primary, unique(categories)

def add_issue(items, severity, code, message, recommendation):
    items.append({"severity": severity, "code": code, "message": message, "recommendation": recommendation})

def analyze_text(requirement: str, source: str | None = None, section_number: str | None = None) -> dict:
    text = re.sub(r"\s+", " ", requirement).strip()
    lower = text.lower()
    tokens = words(text)
    token_set = set(tokens)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    issues = []
    ambiguities, missing, recommendations = [], [], []
    score_parts = {"clarity": 100, "completeness": 100, "testability": 100, "atomicity": 100, "consistency": 100}

    def issue(severity, code, message, recommendation, dimension="clarity", deduction=5):
        add_issue(issues, severity, code, message, recommendation)
        recommendations.append(recommendation)
        score_parts[dimension] = max(0, score_parts[dimension] - deduction)

    if len(tokens) < 5:
        issue("high", "TOO_SHORT", "The statement is too short to establish a verifiable requirement.", "Specify the actor, trigger, behavior, and expected outcome.", "completeness", 25)
    elif len(tokens) < 9:
        issue("medium", "LOW_DETAIL", "The requirement contains limited context.", "Add relevant preconditions, input conditions, and expected results.", "completeness", 10)

    if not MODAL_RE.search(text):
        issue("medium", "MISSING_MODAL", "No obligation or permission level is stated.", "Use shall/must for mandatory behavior, may for optional behavior, or shall not for prohibition.", "clarity", 10)
    if not any(re.search(p, lower) for p in ACTOR_PATTERNS):
        issue("medium", "MISSING_ACTOR", "The responsible actor or system component is not explicit.", "Name the actor or component that performs the behavior.", "clarity", 10)
        ambiguities.append("Responsible actor is not explicit.")

    action_hits = sorted(token_set & ACTION_VERBS)
    if not action_hits:
        issue("high", "MISSING_ACTION", "No observable action verb was detected.", "State what the system or actor shall do in observable terms.", "completeness", 18)
        ambiguities.append("Expected behavior is not explicit.")

    for phrase, advice in VAGUE.items():
        if re.search(r"\b" + re.escape(phrase) + r"\b", lower):
            issue("medium", "VAGUE_TERM", f"The term '{phrase}' is subjective or underspecified.", advice, "clarity", 7)
            ambiguities.append(f"Vague term: {phrase}.")

    if re.search(r"\b(it|they|them|this|that|these|those)\b", lower):
        issue("low", "UNCLEAR_REFERENCE", "A pronoun may refer to more than one entity.", "Replace pronouns with the exact system, user, record, service, or data item.", "clarity", 3)

    if re.search(r"\b(and/or|etc\.?|various|several|some|many)\b", lower):
        issue("medium", "OPEN_ENDED_SCOPE", "Open-ended wording can leave the scope open to interpretation.", "Enumerate the included cases or define an explicit scope boundary.", "completeness", 6)

    conjunctions = len(re.findall(r"\b(and|or)\b", lower))
    if len(sentences) > 2 or conjunctions >= 4 or len(action_hits) >= 4:
        issue("medium", "POSSIBLE_NON_ATOMIC", "The statement may combine multiple independent behaviors or conditions.", "Split it into one independently verifiable obligation per requirement ID.", "atomicity", 12)

    if len(text) > 600:
        issue("low", "LONG_REQUIREMENT", "The requirement is unusually long and may contain multiple obligations.", "Split the statement while preserving dependencies between the resulting requirements.", "atomicity", 5)

    has_measure = bool(NUMBER_UNIT_RE.search(text))
    has_condition = any(re.search(r"\b" + re.escape(term) + r"\b", lower) for term in BOUNDARIES)
    has_outcome = bool(re.search(r"\b(display|return|show|reject|accept|save|store|send|notify|prevent|allow|record|create|update|delete)\b", lower))
    if len(tokens) >= 9 and not has_condition:
        issue("low", "NO_TRIGGER_OR_PRECONDITION", "No trigger or precondition is apparent.", "State when the requirement applies, including relevant preconditions and exception paths.", "completeness", 4)
    if len(tokens) >= 9 and not has_outcome:
        issue("medium", "NO_OBSERVABLE_OUTCOME", "The expected observable result is not clear.", "Describe the output, state change, response, or externally observable result.", "testability", 10)

    primary, categories = classify(text)
    quality = [c for c in categories if c in CATEGORY_RULES]
    for category in quality:
        if category == "Performance":
            if not has_measure:
                issue("high", "PERFORMANCE_WITHOUT_TARGET", "Performance requirement has no measurable target or unit.", "Specify a maximum response time, throughput, workload, and measurement conditions.", "testability", 18)
            if not re.search(r"\b(response|latency|throughput|load|process|complete|requests?)\b", lower):
                issue("low", "PERFORMANCE_METRIC_UNCLEAR", "The performance metric is not clearly identified.", "Name the measured operation and metric, such as p95 response time or requests per second.", "testability", 5)
        elif category == "Security":
            controls = ["encrypt", "authentication", "authorization", "role", "access control", "multi-factor", "mfa", "audit", "session"]
            if not any(c in lower for c in controls):
                issue("high", "SECURITY_CONTROL_UNSPECIFIED", "Security is mentioned without a concrete control.", "Specify the control, protected asset, actor permissions, and expected denial behavior.", "completeness", 15)
            if not any(c in lower for c in ["unauthorized", "unauthorised", "role", "permission", "access", "encrypt", "authentication", "authorization"]):
                issue("medium", "SECURITY_NEGATIVE_CASE_MISSING", "Unauthorized access or misuse behavior is not addressed.", "Define how unauthorized requests are rejected and logged.", "testability", 8)
        elif category == "Availability":
            if not re.search(r"\b\d+(?:\.\d+)?\s*%\b|\b(uptime|downtime|minutes? per month|hours? per month)\b", lower):
                issue("high", "AVAILABILITY_TARGET_MISSING", "Availability is not expressed as a measurable service target.", "Specify uptime percentage over a defined measurement period and planned-maintenance treatment.", "testability", 15)
        elif category == "Reliability":
            if not any(c in lower for c in ["recovery", "failure rate", "retry", "fault", "backup", "restore", "data loss", "mtbf", "mttr", "rpo", "rto"]):
                issue("medium", "RELIABILITY_BEHAVIOR_MISSING", "Reliability is mentioned without a failure or recovery behavior.", "Define failure handling, retry limits, recovery time, and acceptable data loss.", "completeness", 10)
        elif category == "Usability":
            if not any(c in lower for c in ["task", "complete", "click", "steps", "screen reader", "keyboard", "wcag", "accessible", "learn"]):
                issue("medium", "USABILITY_CRITERIA_MISSING", "Usability has no concrete user task or accessibility criterion.", "Define target users, task success rate, maximum steps/time, and accessibility standard where applicable.", "testability", 10)
        elif category == "Compatibility":
            if not any(c in lower for c in ["chrome", "firefox", "safari", "edge", "windows", "linux", "macos", "android", "ios", "version", "browser", "device"]):
                issue("medium", "COMPATIBILITY_MATRIX_MISSING", "Compatibility is not tied to named platforms or versions.", "List supported devices, operating systems, browsers, and minimum versions.", "completeness", 10)
        elif category == "Privacy":
            if not any(c in lower for c in ["consent", "retention", "delete", "erase", "anonym", "encrypt", "access", "purpose"]):
                issue("high", "PRIVACY_CONTROL_MISSING", "Personal-data handling is mentioned without a clear privacy control.", "Specify purpose, consent/legal basis, access restrictions, retention period, and deletion behavior.", "completeness", 15)
        elif category == "Interface / Integration":
            if not any(c in lower for c in ["request", "response", "json", "xml", "http", "endpoint", "webhook", "schema", "status code", "timeout"]):
                issue("medium", "INTERFACE_CONTRACT_MISSING", "The integration requirement lacks a defined interface contract.", "Specify protocol, endpoint/event, payload schema, success response, errors, timeout, and retry behavior.", "testability", 10)
        elif category == "Data":
            if not any(c in lower for c in ["valid", "required", "format", "unique", "range", "backup", "restore", "retention", "schema"]):
                issue("medium", "DATA_RULE_MISSING", "Data behavior lacks explicit validation, integrity, or lifecycle rules.", "Define field constraints, formats, uniqueness, retention, backup, and invalid-data behavior.", "completeness", 9)
        elif category == "Regulatory / Compliance":
            if not re.search(r"\b(iso\s*\d+|pci\s*dss|hipaa|gdpr|wcag|section\s*508|rbi|fssai)\b", lower):
                issue("medium", "STANDARD_NOT_NAMED", "Compliance is mentioned without identifying the applicable standard or regulation.", "Name the applicable regulation/standard, version, scope, and evidence required for compliance.", "completeness", 10)
        elif category == "Maintainability":
            if not any(c in lower for c in ["logging", "monitoring", "modular", "document", "deployment", "diagnostic", "maintain"]):
                issue("medium", "MAINTAINABILITY_MEASURE_MISSING", "Maintainability has no concrete engineering or operational criterion.", "Specify measurable maintainability expectations such as diagnostic coverage, deployment time, or module boundaries.", "testability", 8)

    if "Technical Constraint" in categories and not any(term in lower for term in ["version", "must use", "shall use", "compatible", "hosted", "deployed"]):
        issue("low", "CONSTRAINT_SCOPE_UNCLEAR", "A constraint is present but its applicability or boundary may be unclear.", "State whether the constraint is mandatory, its scope, and any approved exceptions.", "completeness", 4)

    if "User Story" in categories and not re.search(r"\b(so that|in order to)\b", lower):
        issue("low", "USER_STORY_VALUE_MISSING", "The user story may not explain the user value or business outcome.", "Add the 'so that' benefit or expected business outcome.", "completeness", 5)

    if not re.search(r"\b(error|invalid|fail|failure|reject|unavailable|timeout|exception|unauthorized)\b", lower) and len(tokens) > 12:
        issue("low", "EXCEPTION_PATH_NOT_STATED", "No error or exception path is described.", "Consider defining invalid input, unavailable dependency, timeout, and recovery behavior where relevant.", "completeness", 4)

    if re.search(r"\b(always|never|all|any|every|none)\b", lower) and not re.search(r"\b(all|any|every|none)\s+(users?|records?|requests?|cases?|transactions?)\b", lower):
        issue("low", "ABSOLUTE_SCOPE", "Absolute wording may create an unexpectedly broad obligation.", "Define the exact population, scope, and exceptions covered by the absolute term.", "clarity", 3)

    # Derive quality indicators from independent dimensions; do not present this as model confidence.
    dimensions = score_parts
    overall = round(sum(dimensions.values()) / len(dimensions))
    ambiguities = unique(ambiguities + [x["message"] for x in issues if x["code"] in {"VAGUE_TERM","UNCLEAR_REFERENCE","MISSING_ACTOR","MISSING_ACTION"}])
    missing = unique(missing + recommendations)
    if dimensions["clarity"] >= 85: clarity = "Good"
    elif dimensions["clarity"] >= 65: clarity = "Moderate"
    else: clarity = "Poor"
    if dimensions["completeness"] >= 85: completeness = "Complete"
    elif dimensions["completeness"] >= 60: completeness = "Partial"
    else: completeness = "Incomplete"
    if dimensions["testability"] >= 85: testability = "Testable"
    elif dimensions["testability"] >= 60: testability = "Partially Testable"
    else: testability = "Not Testable"

    if not issues:
        add_issue(issues, "info", "NO_RULE_TRIGGERED", "No major issue was detected by the configured checks.", "Review this requirement with stakeholders and validate it against related requirements.")

    # Suggestions never invent domain-specific thresholds or business rules.
    rewrite = text
    if any(x["severity"] in {"high", "medium"} for x in issues):
        rewrite = text + " [Refine using the recommendations below; confirm all thresholds and business rules with stakeholders.]"

    explanation = (
        f"Detected category: {', '.join(categories)}. "
        f"Analyzed {len(tokens)} words in {len(sentences)} sentence(s); "
        f"detected action verbs: {', '.join(action_hits[:8]) if action_hits else 'none'}. "
        f"Numeric/unit threshold detected: {'yes' if has_measure else 'no'}. "
        "Scores are deterministic text-quality indicators from configured rules, not model confidence or proof of correctness."
    )
    if source or section_number:
        explanation += f" Document context: source={source or 'not supplied'}, section={section_number or 'not supplied'}."

    return {
        "quality_score": overall,
        "classification": primary,
        "categories": categories,
        "clarity": clarity,
        "completeness": completeness,
        "testability": testability,
        "dimension_scores": dimensions,
        "ambiguities": ambiguities,
        "missing_information": missing,
        "issues": [x["message"] for x in issues],
        "detailed_findings": issues,
        "issue_count": len([x for x in issues if x["severity"] != "info"]),
        "suggested_rewrite": rewrite,
        "explanation": explanation,
    }

def build_expert_review(requirement: str, analysis: dict) -> dict:
    """Create a readable, evidence-linked review from detected rule results."""
    findings = analysis.get("detailed_findings", [])
    high = [item for item in findings if item.get("severity") == "high"]
    medium = [item for item in findings if item.get("severity") == "medium"]
    low = [item for item in findings if item.get("severity") == "low"]
    categories = analysis.get("categories", [])
    dimensions = analysis.get("dimension_scores", {})
    primary = analysis.get("classification", "Unclassified")

    if high:
        verdict = "Needs substantial revision"
        risk = "High"
        summary = f"This requirement has {len(high)} high-severity concern(s). Resolve these before treating it as implementation-ready."
    elif medium:
        verdict = "Needs clarification"
        risk = "Moderate"
        summary = f"The requirement is understandable at a high level, but {len(medium)} medium-severity concern(s) could lead to inconsistent implementation or testing."
    elif low:
        verdict = "Review recommended"
        risk = "Low"
        summary = "No high-severity issue was detected, although some refinements would improve precision and verification."
    else:
        verdict = "No major textual issue detected"
        risk = "Low"
        summary = "The configured checks found no major textual defect. Stakeholder validation and cross-document review are still required."

    strengths = []
    if re.search(r"\\b(shall|must|will|should|may)\\b", requirement, re.I):
        strengths.append("A requirement modality is stated.")
    if any(re.search(p, requirement.lower()) for p in ACTOR_PATTERNS):
        strengths.append("A responsible actor or component is identified.")
    if set(words(requirement)) & ACTION_VERBS:
        strengths.append("An observable action verb is present.")
    if NUMBER_UNIT_RE.search(requirement):
        strengths.append("At least one numeric value with a recognized unit is present.")
    if not strengths:
        strengths.append("The statement provides source text that can be refined into a verifiable requirement.")

    questions = []
    codes = {item.get("code") for item in findings}
    if "MISSING_ACTOR" in codes:
        questions.append("Which actor or system component owns this behavior?")
    if "MISSING_MODAL" in codes:
        questions.append("Is this behavior mandatory, optional, recommended, or prohibited?")
    if any(code in codes for code in ("VAGUE_TERM", "PERFORMANCE_WITHOUT_TARGET", "AVAILABILITY_TARGET_MISSING")):
        questions.append("What measurable threshold, unit, measurement period, and operating conditions should apply?")
    if "NO_TRIGGER_OR_PRECONDITION" in codes:
        questions.append("What event or precondition causes this requirement to apply?")
    if any(code in codes for code in ("NO_OBSERVABLE_OUTCOME", "MISSING_ACTION")):
        questions.append("What observable result should a tester verify?")
    if "EXCEPTION_PATH_NOT_STATED" in codes:
        questions.append("What should happen for invalid input, unavailable dependencies, timeouts, or other failure cases?")
    if "SECURITY_NEGATIVE_CASE_MISSING" in codes:
        questions.append("How should unauthorized or invalid access attempts be denied and recorded?")
    if "INTERFACE_CONTRACT_MISSING" in codes:
        questions.append("What are the interface protocol, request/response schema, error contract, timeout, and retry rules?")
    if "COMPATIBILITY_MATRIX_MISSING" in codes:
        questions.append("Which exact platforms, browser versions, devices, and minimum versions are supported?")
    if "PRIVACY_CONTROL_MISSING" in codes:
        questions.append("What is the data purpose, lawful basis or consent, retention period, and deletion process?")
    if not questions:
        questions.append("Have the requirement owner and tester agreed on the expected behavior and acceptance evidence?")

    subject = "the specified actor or system component"
    actor_match = re.search(r"\\b(the system|the application|the platform|the service|the user|the administrator|admin|customer|manager|operator)\\b", requirement, re.I)
    if actor_match:
        subject = actor_match.group(0)
    action = next((verb for verb in words(requirement) if verb in ACTION_VERBS), "perform the specified behavior")
    test_scenarios = [
        {
            "id": "TC-01",
            "type": "Positive",
            "purpose": "Verify the stated behavior under its intended valid conditions.",
            "steps": ["Establish the preconditions agreed by the requirement owner.", f"Ask {subject} to {action} as described in the requirement.", "Observe the system response and compare it with the agreed expected result."],
            "expected_result": "The specified behavior occurs and the observable outcome matches the approved acceptance criteria.",
            "note": "Expected details must be confirmed; the analyzer does not invent business rules."
        },
        {
            "id": "TC-02",
            "type": "Negative / boundary",
            "purpose": "Check handling of invalid, missing, unauthorized, or boundary inputs where applicable.",
            "steps": ["Prepare an invalid or boundary condition relevant to this requirement.", "Execute the same behavior.", "Observe the response, state changes, and any error handling."],
            "expected_result": "The system follows the error and boundary behavior defined by the approved specification.",
            "note": "Select applicable cases with the product owner; not every requirement needs every negative case."
        },
        {
            "id": "TC-03",
            "type": "Regression",
            "purpose": "Check that satisfying this requirement does not break related behavior.",
            "steps": ["Run the requirement's approved positive test.", "Run tests for related requirements and integrations.", "Compare outputs and persisted state with their expected results."],
            "expected_result": "This requirement and related approved behaviors continue to pass."
        }
    ]

    prioritized = [
        {"priority": "P1", "action": item["recommendation"], "reason": item["message"]}
        for item in high
    ] + [
        {"priority": "P2", "action": item["recommendation"], "reason": item["message"]}
        for item in medium
    ] + [
        {"priority": "P3", "action": item["recommendation"], "reason": item["message"]}
        for item in low
    ]

    return {
        "review_verdict": verdict,
        "risk_level": risk,
        "executive_summary": summary,
        "requirement_type_interpretation": {
            "primary_type": primary,
            "detected_categories": categories,
            "interpretation": f"The wording most strongly matches {primary.lower()} requirement characteristics. Category matching is rule-based and should be confirmed by a reviewer."
        },
        "strengths": strengths,
        "dimension_assessment": [
            {"dimension": name, "score": value, "interpretation": "Strong" if value >= 85 else "Needs attention" if value >= 65 else "Weak"}
            for name, value in dimensions.items()
        ],
        "detailed_reasoning": [
            {"finding": item["message"], "why_it_matters": f"This may affect {item['code'].lower().replace('_', ' ')} and create ambiguity for implementation or verification.", "recommended_action": item["recommendation"], "severity": item["severity"]}
            for item in findings
        ],
        "questions_for_requirement_owner": unique(questions),
        "suggested_acceptance_criteria": [
            {"id": "AC-01", "given": "The agreed preconditions and valid input are present", "when": f"{subject} performs the stated behavior", "then": "The observable outcome matches the acceptance rule approved by the requirement owner."},
            {"id": "AC-02", "given": "An invalid or out-of-scope condition occurs, where applicable", "when": "The behavior is attempted", "then": "The system follows the explicitly approved error-handling rule without an unintended state change."}
        ],
        "illustrative_test_scenarios": test_scenarios,
        "prioritized_improvement_plan": prioritized,
        "review_limitations": [
            "This review is generated by deterministic linguistic patterns and expert-authored rules, not by a trained generative language model.",
            "A detected issue is a review signal, not proof that the requirement is defective; a missing signal is not proof of correctness.",
            "Numeric thresholds, business policies, legal obligations, and domain assumptions must be confirmed with stakeholders."
        ]
    }


def cross_requirement_checks(requirements: list[str], analyses: list[dict]) -> list[dict]:
    findings = []
    normalized = [re.sub(r"[^a-z0-9 ]", " ", r.lower()) for r in requirements]
    for i in range(len(requirements)):
        for j in range(i + 1, len(requirements)):
            a, b = normalized[i], normalized[j]
            ta = {w for w in words(a) if w not in STOP and len(w) > 2}
            tb = {w for w in words(b) if w not in STOP and len(w) > 2}
            if not ta or not tb:
                continue
            overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
            if overlap >= 0.82:
                findings.append({
                    "type": "possible_duplicate",
                    "severity": "medium",
                    "requirements": [i + 1, j + 1],
                    "message": "These requirements use highly similar key terms and may duplicate the same obligation.",
                    "recommendation": "Compare their actors, triggers, outcomes, and acceptance criteria; merge or distinguish them if appropriate.",
                })
            # Flag opposing explicit modal/polarity for strongly overlapping topics.
            opposing = (("shall not" in a or "must not" in a) and ("shall " in b or "must " in b) and not ("shall not" in b or "must not" in b)) or (("shall not" in b or "must not" in b) and ("shall " in a or "must " in a) and not ("shall not" in a or "must not" in a))
            if overlap >= 0.55 and opposing:
                findings.append({
                    "type": "possible_conflict",
                    "severity": "high",
                    "requirements": [i + 1, j + 1],
                    "message": "These requirements may impose opposing obligations on a similar subject.",
                    "recommendation": "Review scope, actors, conditions, priorities, and exceptions with the requirement owner before treating this as a confirmed conflict.",
                })
    return findings

@app.get("/")
def home():
    return {"message": "SRS Requirement Analyzer is running", "version": VERSION, "provider": "built-in NLP analysis engine", "mode": "model-free"}

@app.get("/health")
def health():
    return {"status": "ok", "service": "SRS AI Analyzer", "version": VERSION, "provider": "built-in NLP analysis engine", "mode": "model-free", "internal_auth_configured": bool(SRS_API_KEY)}

@app.post("/analyze")
async def analyze(request: AnalyzeRequest, _: None = Depends(verify_api_key)):
    requirement = request.requirement or request.text
    if not requirement and request.requirements is not None:
        requirement = json.dumps(request.requirements) if isinstance(request.requirements, (dict, list)) else str(request.requirements)
    if not isinstance(requirement, str) or not requirement.strip():
        raise HTTPException(status_code=400, detail="Please provide requirement text")
    requirement = requirement.strip()
    result = analyze_text(requirement, request.source, request.section_number)
    result["expert_review"] = build_expert_review(requirement, result)
    return {"status": "success", "provider": "built-in NLP analysis engine", "model": None, "requirement": requirement, "analysis": result}

@app.post("/analyze-batch")
async def analyze_batch(request: BatchAnalyzeRequest, _: None = Depends(verify_api_key)):
    analyses = []
    for index, requirement in enumerate(request.requirements):
        result = analyze_text(requirement)
        result["expert_review"] = build_expert_review(requirement, result)
        analyses.append({"requirement_number": index + 1, "requirement": requirement, **result})
    category_counts = Counter(category for item in analyses for category in item["categories"])
    cross_findings = cross_requirement_checks(request.requirements, analyses)
    average_score = round(sum(item["quality_score"] for item in analyses) / len(analyses))
    return {
        "status": "success",
        "provider": "built-in NLP analysis engine",
        "model": None,
        "total_requirements": len(request.requirements),
        "average_quality_score": average_score,
        "category_summary": dict(category_counts),
        "cross_requirement_findings": cross_findings,
        "analyses": analyses,
    }
