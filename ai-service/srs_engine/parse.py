"""Pattern-based structural parsing of a single requirement statement.

Extracts the parts a reviewer looks for: actor, modal verb, main action,
object, triggers/conditions, measurable constraints, references and
user-story structure. Every extracted part keeps the original wording so it
can be shown as evidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .lexicon import (
    ACTION_VERBS, HUMAN_ACTORS, IRREGULAR_PARTICIPLES, MODALS, PRONOUNS, REQUIREMENT_ID_PATTERN,
    SCHEDULE_PATTERN, SYSTEM_ACTORS, VERB_FILLERS,
)
from .text import normalize_space, sentences, words

MODAL_RE = re.compile(
    r"(?<![A-Za-z])(" + "|".join(re.escape(m) for m in sorted(MODALS, key=len, reverse=True)) + r")(?![A-Za-z])",
    re.I,
)
INLINE_ID_RE = re.compile(
    r"^\s*[\[(]?(" + REQUIREMENT_ID_PATTERN + r")[\])]?\s*(?:[:\-–—.)]\s*|\s+(?=[A-Z]))"
)
REFERENCE_RE = re.compile(
    r"\b((?:REQ|FR|NFR|SR|UR|BR|SRS|UC|US|SEC|PR|DR|IR|CR)[-_ ]?\d+(?:\.\d+)*)\b|\b(section\s+\d+(?:\.\d+)*)\b",
    re.I,
)
USER_STORY_RE = re.compile(
    r"^\s*as an?\s+(?P<role>.+?),?\s+i\s+(?:want|need|would like|wish|can)\s+(?:to\s+)?(?P<goal>.+?)"
    r"(?:,?\s+so\s+that\s+(?P<benefit>.+?))?\.?\s*$",
    re.I,
)
TRIGGER_RE = re.compile(
    r"\b(when(?:ever)?|if|unless|after|before|upon|once|until|while|during|in case(?: of)?|as soon as|prior to|"
    r"on (?:successful|failed|receipt|completion|submission|login|logout)|each time|every time|following)\b"
    r"([^,.;]*)",
    re.I,
)
HUMAN_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in sorted(HUMAN_ACTORS, key=len, reverse=True)) + r")s?\b")
SYSTEM_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in sorted(SYSTEM_ACTORS, key=len, reverse=True)) + r")s?\b")
NOT_REAL_TRIGGERS = re.compile(r"^(if|when|where)\s+(possible|necessary|needed|required|applicable|appropriate)\b", re.I)

NUM = r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
UNIT_GROUPS = {
    "time": r"ms|msec|milliseconds?|s|secs?|seconds?|minutes?|mins?|hours?|hrs?|h|days?|weeks?|months?|years?",
    "percent": r"%|percent|per cent",
    "size": r"kb|mb|gb|tb|kilobytes?|megabytes?|gigabytes?|terabytes?|bytes?",
    "rate": r"(?:requests?|transactions?|queries|messages?|events?|tps|rps)\s*(?:per|/)\s*(?:second|sec|s|minute|min|hour)|tps|rps|kbps|mbps|gbps",
    "count": r"concurrent users?|simultaneous users?|users?|requests?|transactions?|attempts?|tries|retries|"
             r"characters?|chars?|digits?|items?|records?|files?|pages?|times?|clicks?|steps?|rows?|sessions?|"
             r"products?|orders?|accounts?|members?|levels?|decimal places?|words?|images?|photos?|seats?|tickets?",
    "currency": r"rs\.?|inr|usd|eur|gbp|dollars?|rupees?|euros?",
}
MEASURE_RE = re.compile(
    r"(?P<cmp>within|in under|under|less than|fewer than|below|no more than|not more than|not exceed(?:ing)?|"
    r"at most|maximum of|max(?:imum)?|up to|at least|minimum of|min(?:imum)?|more than|greater than|over|above|"
    r"exactly|between|<=|>=|≤|≥|<|>)?\s*(?P<cur>[$₹€£])?\s*" + NUM + r"\s*"
    r"(?P<unit>" + "|".join(f"(?:{u})" for u in UNIT_GROUPS.values()) + r")(?![A-Za-z])",
    re.I,
)
TIME_FACTORS = {"ms": 0.001, "msec": 0.001, "millisecond": 0.001, "s": 1, "sec": 1, "second": 1, "minute": 60,
                "min": 60, "hour": 3600, "hr": 3600, "h": 3600, "day": 86400, "week": 604800,
                "month": 2592000, "year": 31536000}
SIZE_FACTORS = {"kb": 0.001, "kilobyte": 0.001, "mb": 1, "megabyte": 1, "gb": 1000, "gigabyte": 1000,
                "tb": 1_000_000, "terabyte": 1_000_000, "byte": 0.000001}
OBJECT_BOUNDARY = {
    "within", "when", "whenever", "if", "unless", "after", "before", "upon", "once", "until", "while",
    "during", "by", "using", "via", "so", "in", "for", "from", "to", "with", "without", "on", "at", "and",
    "or", "but", "that", "which", "who", "where", "through", "into", "under", "less", "more", "than",
    "every", "each", "as", "only", "based", "such", "including", "except",
}
DETERMINERS = {"the", "a", "an", "all", "any", "each", "every", "their", "his", "her", "its", "our", "your", "this", "that", "these", "those"}
PROVIDE_NOUNS = {"ability", "functionality", "option", "capability", "facility", "feature", "mechanism",
                 "means", "function", "interface", "way", "possibility", "tool", "support"}


@dataclass
class Measure:
    text: str
    value: float
    unit: str
    family: str
    comparator: str | None
    normalized: float | None

    def as_dict(self) -> dict:
        return {"text": self.text, "value": self.value, "unit": self.unit, "family": self.family,
                "comparator": self.comparator}


@dataclass
class ParsedRequirement:
    original: str
    text: str
    inline_id: str | None = None
    sentence_list: list[str] = field(default_factory=list)
    modal: str | None = None
    modal_kind: str | None = None
    modal_strength: int = 0
    modals_found: list[str] = field(default_factory=list)
    negated: bool = False
    actor: str | None = None
    actor_kind: str = "missing"
    secondary_actor: str | None = None
    action: str | None = None
    action_phrase: str | None = None
    coordinated_actions: list[str] = field(default_factory=list)
    passive: bool = False
    state_predicate: str | None = None
    object: str | None = None
    conditions: list[str] = field(default_factory=list)
    schedule: str | None = None
    measures: list[Measure] = field(default_factory=list)
    bare_numbers: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    user_story: dict | None = None
    word_count: int = 0

    def summary(self) -> dict:
        return {
            "inline_id": self.inline_id,
            "actor": self.actor,
            "actor_type": self.actor_kind,
            "secondary_actor": self.secondary_actor,
            "modal": self.modal,
            "obligation": self.modal_kind,
            "action": self.action,
            "object": self.object,
            "passive_voice": self.passive,
            "conditions": self.conditions,
            "schedule": self.schedule,
            "measures": [m.as_dict() for m in self.measures],
            "references": self.references,
            "user_story": self.user_story,
            "sentences": len(self.sentence_list),
            "words": self.word_count,
        }


def lemma(word: str) -> str:
    w = word.lower().strip("'\"")
    if w in IRREGULAR_PARTICIPLES:
        return IRREGULAR_PARTICIPLES[w]
    if w in ACTION_VERBS:
        return w
    candidates = []
    if w.endswith("ies") or w.endswith("ied"):
        candidates.append(w[:-3] + "y")
    if w.endswith("ing"):
        candidates += [w[:-3], w[:-3] + "e", w[:-4]]
    if w.endswith("ed"):
        candidates += [w[:-1], w[:-2], w[:-3]]
    if w.endswith("es"):
        candidates += [w[:-2], w[:-1]]
    if w.endswith("s"):
        candidates.append(w[:-1])
    for candidate in candidates:
        if candidate in ACTION_VERBS:
            return candidate
    return candidates[0] if candidates else w


def _is_participle(word: str) -> bool:
    w = word.lower()
    return w in IRREGULAR_PARTICIPLES or (w.endswith("ed") and len(w) > 4) or w.endswith("en")


def _actor_kind(actor: str | None, passive: bool) -> str:
    if not actor:
        return "missing"
    tokens = words(actor)
    if not tokens:
        return "missing"
    if all(t in PRONOUNS for t in tokens):
        return "pronoun"
    joined = " ".join(tokens)
    if HUMAN_RE.search(joined):
        return "human"
    if SYSTEM_RE.search(joined):
        return "system"
    if passive:
        return "passive-subject"
    return "other"


def _clean_actor(prefix: str) -> str | None:
    prefix = prefix.strip(" ,;:-")
    if "," in prefix:  # "When X happens, the system" -> "the system"
        prefix = prefix.split(",")[-1]
    prefix = TRIGGER_RE.sub("", prefix) if TRIGGER_RE.match(prefix.strip()) else prefix
    prefix = re.sub(r"^(?:and|or|then|also|only)\s+", "", prefix.strip(), flags=re.I)
    tokens = prefix.split()
    if not tokens:
        return None
    if len(tokens) > 8:
        tokens = tokens[-8:]
    return " ".join(tokens).strip(" ,;:")


def _take_object(tokens: list[str]) -> str | None:
    picked = []
    for token in tokens:
        bare = token.strip(",.;:()\"'").lower()
        if not bare:
            break
        if bare in OBJECT_BOUNDARY and picked:
            break
        if bare in DETERMINERS and not picked:
            continue
        if bare in OBJECT_BOUNDARY:
            continue
        picked.append(token.strip(",.;:()\"'"))
        if token.rstrip().endswith((",", ".", ";", ":")) or len(picked) >= 6:
            break
    return " ".join(picked) or None


def _measures(text: str) -> tuple[list[Measure], list[str]]:
    found: list[Measure] = []
    spans = []
    for match in MEASURE_RE.finditer(text):
        raw_value = match.group(3).replace(",", "")
        try:
            value = float(raw_value)
        except ValueError:
            continue
        unit = match.group("unit").lower().strip()
        family = next((name for name, pattern in UNIT_GROUPS.items()
                       if re.fullmatch(f"(?:{pattern})", unit, re.I)), "count")
        if match.group("cur"):
            family = "currency"
        normalized = None
        unit_key = re.sub(r"s$", "", unit) if unit not in {"s", "ms"} else unit
        if family == "time":
            normalized = value * TIME_FACTORS.get(unit_key, TIME_FACTORS.get(unit, 1))
        elif family == "size":
            normalized = value * SIZE_FACTORS.get(unit_key, 1)
        else:
            normalized = value
        comparator = (match.group("cmp") or "").lower() or None
        found.append(Measure(match.group(0).strip(), value, unit, family, comparator, normalized))
        spans.append(match.span())
    bare = []
    for match in re.finditer(r"(?<![A-Za-z0-9.\-_/])\d+(?:\.\d+)?(?![A-Za-z0-9.%\-_/])", text):
        if any(start <= match.start() < end for start, end in spans):
            continue
        bare.append(match.group(0))
    return found, bare


def _currency_measures(text: str) -> list[Measure]:
    out = []
    for match in re.finditer(r"([$₹€£])\s*" + NUM, text):
        value = float(match.group(2).replace(",", ""))
        out.append(Measure(match.group(0), value, match.group(1), "currency", None, value))
    return out


def parse(requirement: str) -> ParsedRequirement:
    original = str(requirement or "")
    text = normalize_space(original)
    parsed = ParsedRequirement(original=original, text=text)

    id_match = INLINE_ID_RE.match(text)
    if id_match and len(text) > len(id_match.group(0)) + 3:
        parsed.inline_id = id_match.group(1)
        text = text[id_match.end():].strip()
    text = re.sub(r"^[•\-–—*·]\s+", "", text)
    parsed.text = text
    parsed.sentence_list = sentences(text) or [text]
    parsed.word_count = len(words(text))

    story = USER_STORY_RE.match(text)
    if story:
        parsed.user_story = {k: (v or "").strip() or None for k, v in story.groupdict().items()}

    parsed.modals_found = [m.group(1).lower() for m in MODAL_RE.finditer(text)]
    target_sentence = next((s for s in parsed.sentence_list if MODAL_RE.search(s)), parsed.sentence_list[0])
    modal_match = MODAL_RE.search(target_sentence)

    if parsed.user_story:
        parsed.actor = parsed.user_story["role"]
        parsed.actor_kind = "human"
        goal_tokens = (parsed.user_story["goal"] or "").split()
        if goal_tokens:
            parsed.action = lemma(goal_tokens[0])
            parsed.action_phrase = goal_tokens[0]
            parsed.object = _take_object(goal_tokens[1:])
        parsed.modal_kind = "user story"
    elif modal_match:
        modal = modal_match.group(1).lower()
        parsed.modal = modal
        parsed.modal_kind, parsed.modal_strength = MODALS[modal]
        parsed.negated = parsed.modal_kind == "prohibition" or bool(re.match(r"\s+not\b", target_sentence[modal_match.end():], re.I))
        parsed.actor = _clean_actor(target_sentence[: modal_match.start()])
        after = target_sentence[modal_match.end():].split()
        _parse_predicate(parsed, after)
        parsed.actor_kind = _actor_kind(parsed.actor, parsed.passive)
    else:
        # Declarative present tense: "The system sends a confirmation email."
        tokens = target_sentence.split()
        for index, token in enumerate(tokens[1:9], start=1):
            bare = token.strip(",.;:").lower()
            if bare.endswith("s") and lemma(bare) in ACTION_VERBS and bare not in {"users", "is", "has", "this", "always"}:
                parsed.actor = _clean_actor(" ".join(tokens[:index]))
                parsed.action = lemma(bare)
                parsed.action_phrase = token.strip(",.;:")
                parsed.object = _take_object(tokens[index + 1:])
                break
        parsed.actor_kind = _actor_kind(parsed.actor, False)

    if parsed.action:
        _coordinated(parsed, target_sentence)

    for match in TRIGGER_RE.finditer(text):
        clause = normalize_space(match.group(0)).strip(" ,")
        if NOT_REAL_TRIGGERS.match(clause) or len(clause.split()) < 2:
            continue
        parsed.conditions.append(clause)
    schedule = re.search(SCHEDULE_PATTERN, text, re.I)
    parsed.schedule = schedule.group(0) if schedule else None

    parsed.measures, parsed.bare_numbers = _measures(text)
    known = {m.text for m in parsed.measures}
    parsed.measures += [m for m in _currency_measures(text) if not any(m.text in k for k in known)]
    parsed.references = list(dict.fromkeys(
        (m.group(1) or m.group(2)).upper().replace(" ", "-") if m.group(1) else m.group(2).lower()
        for m in REFERENCE_RE.finditer(text)
    ))
    return parsed


def _parse_predicate(parsed: ParsedRequirement, after: list[str]) -> None:
    tokens = [t for t in after]
    i = 0
    # Skip "not", adverbs, and "be able to".
    while i < len(tokens):
        bare = tokens[i].strip(",.;:").lower()
        if bare == "be" and i + 2 < len(tokens) and tokens[i + 1].lower() == "able" and tokens[i + 2].lower() == "to":
            i += 3
            continue
        if bare in VERB_FILLERS and bare != "be":
            i += 1
            continue
        if bare.endswith("ly") and bare not in ACTION_VERBS and len(bare) > 4:
            i += 1
            continue
        break
    if i >= len(tokens):
        return
    first = tokens[i].strip(",.;:").lower()
    if first in {"be", "been", "being", "get"}:
        nxt = tokens[i + 1].strip(",.;:").lower() if i + 1 < len(tokens) else ""
        if nxt and _is_participle(nxt):
            parsed.passive = True
            parsed.action = lemma(nxt)
            parsed.action_phrase = f"{first} {nxt}"
            by = None
            rest = tokens[i + 2:]
            for j, tok in enumerate(rest):
                if tok.lower() == "by" and j + 1 < len(rest):
                    by = _take_object(rest[j + 1:])
                    break
            parsed.object = parsed.actor
            if by:
                parsed.secondary_actor = by
            return
        predicate = []
        for tok in tokens[i + 1:i + 6]:
            if re.search(r"\d", tok) or tok.strip(",.;:").lower() in OBJECT_BOUNDARY - {"and", "or"}:
                break
            predicate.append(tok.strip(",.;:"))
        parsed.state_predicate = " ".join(predicate) or None
        parsed.action = "be"
        parsed.action_phrase = f"be {parsed.state_predicate or ''}".strip()
        parsed.object = parsed.state_predicate
        return
    if first in {"allow", "allows", "enable", "enables", "permit", "permits", "let", "lets"}:
        rest = tokens[i + 1:]
        for j, tok in enumerate(rest):
            if tok.lower() == "to" and j + 1 < len(rest):
                parsed.secondary_actor = " ".join(t.strip(",.;:") for t in rest[:j]) or None
                verb_tokens = rest[j + 1:]
                k = 0
                while k < len(verb_tokens) and verb_tokens[k].strip(",.;:").lower() in VERB_FILLERS:
                    k += 1
                if k < len(verb_tokens):
                    parsed.action = lemma(verb_tokens[k].strip(",.;:"))
                    parsed.action_phrase = verb_tokens[k].strip(",.;:")
                    parsed.object = _take_object(_skip_verb_chain(verb_tokens[k + 1:]))
                return
    if first in {"provide", "provides", "offer", "offers", "include", "includes", "have", "has"}:
        rest = tokens[i + 1:]
        lowered = [t.strip(",.;:").lower() for t in rest]
        for j, tok in enumerate(lowered[:5]):
            if tok in PROVIDE_NOUNS and j + 2 < len(rest) and lowered[j + 1] in {"to", "for"}:
                verb = rest[j + 2].strip(",.;:")
                parsed.action = lemma(verb)
                parsed.action_phrase = verb
                parsed.object = _take_object(rest[j + 3:])
                if parsed.secondary_actor is None:
                    parsed.secondary_actor = None
                return
    parsed.action = lemma(first)
    parsed.action_phrase = tokens[i].strip(",.;:")
    parsed.object = _take_object(_skip_verb_chain(tokens[i + 1:]))


def _skip_verb_chain(tokens: list[str]) -> list[str]:
    """Skip ", edit and delete" after the main verb so the object is found."""
    i = 0
    while i < len(tokens):
        bare = tokens[i].strip(",.;:").lower()
        if bare in {"and", "or", "and/or"} and i + 1 < len(tokens) and lemma(tokens[i + 1].strip(",.;:")) in ACTION_VERBS:
            i += 1
            continue
        if lemma(bare) in ACTION_VERBS and (tokens[i].endswith(",") or (i + 1 < len(tokens) and tokens[i + 1].lower() in {"and", "or", "and/or"})):
            i += 1
            continue
        if i > 0 and lemma(bare) in ACTION_VERBS and tokens[i - 1].strip(",").lower() in {"and", "or", "and/or"}:
            i += 1
            continue
        break
    return tokens[i:] if i < len(tokens) else tokens


def _coordinated(parsed: ParsedRequirement, sentence: str) -> None:
    """Find additional verbs joined to the main action ("create, edit and delete")."""
    lower = sentence.lower()
    anchor = lower.find((parsed.action_phrase or "").lower())
    tail = lower[anchor:] if anchor >= 0 else lower
    found = []
    for match in re.finditer(r"(?:,|\band\b|\bor\b|\bas well as\b)\s+(?:also\s+)?(?:to\s+)?([a-z]+)", tail):
        word = match.group(1)
        base = lemma(word)
        if base in ACTION_VERBS and base != parsed.action and word not in {"data", "status", "records"}:
            # Avoid nouns that are also verbs when preceded by an article ("and the report").
            found.append(base)
    parsed.coordinated_actions = list(dict.fromkeys(found))
