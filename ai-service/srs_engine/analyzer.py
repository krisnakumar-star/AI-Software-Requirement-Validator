"""Per-requirement analysis: classification, defect detection, explainable
scoring, and review generation (improved draft, questions, acceptance
criteria, test scenarios, priority).

Scores are deterministic: each dimension starts at 100 and every finding
subtracts a documented number of points. Nothing here is a trained model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .lexicon import (
    ABSOLUTE_TERMS, ACTION_VERBS, AMBIGUOUS_PHRASES, AUTHORIZATION_TERMS, CATEGORY_RULES, DATA_ENTRY,
    DEPENDENCY_TERMS, DESIGN_TERMS, ERROR_TERMS, EVENT_ACTIONS, INPUT_TERMS, NFR_CATEGORIES,
    NFR_METRIC_TERMS, OPEN_ENDED, OUTCOME_TERMS, OUTPUT_TERMS, QUERY_ACTIONS, RECOVERY_TERMS,
    RISKY_OPERATIONS, SECURITY_CONTROLS, SENSITIVE_ACTIONS, SENSITIVE_DATA_TERMS, STATE_CHANGING,
    UNREALISTIC_PATTERNS, VAGUE_TERMS, VALIDATION_TERMS, IRREGULAR_PARTICIPLES,
)
from .parse import ParsedRequirement, parse
from .text import any_term, contains_phrase, find_phrase, sentences, terminology_variants, truncate, unique

DIMENSIONS = ["clarity", "completeness", "testability", "atomicity", "consistency", "verifiability",
              "feasibility", "traceability"]
DIMENSION_WEIGHTS = {"clarity": 0.17, "completeness": 0.17, "testability": 0.17, "atomicity": 0.08,
                     "consistency": 0.10, "verifiability": 0.11, "feasibility": 0.08, "traceability": 0.12}
SEVERITY_POINTS = {"critical": 35, "high": 22, "medium": 14, "low": 6, "info": 0}
SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
SCORE_CAPS = {"critical": 45, "high": 74, "multi_medium": 79}
RISK_CATEGORIES = {"Security", "Privacy", "Regulatory / Compliance"}
GENERIC_OBJECTS = {"data", "information", "details", "report", "reports", "results", "result", "content",
                   "items", "things", "stuff", "records", "functionality", "features", "it", "them", "list"}
DATA_ENTITY_TERMS = ["email", "phone", "date", "address", "name", "amount", "price", "file", "image",
                     "document", "record", "field", "password", "quantity", "description", "comment",
                     "identifier", "age", "salary", "photo", "attachment"]
BUSINESS_TERMS = ["discount", "fee", "penalty", "tax", "eligible", "eligibility", "interest", "commission",
                  "threshold", "quota", "fine", "late fee", "credit limit", "bonus", "surcharge"]
BOUNDARY_WORDS = ["limit", "maximum", "minimum", "up to", "at least", "no more than", "threshold", "range",
                  "capacity", "quota", "exceed", "max", "min"]
NUMERIC_FIELD_TERMS = ["amount", "quantity", "age", "price", "file size", "length", "number of", "count",
                       "weight", "duration", "balance", "score", "rating"]


@dataclass
class Finding:
    code: str
    title: str
    severity: str
    dimension: str
    message: str
    evidence: str
    why_it_matters: str
    recommendation: str
    question: str | None = None
    secondary_dimension: str | None = None
    points: int = 0

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "title": self.title,
            "severity": self.severity,
            "dimension": self.dimension,
            "secondary_dimension": self.secondary_dimension,
            "message": self.message,
            "evidence": self.evidence,
            "why_it_matters": self.why_it_matters,
            "recommendation": self.recommendation,
            "question": self.question,
            "points_deducted": self.points,
        }


@dataclass
class Context:
    parsed: ParsedRequirement
    text: str
    lower: str
    categories: list[str]
    primary: str
    functional: bool
    findings: list[Finding] = field(default_factory=list)

    def add(self, code, title, severity, dimension, message, evidence, why, recommendation,
            question=None, secondary=None):
        if any(f.code == code and f.evidence == evidence for f in self.findings):
            return
        self.findings.append(Finding(code, title, severity, dimension, message, evidence or "—", why,
                                     recommendation, question, secondary))

    def has(self, code: str) -> bool:
        return any(f.code == code for f in self.findings)


# ==================================================
# CLASSIFICATION
# ==================================================

def classify(parsed: ParsedRequirement, text: str | None = None) -> dict:
    lower = (text or parsed.text).lower()
    scores: dict[str, float] = {}
    evidence: dict[str, list[str]] = {}
    for category, (terms, weight) in CATEGORY_RULES.items():
        hits = []
        for term in terms:
            if "\\d" in term:
                match = re.search(term, lower)
                if match:
                    hits.append(match.group(0))
            elif any_term(lower, [term]):
                hits.append(term.strip())
        if hits:
            scores[category] = weight * len(hits)
            evidence[category] = unique(hits)[:4]
    for category, pattern in NFR_METRIC_TERMS.items():
        if category in scores and re.search(pattern, lower):
            scores[category] += 0.5

    action = parsed.action
    behavioural = bool(action and action != "be" and (action in ACTION_VERBS or parsed.actor_kind in {"system", "human"}))
    nfr_verbs = {"encrypt", "hash", "respond", "load", "support", "comply", "scale", "recover", "mask", "log", "audit"}
    nfr_hits = {c: s for c, s in scores.items() if c in NFR_CATEGORIES}

    if parsed.user_story:
        primary = "User Story"
    elif scores.get("Technical Constraint", 0) >= 1:
        primary = "Constraint"
    elif scores.get("Business Rule", 0) >= 1.7 or (scores.get("Business Rule") and parsed.conditions and re.search(r"\b(then|otherwise|only if)\b", lower)):
        primary = "Business Rule"
    elif nfr_hits and (not behavioural or action == "be" or action in nfr_verbs or parsed.passive):
        primary = "Non-Functional"
    elif behavioural:
        primary = "Functional"
    elif nfr_hits:
        primary = "Non-Functional"
    else:
        primary = "Unclassified"

    ordered = sorted(scores, key=lambda c: -scores[c])
    categories = ordered[:]
    if primary == "Functional":
        categories = ["Functional"] + [c for c in ordered if c != "Functional"]
    elif primary in {"User Story", "Business Rule"} and primary not in categories:
        categories = [primary] + categories
    elif primary == "Unclassified" and not categories:
        categories = ["Unclassified"]
    if primary == "Constraint" and "Technical Constraint" not in categories:
        categories.insert(0, "Technical Constraint")
    return {"primary": primary, "categories": unique(categories), "evidence": evidence}


# ==================================================
# DEFECT DETECTION
# ==================================================

def _vague_checks(ctx: Context) -> None:
    p = ctx.parsed
    measure_families = {m.family for m in p.measures}
    speed = {"fast", "quick", "quickly", "rapid", "slow", "responsive", "efficient", "efficiently",
             "as fast as possible", "high performance", "timely", "soon"}
    sized = {"large", "small", "high", "low", "minimal", "significant", "scalable"}
    for term, (why, specify) in VAGUE_TERMS.items():
        found = find_phrase(ctx.text, term)
        if not found:
            continue
        lowered = term.lower()
        if lowered in {"high", "low"}:
            if not re.search(r"\b" + lowered + r"[- ](speed|performance|latency|throughput|volume|load|quality|accuracy|resolution|traffic)\b", ctx.lower):
                continue
        if lowered in {"some", "many", "few", "several"} and re.search(r"\b" + lowered + r"\s+(of\s+)?(the\s+)?(following|listed)\b", ctx.lower):
            continue
        if lowered in {"normal"} and "normal user" in ctx.lower:
            continue
        if lowered in {"secure", "securely"} and any_term(ctx.lower, SECURITY_CONTROLS):
            severity = "low"
        elif lowered in speed and "time" in measure_families or lowered in sized and measure_families & {"size", "count", "percent", "rate"}:
            severity = "low"
        elif ctx.primary == "Non-Functional" and not p.measures:
            severity = "high"
        else:
            severity = "medium"
        ctx.add(
            "VAGUE_TERM", "Vague or subjective term", severity, "clarity",
            f"'{found}' is vague: {why}.", found,
            "Different readers, developers, and testers will interpret it differently, so it cannot be verified consistently.",
            f"Replace '{found}' with {specify}.",
            f"What exactly does '{found}' mean here — what measurable value or rule defines it?",
            secondary="testability",
        )


def _ambiguity_checks(ctx: Context) -> None:
    p = ctx.parsed
    for phrase, why in AMBIGUOUS_PHRASES.items():
        if phrase in {"tbd", "tbc", "to be decided", "to be determined"}:
            continue
        found = find_phrase(ctx.text, phrase)
        if not found:
            continue
        verb_like = phrase in {"support", "handle", "manage", "process"}
        if verb_like and not (p.action == phrase or re.search(r"\b(shall|must|should|will|can|to)\s+(also\s+)?" + phrase + r"\b", ctx.lower)):
            continue
        if phrase == "process" and p.object and len(p.object.split()) >= 2 and any_term(ctx.lower, OUTCOME_TERMS):
            continue
        ctx.add(
            "AMBIGUOUS_PHRASE", "Ambiguous wording", "medium", "clarity",
            f"'{found}' is ambiguous. {why}", found,
            "Ambiguous wording allows several valid implementations; disagreements surface late, during testing or acceptance.",
            f"Replace '{found}' with the specific behaviour(s) required.",
            f"What specific behaviour is meant by '{found}'?",
        )
    for phrase in ["the above", "as mentioned", "as described", "same as", "the following"]:
        found = find_phrase(ctx.text, phrase)
        if not found:
            continue
        if phrase == "the following" and ":" in ctx.text:
            continue
        if phrase in {"as described", "same as"} and p.references:
            continue
        ctx.add(
            "UNCLEAR_REFERENCE", "Unclear reference", "medium", "clarity",
            f"'{found}' points to content outside this requirement without identifying it.", found,
            "If the referenced text moves or changes, this requirement silently changes meaning and loses traceability.",
            "Reference the exact requirement ID or section, or restate the content.",
            f"Which requirement or section does '{found}' refer to?",
            secondary="traceability",
        )
    for word in ["it", "they", "them", "this", "these", "those", "its", "their"]:
        pattern = r"(?<![a-z])" + word + r"(?![a-z])"
        for match in re.finditer(pattern, ctx.lower):
            before = ctx.lower[max(0, match.start() - 12):match.start()]
            after = ctx.lower[match.end():match.end() + 12]
            if word == "this" and re.match(r"\s+(requirement|document|section|feature)", after):
                continue
            if word in {"their", "its"} and p.actor_kind in {"human", "system"}:
                continue  # "users ... their password" has a clear antecedent.
            if word in {"they", "them"} and p.actor and re.search(r"s\b", p.actor.lower()) and p.actor_kind == "human":
                continue
            if "so that" in before or "such that" in before:
                continue
            if p.actor_kind == "pronoun" and match.start() < 15:
                continue  # Reported as MISSING_ACTOR.
            severity = "low"
            evidence = ctx.text[match.start():match.end()]
            ctx.add(
                "UNCLEAR_REFERENCE", "Unclear pronoun reference", severity, "clarity",
                f"The pronoun '{evidence}' may refer to more than one entity.", evidence,
                "Pronouns force the reader to guess the subject; in a standalone requirement the antecedent may not exist.",
                f"Replace '{evidence}' with the exact system, actor, or data item.",
                f"What does '{evidence}' refer to?",
            )
            break
    for term in OPEN_ENDED:
        found = find_phrase(ctx.text, term) if term[-1].isalpha() else (term if term in ctx.lower else None)
        if not found:
            continue
        severity = "low" if term == "such as" else "medium"
        ctx.add(
            "OPEN_ENDED", "Open-ended scope", severity, "completeness",
            f"'{found}' leaves the scope open-ended.", found,
            "Open lists make it impossible to know when the requirement is complete, which invites scope creep and disputes.",
            "Enumerate every in-scope item, or state an explicit scope boundary.",
            "What is the complete list of items in scope?",
            secondary="testability",
        )


def _structure_checks(ctx: Context) -> None:
    p = ctx.parsed
    if p.word_count < 5:
        ctx.add("INCOMPLETE", "Requirement too short", "high", "completeness",
                "The statement is too short to express a verifiable requirement.", truncate(ctx.text, 60),
                "Without actor, behaviour, and expected result, the requirement cannot be designed or tested.",
                "Specify who does what, under which condition, with what observable result.",
                "What behaviour, actor, and expected result does this item describe?", secondary="testability")
    placeholder = re.search(r"\b(tbd|tbc|to be (decided|determined|confirmed)|\?\?+|xxx)\b", ctx.lower)
    if placeholder:
        ctx.add("INCOMPLETE", "Unresolved placeholder", "high", "completeness",
                "The requirement contains an unresolved placeholder.", ctx.text[placeholder.start():placeholder.end()],
                "Implementation cannot start reliably until the placeholder is resolved.",
                "Resolve the placeholder with the requirement owner, or move the item to an open-issues list.",
                "Who owns this decision, and when will it be resolved?")
    dangling = re.search(r"\b(to|and|or|the|with|of|for|by|such as)\s*[:,]?\s*$", ctx.lower.rstrip("."))
    if dangling and p.word_count >= 3:
        ctx.add("INCOMPLETE", "Incomplete sentence", "high", "completeness",
                "The sentence appears to be cut off.", truncate(ctx.text[-30:], 30),
                "Truncated requirements often result from extraction errors and silently lose information.",
                "Check the source document and complete the statement.",
                "What is the complete wording of this requirement?")

    if not p.modal and not p.user_story:
        ctx.add("MISSING_MODAL", "Obligation level not stated", "medium", "clarity",
                "No modal verb (shall/must/should/may) states whether this is mandatory, recommended, or optional.",
                truncate(ctx.text, 50),
                "Without an obligation level, the team cannot tell whether failing to implement it is a defect.",
                "Use 'shall' for mandatory behaviour, 'should' for recommended, 'may' for optional, 'shall not' for prohibited.",
                "Is this behaviour mandatory, recommended, or optional?")
    elif p.modal == "will":
        ctx.add("WEAK_MODAL", "Ambiguous modal verb 'will'", "low", "clarity",
                "'will' can be read as a statement of fact rather than an obligation.", "will",
                "Contractually and for testing, 'will' is weaker and less precise than 'shall'.",
                "Use 'shall' if this is a mandatory requirement.", "Is this a mandatory obligation?")
    elif p.modal in {"should", "may", "can", "could", "might"}:
        mandatory_context = bool(set(ctx.categories) & RISK_CATEGORIES)
        ctx.add("WEAK_MODAL", "Non-binding modal verb", "medium" if mandatory_context else "low", "clarity",
                f"'{p.modal}' makes the requirement {('recommended' if p.modal == 'should' else 'optional')}"
                + (" even though it concerns security, privacy, or compliance." if mandatory_context else "."),
                p.modal,
                "Teams often skip non-binding requirements under schedule pressure; testers cannot fail a build against them.",
                "Confirm the intended obligation and use 'shall' if the behaviour is mandatory.",
                f"Is this behaviour truly {('recommended' if p.modal == 'should' else 'optional')}, or mandatory?")
    if len(set(m for m in p.modals_found if m in {"shall", "must", "should", "may", "will", "can"})) >= 2:
        ctx.add("MIXED_MODALS", "Mixed obligation levels", "low", "consistency",
                f"The requirement mixes obligation levels ({', '.join(unique(p.modals_found))}).", ", ".join(unique(p.modals_found)),
                "Mixed modals inside one requirement make it unclear which parts are mandatory.",
                "Split the requirement so each statement has a single obligation level.")

    if p.actor_kind == "missing" and not p.user_story:
        ctx.add("MISSING_ACTOR", "Responsible actor missing", "medium", "clarity",
                "No actor or system component is identified as responsible for the behaviour.", truncate(ctx.text, 50),
                "Without an owner, it is unclear which component implements the behaviour and which user can trigger it.",
                "Name the system component or user role that performs the behaviour.",
                "Which system component or user role performs this behaviour?", secondary="completeness")
    elif p.actor_kind == "pronoun":
        ctx.add("MISSING_ACTOR", "Actor is a pronoun", "high", "clarity",
                f"The actor is the pronoun '{p.actor}', which has no antecedent in a standalone requirement.", p.actor or "it",
                "Requirements are read and traced individually; a pronoun subject makes ownership ambiguous.",
                "Replace the pronoun with the exact system or component name.",
                f"Which system or component does '{p.actor}' refer to?", secondary="completeness")
    elif p.passive and not p.secondary_actor and ctx.primary == "Functional":
        ctx.add("PASSIVE_VOICE", "Passive voice hides the actor", "low", "clarity",
                f"'{p.actor} {p.modal} {p.action_phrase}' does not say which component or user performs the action.",
                f"{p.modal} {p.action_phrase}",
                "Passive requirements make it unclear which component is responsible and who triggers the action.",
                "Rewrite in active voice naming the responsible component, e.g. 'The system shall ...'.",
                "Which component or user performs this action?")

    if not p.action:
        ctx.add("MISSING_ACTION", "No observable action", "high", "completeness",
                "No main action or behaviour could be identified.", truncate(ctx.text, 50),
                "A requirement without a verb describes a topic, not a behaviour; it cannot be designed or tested.",
                "State what the system or actor shall do using an observable action verb.",
                "What exactly should the system or user do?", secondary="testability")
    elif p.action == "be" and ctx.primary in {"Functional", "Unclassified"}:
        ctx.add("MISSING_ACTION", "States a property, not a behaviour", "medium", "completeness",
                f"'{p.action_phrase}' describes a property but no observable behaviour.", p.action_phrase or "be",
                "Properties without observable behaviour or a metric cannot be verified.",
                "Describe the behaviour that demonstrates the property, or add a measurable criterion.",
                "What observable behaviour shows this property is satisfied?", secondary="testability")

    def is_alternate_flow(sentence: str) -> bool:
        s_l = sentence.lower()
        return bool(re.match(r"^(if|otherwise|in case|when|unless|on failure|should)\b", s_l)) and bool(any_term(s_l, ERROR_TERMS))

    main_sentences = [s for s in p.sentence_list if not is_alternate_flow(s)]
    sentence_modals = [s for s in main_sentences if re.search(r"\b(shall|must|should|will|may)\b", s, re.I)]
    clause_modals = sum(len(re.findall(r"\b(and|,)\s+(shall|must|should|will)\b", s.lower())) for s in main_sentences)
    if len(sentence_modals) >= 2 or clause_modals >= 1:
        ctx.add("NON_ATOMIC", "Multiple obligations in one requirement", "medium", "atomicity",
                f"The text contains {max(len(sentence_modals), clause_modals + 1)} separate obligations.",
                truncate(sentence_modals[1] if len(sentence_modals) >= 2 else ctx.text, 70),
                "Compound requirements cannot be traced, prioritised, or marked pass/fail independently.",
                "Split it into one requirement per obligation, each with its own ID.",
                "Should these obligations be tracked as separate requirements?", secondary="traceability")
    elif len(p.coordinated_actions) >= 2 or (p.coordinated_actions and p.word_count > 22):
        verbs = [p.action] + p.coordinated_actions
        ctx.add("NON_ATOMIC", "Several actions bundled together", "low" if len(verbs) <= 3 else "medium", "atomicity",
                f"Several actions are bundled together ({', '.join(verbs)}).", ", ".join(verbs),
                "Each action usually has its own rules, permissions and tests; bundling hides gaps for individual actions.",
                "Consider one requirement per action, or confirm the actions share identical rules and acceptance criteria.")
    if p.word_count > 60:
        ctx.add("LONG_REQUIREMENT", "Very long requirement", "low", "atomicity",
                f"The requirement is {p.word_count} words long.", truncate(ctx.text, 60),
                "Long requirements usually hide several obligations and are hard to review and test.",
                "Split the statement while preserving dependencies between the parts.")


def _behaviour_checks(ctx: Context) -> None:
    p = ctx.parsed
    action = p.action or ""
    lower = ctx.lower
    is_functional = ctx.functional
    action_word = (p.action_phrase or "").lower()

    object_l = (p.object or "").lower()

    def outside_action(terms):
        return [t for t in any_term(lower, terms)
                if t.lower() not in {action, action_word} and not action_word.startswith(t.lower())
                and not (t.lower().isalpha() and t.lower() in object_l)]

    has_auth = bool(any_term(lower, AUTHORIZATION_TERMS))
    has_error = bool(any_term(lower, ERROR_TERMS))
    has_recovery = bool(any_term(lower, RECOVERY_TERMS))
    has_validation = bool(any_term(lower, VALIDATION_TERMS)) or any(m.family in {"count", "size"} for m in p.measures)
    outcome_terms = outside_action(OUTCOME_TERMS)
    has_inputs = bool(outside_action(INPUT_TERMS)) or bool(re.search(r"\b(with|using|by entering|by providing|by)\b\s+\w+", lower))
    has_condition = bool(p.conditions) or bool(p.user_story)

    if is_functional and action:
        vague_actions = {"process", "handle", "manage", "support", "validate", "verify", "check", "calculate",
                         "compute", "evaluate", "analyze", "analyse", "track", "monitor"}
        if not p.object or (action in vague_actions and not outcome_terms):
            ctx.add("MISSING_OUTCOME", "Expected outcome not stated", "medium", "completeness",
                    f"The requirement says the system will '{action}'"
                    + (f" {p.object}" if p.object else "") + " but not what observable result is expected.",
                    p.action_phrase or action,
                    "Testers need an observable result (output, state change, message) to decide pass or fail.",
                    "Describe the expected output, state change, or response.",
                    f"What should be observable after the system performs '{action}'?", secondary="testability")
        if action in STATE_CHANGING and not outcome_terms and not p.user_story:
            ctx.add("MISSING_POSTCONDITION", "Resulting state not defined", "medium", "completeness",
                    f"After '{action}' succeeds, the resulting state (saved record, status, confirmation) is not described.",
                    p.action_phrase or action,
                    "Without a postcondition, it is unclear what persists and what the user sees, so success cannot be verified.",
                    "State the resulting system state and the feedback given to the user.",
                    f"What is the system state and user feedback after a successful '{action}'?", secondary="testability")
        if action in STATE_CHANGING | {"view", "access", "download", "export", "approve"} and not has_condition and not has_auth:
            sensitive = action in SENSITIVE_ACTIONS
            ctx.add("MISSING_PRECONDITION", "Preconditions not stated", "medium" if sensitive else "low", "completeness",
                    f"No precondition is given for '{action}' (e.g. required user state, existing data, or prior step).",
                    p.action_phrase or action,
                    "Preconditions define when the behaviour is allowed; missing ones lead to unhandled states.",
                    "State the conditions that must hold before the action can be performed.",
                    f"What must be true before '{action}' is allowed?")
        if action in DATA_ENTRY and not has_inputs and not p.measures:
            ctx.add("MISSING_INPUTS", "Inputs not specified", "medium", "completeness",
                    f"The data the actor must provide to '{action}' is not specified.", p.action_phrase or action,
                    "Developers and testers need the input fields and their rules to build forms, APIs and test data.",
                    "List the required and optional inputs and their formats.",
                    f"Which inputs are required to '{action}', and in what format?")
        elif action in DATA_ENTRY and has_inputs and not has_validation:
            ctx.add("MISSING_VALIDATION_RULES", "Validation rules missing", "medium", "completeness",
                    "Inputs are mentioned but no validation rules (format, length, mandatory fields, ranges) are defined.",
                    p.object or p.action_phrase or action,
                    "Without validation rules, invalid data can enter the system and negative tests cannot be designed.",
                    "Define format, length, range, uniqueness and mandatory-field rules for each input.",
                    "What validation rules apply to each input?", secondary="testability")
        if action in QUERY_ACTIONS and not outside_action(OUTPUT_TERMS):
            generic = not p.object or any(w in GENERIC_OBJECTS for w in (p.object or "").lower().split())
            if generic or action in {"generate", "export", "report", "calculate", "compute", "summarize", "summarise"}:
                ctx.add("MISSING_OUTPUTS", "Outputs not specified", "low" if (p.measures or p.conditions) else "medium", "completeness",
                        f"The content or format of the output of '{action}' is not specified.", p.object or action,
                        "Without defined outputs, the delivered result cannot be checked against expectations.",
                        "Specify the output fields, ordering, format and destination.",
                        f"What exactly should the output of '{action}' contain, and in which format?", secondary="testability")
        if action in EVENT_ACTIONS and not p.conditions and not p.schedule:
            ctx.add("UNCLEAR_TRIGGER", "Trigger or timing not defined", "medium", "completeness",
                    f"It is not stated when or how often the system should '{action}'.", p.action_phrase or action,
                    "Event-driven behaviour without a trigger cannot be implemented consistently or tested.",
                    "State the triggering event or schedule (e.g. 'when X occurs', 'daily at [TBD]').",
                    f"Which event or schedule triggers '{action}'?", secondary="testability")
        if action in DATA_ENTRY - RISKY_OPERATIONS and not has_error:
            ctx.add("MISSING_EXCEPTION_HANDLING", "Error handling not defined", "medium", "completeness",
                    "No behaviour is defined for invalid input or failure cases.", p.action_phrase or action,
                    "Unspecified error behaviour leads to inconsistent messages, data corruption, or security gaps.",
                    "Define how invalid input, duplicates, and failures are handled and reported to the user.",
                    "What should happen when the input is invalid or the operation fails?", secondary="testability")

    sensitive_data = any_term(lower, SENSITIVE_DATA_TERMS)
    if action in SENSITIVE_ACTIONS and is_functional and not has_auth:
        actor_role = (p.secondary_actor or p.actor or "").lower()
        implied = any(word in actor_role for word in ["admin", "manager", "owner", "supervisor", "authorized", "authorised"])
        ctx.add("MISSING_AUTHORIZATION", "Authorization conditions missing", "low" if implied else "high",
                "completeness",
                f"It is not stated who is permitted to '{action}'"
                + (f" {p.object}" if p.object else "") + (" beyond the named role." if implied else "."),
                p.action_phrase or action,
                "Sensitive operations without explicit permission rules are a common source of access-control vulnerabilities.",
                "State which roles may perform the action and how unauthorised attempts are rejected.",
                f"Which roles are allowed to '{action}', and what happens for unauthorised users?", secondary="testability")
    if sensitive_data and not any_term(lower, SECURITY_CONTROLS):
        ctx.add("MISSING_SECURITY_CONSTRAINT", "Security constraint missing for sensitive data", "high", "completeness",
                f"Sensitive data ('{sensitive_data[0]}') is handled without a stated protection control.", sensitive_data[0],
                "Sensitive data without explicit protection (encryption, masking, access control) creates security and compliance risk.",
                "Specify the protection controls, e.g. encryption in transit/at rest, masking, retention and access restrictions.",
                f"How must '{sensitive_data[0]}' be protected in storage, transit and display?", secondary="verifiability")
    if "Security" in ctx.categories and not any_term(lower, SECURITY_CONTROLS) and not sensitive_data:
        ctx.add("MISSING_SECURITY_CONSTRAINT", "Security goal without a control", "high", "completeness",
                "Security is mentioned but no concrete control is specified.", find_phrase(ctx.text, "secure") or truncate(ctx.text, 40),
                "A security goal without controls cannot be implemented or verified.",
                "Name the security controls, the protected assets and the threat being mitigated.",
                "Which concrete security controls are required, and for which assets?", secondary="testability")

    if "Performance" in ctx.categories and not any(m.family in {"time", "rate"} for m in p.measures):
        ctx.add("MISSING_PERFORMANCE_THRESHOLD", "Performance threshold missing", "high", "testability",
                "A performance expectation is stated without a numeric threshold, unit or load condition.",
                (any_term(lower, CATEGORY_RULES["Performance"][0]) or [truncate(ctx.text, 30)])[0],
                "Performance cannot be tested or accepted without a number, unit, percentile and load profile.",
                "Specify the operation, metric (e.g. 95th percentile response time), threshold, unit and load conditions.",
                "What is the maximum acceptable time or minimum throughput, and under what load?", secondary="verifiability")
    for category in ["Availability", "Reliability", "Scalability", "Usability", "Compatibility", "Maintainability"]:
        if category in ctx.categories and not re.search(NFR_METRIC_TERMS.get(category, r"$^"), lower):
            severity = "high" if category in {"Availability", "Reliability", "Scalability"} else "medium"
            evidence = (any_term(lower, CATEGORY_RULES.get(category, ([], 0))[0]) or [category.lower()])[0]
            ctx.add("MISSING_MEASURABLE_TARGET", f"{category} target not measurable", severity, "testability",
                    f"The {category.lower()} expectation has no measurable target.", evidence,
                    f"{category} requirements without a metric cannot be verified or used for acceptance.",
                    {
                        "Availability": "State an uptime percentage, measurement period and treatment of planned maintenance.",
                        "Reliability": "State failure-rate, MTBF/MTTR, RPO/RTO or recovery behaviour targets.",
                        "Scalability": "State expected users, transactions, data volume and growth targets.",
                        "Usability": "State measurable criteria: task success rate, steps, time, or accessibility standard (e.g. WCAG level).",
                        "Compatibility": "List supported browsers, devices, operating systems and minimum versions.",
                        "Maintainability": "State measurable criteria such as module boundaries, test coverage or time to deploy a fix.",
                    }[category],
                    f"What measurable {category.lower()} target applies?", secondary="verifiability")

    if any_term(lower, DEPENDENCY_TERMS) and not p.references:
        dep = any_term(lower, DEPENDENCY_TERMS)[0]
        after = ctx.text[ctx.lower.find(dep.lower()) + len(dep):][:40]
        named = re.search(r"\b[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*", after)
        if not named:
            ctx.add("MISSING_DEPENDENCY", "External dependency not identified", "medium", "completeness",
                    f"The requirement depends on '{dep}' but does not identify the system or its interface.", dep,
                    "Unidentified dependencies hide integration effort, contracts and failure modes until late in the project.",
                    "Name the external system, the interface contract (protocol, data, errors) and the owner.",
                    f"Which exact system is '{dep}', and what is its interface contract?", secondary="traceability")

    is_risky = action in RISKY_OPERATIONS or bool(any_term(lower, DEPENDENCY_TERMS)) or action in {"backup", "restore", "migrate"}
    if is_functional and is_risky and not has_recovery and not has_error:
        severity = "high" if action in {"pay", "purchase", "checkout", "transfer", "refund", "charge", "debit", "backup", "restore", "migrate"} else "medium"
        ctx.add("MISSING_FAILURE_RECOVERY", "Failure and recovery behaviour missing", severity, "completeness",
                f"No behaviour is defined if '{action}' fails part-way (e.g. timeout, unavailable service, partial completion).",
                p.action_phrase or action,
                "Operations that move money, files or data across systems need defined failure handling to avoid data loss or duplicates.",
                "Define the failure modes and the recovery behaviour (retry limits, rollback, user notification).",
                f"What should happen if '{action}' fails or times out?", secondary="testability")

    if any_term(lower, BOUNDARY_WORDS) and not p.measures and not p.bare_numbers:
        word = any_term(lower, BOUNDARY_WORDS)[0]
        ctx.add("MISSING_BOUNDARY", "Boundary value not specified", "medium", "testability",
                f"'{word}' implies a boundary, but no value is given.", word,
                "Boundary conditions are where most defects occur; without the value they cannot be tested.",
                "State the exact boundary value, unit, and whether it is inclusive.",
                f"What is the exact value for '{word}', and is it inclusive?", secondary="completeness")
    numeric_fields = any_term(lower, NUMERIC_FIELD_TERMS)
    if numeric_fields and action in DATA_ENTRY and not p.measures and not ctx.has("MISSING_BOUNDARY"):
        ctx.add("MISSING_BOUNDARY", "Range for numeric input missing", "low", "testability",
                f"'{numeric_fields[0]}' is a numeric input without a valid range.", numeric_fields[0],
                "Without ranges, boundary and negative tests cannot be derived.",
                "Specify minimum, maximum, precision and unit for the value.",
                f"What range of values is valid for '{numeric_fields[0]}'?")
    for m in p.measures:
        if not m.comparator and m.family in {"time", "size", "count", "rate"}:
            ctx.add("MISSING_BOUNDARY", "Direction of limit unclear", "low", "testability",
                    f"'{m.text}' has no comparator, so it is unclear whether it is a maximum, minimum or exact value.", m.text,
                    "Testers need to know which side of the value is acceptable.",
                    "Add 'within', 'at most', 'at least' or 'exactly'.")
            break
    if p.bare_numbers and not p.measures:
        candidates = [n for n in p.bare_numbers if not re.fullmatch(r"(19|20)\d\d", n)]
        if candidates:
            ctx.add("NUMBER_WITHOUT_UNIT", "Number without a unit", "low", "testability",
                    f"The value '{candidates[0]}' has no unit.", candidates[0],
                    "A number without a unit can be misread (seconds vs milliseconds, users vs requests).",
                    "Add the unit and comparator for every numeric value.")

    data_actions = {"store", "save", "record", "maintain", "keep", "retain", "capture", "archive", "import", "export", "persist"}
    entities = any_term(lower, DATA_ENTITY_TERMS)
    if (action in data_actions and entities and not has_validation and not any_term(lower, SECURITY_CONTROLS)
            and not any_term(lower, ["retention", "retain for", "format", "type", "length"])):
        ctx.add("UNSPECIFIED_DATA_CONSTRAINTS", "Data constraints not specified", "medium", "completeness",
                f"Data items ({', '.join(entities[:3])}) are handled without type, format, size, uniqueness or retention rules.",
                ", ".join(entities[:3]),
                "Unspecified data constraints cause inconsistent storage, integration failures and data-quality problems.",
                "Define type, format, size, uniqueness and retention for each data item.",
                f"What are the format, size and retention rules for {entities[0]}?")

    business = any_term(lower, BUSINESS_TERMS)
    if business and not p.measures and not p.bare_numbers:
        ctx.add("INCOMPLETE_BUSINESS_RULE", "Business rule criteria missing", "medium", "completeness",
                f"The business rule involving '{business[0]}' does not state the criteria or values.", business[0],
                "Business rules without values or criteria are implemented by guesswork and are hard to audit.",
                "State the exact criteria, values, calculation and effective conditions of the rule.",
                f"What are the exact criteria and values for '{business[0]}'?", secondary="testability")
    if re.search(r"\b(if|only if|when)\b", lower) and ("Business Rule" in ctx.categories) and not re.search(r"\b(otherwise|else|if not|unless)\b", lower):
        ctx.add("INCOMPLETE_BUSINESS_RULE", "Alternative branch not defined", "low", "completeness",
                "The rule states what happens when the condition holds, but not when it does not.",
                (p.conditions[0] if p.conditions else "if"),
                "Undefined alternative branches lead to inconsistent behaviour for the remaining cases.",
                "State the behaviour when the condition is not met.",
                "What should happen when the condition is not satisfied?")

    unrealistic_hits = []
    for pattern, explanation in UNREALISTIC_PATTERNS:
        match = re.search(pattern, lower)
        if match:
            unrealistic_hits.append(match.group(0))
            ctx.add("UNREALISTIC", "Unrealistic or unverifiable commitment", "high", "feasibility",
                    explanation, ctx.text[match.start():match.end()],
                    "Absolute guarantees cannot be built or proven, so the requirement will always be disputed at acceptance.",
                    "Replace the absolute with a measurable, achievable target.",
                    "What measurable target would be acceptable instead?", secondary="testability")
    for term in ABSOLUTE_TERMS:
        found = find_phrase(ctx.text, term) if term[-1].isalnum() else (term if term in lower else None)
        if found and not any(found.lower() in hit for hit in unrealistic_hits):
            ctx.add("ABSOLUTE_TERM", "Absolute wording", "low", "clarity",
                    f"'{found}' is absolute and may create an unexpectedly broad obligation.", found,
                    "Absolute words remove room for exceptions that usually exist in practice.",
                    "Define the exact scope and the accepted exceptions.", secondary="feasibility")
            break

    if ctx.primary != "Constraint":
        design = [t.strip() for t in DESIGN_TERMS if (t in lower if t.endswith(" ") else contains_phrase(lower, t))]
        if design:
            ctx.add("DESIGN_DETAIL", "Implementation detail in requirement", "low", "feasibility",
                    f"The requirement prescribes a design or technology choice ('{design[0]}').", design[0],
                    "Design details in requirements constrain the solution unnecessarily unless they are genuine constraints.",
                    "Move the design detail to the design document, or record it explicitly as a constraint with its rationale.",
                    f"Is '{design[0]}' a mandatory constraint, or a design suggestion?")

    variants = {canon: v for canon, v in terminology_variants(ctx.text).items() if len(v) >= 2}
    for canon, used in variants.items():
        ctx.add("INCONSISTENT_TERMINOLOGY", "Inconsistent terminology", "low", "consistency",
                f"Different terms are used for the same concept ({', '.join(sorted(used))}).", ", ".join(sorted(used)),
                "Synonyms make readers wonder whether different things are meant.",
                f"Use one term consistently (e.g. '{canon}') and define it in the glossary.")


def _acceptance_check(ctx: Context) -> None:
    p = ctx.parsed
    anchors = sum([
        bool(p.measures),
        bool(p.conditions or p.schedule),
        bool([t for t in any_term(ctx.lower, OUTCOME_TERMS) if t.lower() != (p.action or "")]),
        bool(p.object and not any(w in GENERIC_OBJECTS for w in p.object.lower().split())),
        bool(any_term(ctx.lower, ERROR_TERMS)),
    ])
    piled = any(ctx.has(c) for c in ("MISSING_OUTCOME", "MISSING_POSTCONDITION", "MISSING_INPUTS", "MISSING_OUTPUTS",
                                       "MISSING_PERFORMANCE_THRESHOLD", "MISSING_MEASURABLE_TARGET", "INCOMPLETE"))
    if (anchors == 0 or (anchors == 1 and not piled)) and ctx.primary != "Constraint":
        ctx.add("MISSING_ACCEPTANCE_CRITERIA", "No verifiable acceptance criteria", "medium", "verifiability",
                "The requirement offers too few concrete anchors (measure, trigger, specific outcome, error case) to derive acceptance criteria without assumptions.",
                truncate(ctx.text, 60),
                "Without acceptance criteria, 'done' is decided by opinion and sign-off disputes are likely.",
                "Add Given/When/Then acceptance criteria with observable, measurable results.",
                "How will the requirement owner decide that this requirement is satisfied?", secondary="testability")
    issues_affecting_testability = [f for f in ctx.findings if f.dimension == "testability" or f.secondary_dimension == "testability"]
    if ctx.primary == "Non-Functional" and not p.measures and not ctx.has("MISSING_PERFORMANCE_THRESHOLD") and not ctx.has("MISSING_MEASURABLE_TARGET") and issues_affecting_testability:
        ctx.add("NOT_TESTABLE", "Not testable as written", "high", "testability",
                "This quality requirement has no measurable criterion, so no objective test can pass or fail it.",
                truncate(ctx.text, 60),
                "Untestable requirements cannot be accepted or rejected objectively.",
                "Add a measurable criterion: metric, threshold, unit and measurement conditions.",
                "Which measurable criterion proves this requirement is met?", secondary="verifiability")
    elif (any(f.code == "VAGUE_TERM" and f.severity in {"medium", "high"} for f in ctx.findings) and not p.measures
          and not ctx.has("MISSING_PERFORMANCE_THRESHOLD") and not ctx.has("MISSING_MEASURABLE_TARGET")):
        ctx.add("NOT_TESTABLE", "Not testable as written", "medium", "testability",
                "The requirement relies on subjective wording and has no measurable criterion.",
                next(f.evidence for f in ctx.findings if f.code == "VAGUE_TERM"),
                "A tester cannot write an objective pass/fail check for subjective wording.",
                "Replace the subjective wording with measurable acceptance criteria.",
                "What measurable result proves this requirement is met?", secondary="verifiability")


def _traceability_check(ctx: Context, requirement_id: str | None, id_generated: bool) -> None:
    if id_generated and not ctx.parsed.inline_id:
        ctx.add("MISSING_ID", "No source requirement ID", "low", "traceability",
                "The requirement had no ID in the source document; a generated ID is used.", requirement_id or "—",
                "Without stable IDs, requirements cannot be traced to design, tests and change requests.",
                "Assign a stable, unique ID in the source SRS.")


# ==================================================
# SCORING
# ==================================================

def _score(ctx: Context) -> tuple[int, dict, list[dict], list[str]]:
    dims = {d: 100 for d in DIMENSIONS}
    deductions = {d: [] for d in DIMENSIONS}
    for finding in ctx.findings:
        points = SEVERITY_POINTS[finding.severity]
        finding.points = points
        dims[finding.dimension] -= points
        deductions[finding.dimension].append({"code": finding.code, "points": points, "severity": finding.severity})
        if finding.secondary_dimension:
            half = points // 2
            dims[finding.secondary_dimension] -= half
            deductions[finding.secondary_dimension].append({"code": finding.code, "points": half, "severity": finding.severity, "secondary": True})
    dims = {d: max(0, v) for d, v in dims.items()}
    overall = _combine(dims, [f.severity for f in ctx.findings])
    caps = []
    worst = max((SEVERITY_RANK[f.severity] for f in ctx.findings), default=0)
    if worst >= 4 and overall > SCORE_CAPS["critical"]:
        caps.append(f"Capped at {SCORE_CAPS['critical']} because of a critical finding.")
        overall = SCORE_CAPS["critical"]
    elif worst >= 3 and overall > SCORE_CAPS["high"]:
        caps.append(f"Capped at {SCORE_CAPS['high']} because of a high-severity finding.")
        overall = SCORE_CAPS["high"]
    elif sum(1 for f in ctx.findings if f.severity == "medium") >= 2 and overall > SCORE_CAPS["multi_medium"]:
        caps.append(f"Capped at {SCORE_CAPS['multi_medium']} because of two or more medium-severity findings.")
        overall = SCORE_CAPS["multi_medium"]
    breakdown = [
        {"dimension": d, "weight": DIMENSION_WEIGHTS[d], "score": dims[d], "deductions": deductions[d]}
        for d in DIMENSIONS
    ]
    return overall, dims, breakdown, caps


def _combine(dims: dict, severities: list[str]) -> int:
    """Overall = 40% weighted dimension average + 60% finding penalty.

    The penalty multiplies 100 by (1 - points/100) for every finding, so each
    additional problem lowers the score with diminishing effect:
    critical x0.65, high x0.78, medium x0.86, low x0.94.
    """
    weighted = sum(dims[d] * w for d, w in DIMENSION_WEIGHTS.items())
    penalty = 100.0
    for severity in severities:
        penalty *= 1 - SEVERITY_POINTS.get(severity, 0) / 100
    return round(0.4 * weighted + 0.6 * penalty)


def rescore(analysis: dict, extra_findings: list[dict]) -> None:
    """Apply document-level findings (contradictions, duplicate IDs...) to an analysis in place."""
    if not extra_findings:
        return
    dims = dict(analysis["dimension_scores"])
    for finding in extra_findings:
        points = SEVERITY_POINTS.get(finding["severity"], 0)
        finding["points_deducted"] = points
        dims[finding["dimension"]] = max(0, dims[finding["dimension"]] - points)
        for row in analysis["score_breakdown"]:
            if row["dimension"] == finding["dimension"]:
                row["deductions"].append({"code": finding["code"], "points": points, "severity": finding["severity"], "document_level": True})
                row["score"] = dims[finding["dimension"]]
        analysis["detailed_findings"].append(finding)
        analysis["issues"].append(finding["message"])
    analysis["dimension_scores"] = dims
    overall = _combine(dims, [f["severity"] for f in analysis["detailed_findings"]])
    worst = max((SEVERITY_RANK.get(f["severity"], 0) for f in analysis["detailed_findings"]), default=0)
    if worst >= 4:
        overall = min(overall, SCORE_CAPS["critical"])
    elif worst >= 3:
        overall = min(overall, SCORE_CAPS["high"])
    elif sum(1 for f in analysis["detailed_findings"] if f["severity"] == "medium") >= 2:
        overall = min(overall, SCORE_CAPS["multi_medium"])
    analysis["quality_score"] = overall
    _apply_labels(analysis)


# ==================================================
# REVIEW GENERATION
# ==================================================

def _past(verb: str) -> str:
    reverse = {v: k for k, v in IRREGULAR_PARTICIPLES.items()}
    if verb in reverse:
        return reverse[verb]
    if verb in {"log", "plan", "ship", "stop", "drop", "tag", "flag", "chat", "submit", "commit", "transfer", "cancel"}:
        return verb + verb[-1] + "ed" if verb not in {"cancel"} else "cancelled"
    if verb.endswith("e"):
        return verb + "d"
    if verb.endswith("y") and verb[-2:-1] not in "aeiou":
        return verb[:-1] + "ied"
    return verb + "ed"


def _strip_trigger(clause: str) -> str:
    return re.sub(r"^(when(ever)?|if|after|upon|once|as soon as|on)\s+", "", clause, flags=re.I).strip()


def _strengths(ctx: Context) -> list[dict]:
    p = ctx.parsed
    lower = ctx.lower
    out = []
    if p.actor_kind in {"system", "human"} and p.actor:
        out.append({"strength": "The responsible actor is explicit.", "evidence": p.actor})
    if p.modal_kind in {"mandatory", "prohibition"}:
        out.append({"strength": "The obligation level is explicit.", "evidence": p.modal})
    if p.action and p.action != "be" and p.action in ACTION_VERBS:
        out.append({"strength": "An observable action is stated.", "evidence": p.action_phrase or p.action})
    for m in p.measures[:2]:
        out.append({"strength": "A measurable constraint is given.", "evidence": m.text})
    if p.conditions:
        out.append({"strength": "The trigger or condition is stated.", "evidence": p.conditions[0]})
    if p.schedule:
        out.append({"strength": "Timing or schedule is stated.", "evidence": p.schedule})
    errors = any_term(lower, ERROR_TERMS)
    if errors:
        out.append({"strength": "Error or exception behaviour is addressed.", "evidence": errors[0]})
    auth = any_term(lower, AUTHORIZATION_TERMS)
    if auth:
        out.append({"strength": "Access restrictions are stated.", "evidence": auth[0].strip()})
    controls = any_term(lower, SECURITY_CONTROLS)
    if controls:
        out.append({"strength": "A concrete security control is named.", "evidence": controls[0]})
    if p.user_story and p.user_story.get("benefit"):
        out.append({"strength": "The user value is stated.", "evidence": "so that " + p.user_story["benefit"]})
    if p.references:
        out.append({"strength": "It references related items for traceability.", "evidence": ", ".join(p.references[:3])})
    if not ctx.has("NON_ATOMIC") and p.word_count >= 6:
        out.append({"strength": "It expresses a single obligation.", "evidence": truncate(ctx.text, 50)})
    return out


def _improved_draft(ctx: Context) -> tuple[str, list[str]]:
    p = ctx.parsed
    notes: list[str] = []
    codes = {f.code for f in ctx.findings}
    if not ctx.findings or all(f.severity == "low" for f in ctx.findings) and len(ctx.findings) <= 1:
        return ctx.text, ["No material rewrite needed; confirm wording with the requirement owner."]

    if p.user_story:
        story = p.user_story
        benefit = story.get("benefit") or "[TBD: business value]"
        if not story.get("benefit"):
            notes.append("Added a placeholder for the missing user value ('so that ...').")
        draft = f"As a {story['role']}, I want to {story['goal']} so that {benefit}."
        extras = []
        if codes & {"MISSING_ACCEPTANCE_CRITERIA", "NOT_TESTABLE"}:
            extras.append("Acceptance: [TBD: observable, measurable acceptance criteria].")
        return " ".join([draft] + extras), notes

    draft = ctx.text.rstrip(" .")
    for finding in ctx.findings:
        if finding.code in {"VAGUE_TERM"} and finding.evidence and finding.evidence in draft:
            spec = VAGUE_TERMS.get(finding.evidence.lower(), ("", "a measurable criterion"))[1]
            draft = re.sub(r"(?<![A-Za-z])" + re.escape(finding.evidence) + r"(?![A-Za-z])",
                           f"{finding.evidence} [TBD: {spec}]", draft, count=1)
            notes.append(f"Marked '{finding.evidence}' for a measurable definition.")
        if finding.code == "OPEN_ENDED" and finding.evidence.lower() in {"etc", "and so on", "and more", "among others"}:
            draft = re.sub(r",?\s*(etc\.?|and so on|and more|among others)", " and [TBD: complete list of items]", draft, count=1, flags=re.I)
            notes.append("Replaced the open-ended list ending with a placeholder for the complete list.")
        if finding.code == "OPEN_ENDED" and finding.evidence.lower() == "and/or":
            draft = draft.replace(finding.evidence, "[TBD: 'and' or 'or']", 1)
            notes.append("Marked 'and/or' for a decision.")
    if p.actor_kind == "pronoun" and p.actor:
        draft = re.sub(r"^" + re.escape(p.actor), "[TBD: system or component name]", draft, count=1)
        notes.append("Replaced the pronoun subject with a placeholder for the exact component.")
    if p.modal in {"should", "will", "needs to", "need to", "has to", "have to"}:
        draft = re.sub(r"(?<![A-Za-z])" + re.escape(p.modal) + r"(?![A-Za-z])", "shall", draft, count=1, flags=re.I)
        notes.append(f"Changed '{p.modal}' to 'shall' — confirm the requirement is mandatory.")
    elif not p.modal and p.action and p.action_phrase and p.actor:
        draft = re.sub(r"(?<![A-Za-z])" + re.escape(p.action_phrase) + r"(?![A-Za-z])", f"shall {p.action}", draft, count=1)
        notes.append("Added the modal 'shall' to state the obligation.")
    if p.actor_kind == "missing" and not p.user_story:
        draft = "[TBD: responsible actor] " + draft[0].lower() + draft[1:] if draft else draft
        notes.append("Added a placeholder for the responsible actor.")
    if "UNCLEAR_TRIGGER" in codes:
        draft = "When [TBD: triggering event or schedule], " + draft[0].lower() + draft[1:]
        notes.append("Added a placeholder for the trigger.")
    elif "MISSING_PRECONDITION" in codes and any(f.code == "MISSING_PRECONDITION" and f.severity != "low" for f in ctx.findings):
        draft = "Given [TBD: precondition], " + draft[0].lower() + draft[1:]
        notes.append("Added a placeholder for the precondition.")

    if "NON_ATOMIC" in codes:
        parts = [s.rstrip(" .") for s in sentences(draft) if s.strip()]
        if len(parts) < 2 and p.coordinated_actions and p.actor and p.object:
            modal = "shall" if p.modal in {None, "should", "will", "can", "may"} else p.modal
            subject = p.actor
            who = f" allow {p.secondary_actor} to" if p.secondary_actor else ""
            parts = [f"{subject} {modal}{who} {verb} {p.object}" for verb in [p.action] + p.coordinated_actions]
        if len(parts) >= 2:
            draft = " ".join(f"({i}) {part}." for i, part in enumerate(parts, start=1))
            notes.append("Split the compound statement into separately verifiable obligations.")

    additions = []
    if "MISSING_INPUTS" in codes:
        additions.append("The required inputs are [TBD: fields, formats and which are mandatory].")
    if "MISSING_VALIDATION_RULES" in codes:
        additions.append("Inputs shall be validated against [TBD: format, length and range rules].")
    if codes & {"MISSING_OUTCOME", "MISSING_POSTCONDITION"}:
        additions.append("On success, the system shall [TBD: resulting state and user feedback].")
    if "MISSING_OUTPUTS" in codes:
        additions.append("The output shall contain [TBD: fields, ordering and format].")
    if "MISSING_AUTHORIZATION" in codes:
        additions.append("Only [TBD: authorised roles] shall be permitted to perform this action; unauthorised attempts shall be [TBD: rejected and logged].")
    if "MISSING_SECURITY_CONSTRAINT" in codes:
        additions.append("[TBD: protection controls, e.g. encryption, masking, access restrictions] shall apply.")
    if codes & {"MISSING_PERFORMANCE_THRESHOLD", "MISSING_MEASURABLE_TARGET", "NOT_TESTABLE"}:
        additions.append("Measurable criterion: [TBD: metric, threshold, unit and measurement conditions].")
    if "MISSING_EXCEPTION_HANDLING" in codes:
        additions.append("If [TBD: invalid input or error condition], the system shall [TBD: error behaviour and message] without changing stored data.")
    if "MISSING_FAILURE_RECOVERY" in codes:
        additions.append("If the operation fails, the system shall [TBD: recovery behaviour, e.g. retry limit or rollback] and inform [TBD: affected actor].")
    if "MISSING_DEPENDENCY" in codes:
        additions.append("The external system is [TBD: name, interface and owner].")
    if "UNSPECIFIED_DATA_CONSTRAINTS" in codes:
        additions.append("Data constraints: [TBD: type, format, size, uniqueness and retention].")
    if "INCOMPLETE_BUSINESS_RULE" in codes:
        additions.append("Rule criteria: [TBD: exact values, conditions and the behaviour when the condition is not met].")
    if additions:
        notes.append("Added placeholders for missing information instead of inventing values.")
    text = draft if draft.endswith(".") else draft + "."
    return " ".join([text] + additions), unique(notes)


def _acceptance_criteria(ctx: Context) -> list[dict]:
    p = ctx.parsed
    codes = {f.code for f in ctx.findings}
    system = p.actor if p.actor_kind == "system" else "the system"
    human = p.secondary_actor or (p.actor if p.actor_kind == "human" else None)
    obj = p.object
    action = p.action if p.action and p.action != "be" else None
    criteria = []
    obj_text = f" {obj}" if obj else ""
    verb_be = "are" if obj and re.search(r"[^s]s$", obj.split()[-1]) else "is"
    true_triggers = [c for c in p.conditions if re.match(r"^(when(ever)?|if|after|upon|once|as soon as|on |each time|every time|following)", c, re.I)]

    if p.passive and action:
        rest = ctx.text.lower().split((p.action_phrase or "").lower(), 1)[-1].strip(" .")
        criteria.append({
            "id": "AC-01",
            "given": "[TBD: representative test data]",
            "when": f"{obj or 'the data'} {verb_be} {_past(action)}",
            "then": "inspection confirms it is " + _past(action) + (f" {rest}" if rest else "") + (f" ({p.measures[0].text})" if p.measures else ""),
        })
        return criteria

    if ctx.primary == "Non-Functional" or not action:
        target = p.measures[0].text if p.measures else "[TBD: measurable target]"
        subject = p.state_predicate or obj
        criteria.append({
            "id": "AC-01",
            "given": "[TBD: test environment, data volume and load profile]",
            "when": f"{subject} is measured over [TBD: measurement period]" if subject else "the quality attribute is measured",
            "then": f"the result satisfies {target}",
        })
        for i, m in enumerate(p.measures[1:3], start=2):
            criteria.append({"id": f"AC-0{i}", "given": "[TBD: test conditions]", "when": "the measurement is taken",
                             "then": f"the result satisfies {m.text}"})
        return criteria

    authorised = bool(any_term(ctx.lower, AUTHORIZATION_TERMS))
    given = _strip_trigger(true_triggers[0]) if true_triggers else (
        "the actor is authorised" if authorised else "[TBD: precondition]")
    system_l = system[0].lower() + system[1:] if system else "the system"
    when = f"{human} requests to {action}{obj_text}" if human else f"{system_l} is required to {action}{obj_text}"
    if true_triggers and not human:
        when = _strip_trigger(true_triggers[0])
        given = "the actor is authorised" if authorised else "the system is operational"
    if obj and action in ACTION_VERBS:
        then_parts = [f"{obj} {verb_be} {_past(action)}"]
    else:
        then_parts = [f"the '{action}' operation completes successfully"]
    if p.measures:
        then_parts.append(f"within the stated limit ({p.measures[0].text})")
    if codes & {"MISSING_OUTCOME", "MISSING_POSTCONDITION"}:
        then_parts.append("and [TBD: confirmation / resulting state] is observable")
    criteria.append({"id": "AC-01", "given": given + (" and valid input is provided" if action in DATA_ENTRY else ""),
                     "when": when, "then": " ".join(then_parts)})

    if action in DATA_ENTRY or "MISSING_VALIDATION_RULES" in codes:
        criteria.append({"id": f"AC-0{len(criteria) + 1}", "given": "an input violates [TBD: validation rule]",
                         "when": f"the actor attempts to {action}{obj_text}",
                         "then": "the system rejects the request, shows [TBD: error message], and no data is changed"})
    if action in SENSITIVE_ACTIONS:
        criteria.append({"id": f"AC-0{len(criteria) + 1}", "given": "the actor lacks the required permission",
                         "when": f"the actor attempts to {action}{obj_text}",
                         "then": "the action is denied, no data changes, and the attempt is [TBD: logged / reported]"})
    if p.negated:
        criteria.append({"id": f"AC-0{len(criteria) + 1}", "given": given,
                         "when": f"an actor attempts to {action}{obj_text}",
                         "then": "the system prevents the action"})
    for m in p.measures[:1]:
        criteria.append({"id": f"AC-0{len(criteria) + 1}", "given": f"the operation runs at the stated limit ({m.text})",
                         "when": f"{action} is performed", "then": "the limit is respected and [TBD: behaviour beyond the limit] applies"})
    return criteria[:5]


def _test_scenarios(ctx: Context) -> dict:
    p = ctx.parsed
    action = p.action if p.action and p.action != "be" else None
    obj = p.object or "the item"
    positive, negative, boundary = [], [], []
    if action:
        positive.append(f"Perform '{action} {obj}' with valid data and preconditions; verify the expected result"
                        + (f" {p.measures[0].text}." if p.measures else "."))
    else:
        positive.append(f"Measure the quality attribute under the agreed conditions; verify {p.measures[0].text if p.measures else '[TBD: target]'}.")
    for condition in p.conditions[:2]:
        positive.append(f"Trigger the condition '{condition}' and verify the behaviour occurs.")
    if p.schedule:
        positive.append(f"Verify the behaviour runs on schedule ({p.schedule}).")
    if p.secondary_actor or p.actor_kind == "human":
        positive.append(f"Verify '{p.secondary_actor or p.actor}' can complete the flow end to end.")

    if action in DATA_ENTRY:
        negative.append(f"Submit invalid or malformed input when trying to {action} {obj}; verify rejection and no data change.")
        negative.append(f"Omit each mandatory input when trying to {action} {obj}; verify a clear validation message.")
    if action in SENSITIVE_ACTIONS or any_term(ctx.lower, AUTHORIZATION_TERMS):
        negative.append(f"Attempt to {action} {obj} as an unauthorised user; verify access is denied and logged.")
    if action in RISKY_OPERATIONS or any_term(ctx.lower, DEPENDENCY_TERMS):
        negative.append(f"Simulate a timeout or unavailable dependency during '{action}'; verify no partial or duplicate result.")
    if p.negated and action:
        negative.append(f"Attempt to {action} {obj} as described in the prohibition; verify it is blocked.")
    if p.conditions:
        negative.append(f"Verify the behaviour does NOT occur when '{_strip_trigger(p.conditions[0])}' is not met.")
    if not negative:
        negative.append("[TBD: negative cases once error behaviour is defined]")

    for m in p.measures[:2]:
        if m.family == "count" and float(m.value).is_integer():
            v = int(m.value)
            boundary.append(f"Test at {v - 1}, {v} and {v + 1} {m.unit} to verify the limit '{m.text}'.")
        elif m.family == "time":
            boundary.append(f"Measure at nominal and peak load; verify the time stays {m.text}.")
        elif m.family == "size":
            boundary.append(f"Use inputs just below, at and just above {m.value:g} {m.unit}; verify acceptance and rejection.")
        elif m.family == "percent":
            boundary.append(f"Verify the measured value against {m.text} over the agreed period.")
        else:
            boundary.append(f"Test values at and around the limit '{m.text}'.")
    if not boundary:
        boundary.append("[TBD: boundary values once limits are specified]" if any(
            f.code in {"MISSING_BOUNDARY", "MISSING_VALIDATION_RULES", "MISSING_INPUTS"} for f in ctx.findings)
            else "No explicit limits stated; confirm whether any boundaries apply.")
    return {"positive": positive, "negative": negative, "boundary": boundary}


def _priority(ctx: Context) -> tuple[str, str]:
    worst = max((SEVERITY_RANK[f.severity] for f in ctx.findings), default=0)
    risk = sorted(set(ctx.categories) & RISK_CATEGORIES)
    money = any_term(ctx.lower, ["payment", "pay", "refund", "transfer", "invoice", "billing", "card"])
    drivers = []
    if worst >= 4:
        level = "Critical"
        drivers.append("a critical finding")
    elif worst >= 3 and (risk or money):
        level = "Critical"
        drivers.append("a high-severity finding in a " + ("security/privacy/compliance" if risk else "financial") + " requirement")
    elif worst >= 3:
        level = "High"
        drivers.append("at least one high-severity finding")
    elif worst >= 2 and (risk or money):
        level = "High"
        drivers.append("medium-severity findings in a sensitive area")
    elif worst >= 2:
        level = "Medium"
        drivers.append("medium-severity findings")
    else:
        level = "Low"
        drivers.append("only minor or no findings")
    if ctx.parsed.modal_kind in {"mandatory", "prohibition"}:
        drivers.append("mandatory obligation")
    return level, "Priority is " + level.lower() + " because of " + " and ".join(drivers) + "."


def _status(score: int) -> str:
    return "Good" if score >= 80 else "Needs Improvement" if score >= 60 else "Poor"


def _apply_labels(analysis: dict) -> None:
    dims = analysis["dimension_scores"]
    analysis["status"] = _status(analysis["quality_score"])
    analysis["clarity"] = "Good" if dims["clarity"] >= 85 else "Moderate" if dims["clarity"] >= 65 else "Poor"
    analysis["completeness"] = "Complete" if dims["completeness"] >= 85 else "Partial" if dims["completeness"] >= 60 else "Incomplete"
    analysis["testability"] = "Testable" if dims["testability"] >= 85 else "Partially Testable" if dims["testability"] >= 60 else "Not Testable"
    worst = max((SEVERITY_RANK.get(f["severity"], 0) for f in analysis["detailed_findings"]), default=0)
    analysis["severity"] = {4: "Critical", 3: "High", 2: "Medium", 1: "Low", 0: "None"}[worst]
    analysis["issue_count"] = len([f for f in analysis["detailed_findings"] if f["severity"] != "info"])


# ==================================================
# PUBLIC ENTRY POINT
# ==================================================

def analyze_requirement(text: str, requirement_id: str | None = None, id_generated: bool = False,
                        source: str | None = None, section: str | None = None) -> dict:
    parsed = parse(text)
    check_text = parsed.text
    if parsed.user_story and parsed.user_story.get("benefit"):
        check_text = re.split(r",?\s+so\s+that\s+", parsed.text, maxsplit=1, flags=re.I)[0]
    classification = classify(parsed, check_text)
    primary = classification["primary"]
    functional = primary in {"Functional", "User Story", "Business Rule"} or (
        primary == "Non-Functional" and parsed.action not in {None, "be"} and parsed.action in ACTION_VERBS
        and not parsed.passive and parsed.actor_kind in {"system", "human"})
    ctx = Context(parsed, check_text, check_text.lower(), classification["categories"], primary, functional)

    _structure_checks(ctx)
    _vague_checks(ctx)
    _ambiguity_checks(ctx)
    _behaviour_checks(ctx)
    _acceptance_check(ctx)
    _traceability_check(ctx, requirement_id, id_generated)

    ctx.findings.sort(key=lambda f: -SEVERITY_RANK[f.severity])
    overall, dims, breakdown, caps = _score(ctx)
    findings = [f.as_dict() for f in ctx.findings]
    improved, rewrite_notes = _improved_draft(ctx)
    priority, priority_reason = _priority(ctx)
    questions = unique(f.question for f in ctx.findings if f.question)[:8]
    strengths = _strengths(ctx)

    top = findings[0] if findings else None
    explanation = (
        f"Classified as {primary}"
        + (f" ({', '.join(c for c in classification['categories'] if c != primary)[:80]})" if len(classification["categories"]) > 1 else "")
        + f". Detected actor: {parsed.actor or 'none'}; action: {parsed.action or 'none'}; "
        + f"obligation: {parsed.modal_kind or 'not stated'}; measurable constraints: {len(parsed.measures)}. "
        + (f"{len(findings)} finding(s); most severe: {top['title']} ({top['severity']}). " if top else "No issues detected by the configured checks. ")
        + "Score = 40% weighted average of eight dimension scores (each 100 minus documented deductions) + 60% per-finding penalty."
        + (" " + " ".join(caps) if caps else "")
    )

    analysis = {
        "requirement_id": requirement_id,
        "quality_score": overall,
        "classification": primary,
        "categories": classification["categories"],
        "category_evidence": classification["evidence"],
        "dimension_scores": dims,
        "score_breakdown": breakdown,
        "score_caps": caps,
        "detailed_findings": findings,
        "issues": [f["message"] for f in findings],
        "ambiguities": unique(f["message"] for f in findings if f["code"] in {
            "VAGUE_TERM", "AMBIGUOUS_PHRASE", "UNCLEAR_REFERENCE", "OPEN_ENDED", "WEAK_MODAL", "MISSING_ACTOR"}),
        "missing_information": unique(f["recommendation"] for f in findings if f["code"].startswith("MISSING_") or f["code"] in {"INCOMPLETE", "INCOMPLETE_BUSINESS_RULE", "UNCLEAR_TRIGGER", "UNSPECIFIED_DATA_CONSTRAINTS"}),
        "strengths": strengths,
        "improved_requirement": improved,
        "suggested_rewrite": improved,
        "rewrite_notes": rewrite_notes,
        "clarification_questions": questions,
        "acceptance_criteria": _acceptance_criteria(ctx),
        "test_scenarios": _test_scenarios(ctx),
        "priority": priority,
        "priority_reason": priority_reason,
        "structure": parsed.summary(),
        "explanation": explanation,
        "source": source,
        "section": section,
        "cross_references": [],
    }
    _apply_labels(analysis)
    return analysis
