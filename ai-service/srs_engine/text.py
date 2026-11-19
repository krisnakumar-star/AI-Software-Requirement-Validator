"""Small, dependency-free NLP helpers: tokenizing, sentence splitting,
light stemming, and terminology canonicalization."""
from __future__ import annotations

import re
from functools import lru_cache

from .lexicon import STOPWORDS, SYNONYM_GROUPS

WORD_RE = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def words(text: str) -> list[str]:
    return WORD_RE.findall(str(text or "").lower())


def sentences(text: str) -> list[str]:
    # Avoid splitting on decimals ("99.9%"), abbreviations ("e.g."), and IDs ("REQ-1.2").
    protected = re.sub(r"\b(e\.g|i\.e|etc|vs|approx|no|fig|sec)\.", lambda m: m.group(0).replace(".", "§"), text, flags=re.I)
    parts = re.split(r"(?<=[.!?;])\s+(?=[A-Z0-9(\"'])", protected)
    return [p.replace("§", ".").strip() for p in parts if p.strip()]


@lru_cache(maxsize=8192)
def _rx(pattern: str, flags: int = 0) -> re.Pattern:
    return re.compile(pattern, flags)


def contains_phrase(text_lower: str, phrase: str) -> bool:
    """Whole-word phrase match; phrases ending in punctuation or partial stems match loosely."""
    phrase = phrase.lower()
    if not phrase[-1:].isalnum() or not phrase[:1].isalnum():
        return phrase in text_lower
    return _rx(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])").search(text_lower) is not None


def find_phrase(text: str, phrase: str) -> str | None:
    """Return the phrase as it appears in the original text (for evidence)."""
    match = _rx(r"(?<![A-Za-z0-9])" + re.escape(phrase) + r"(?![A-Za-z0-9])", re.I).search(text)
    return match.group(0) if match else None


def contains_stem(text_lower: str, stem: str) -> bool:
    """Prefix match for word stems such as 'encrypt' (encrypt/encrypted/encryption)."""
    return _rx(r"(?<![a-z0-9])" + re.escape(stem.lower())).search(text_lower) is not None


def any_term(text_lower: str, terms) -> list[str]:
    """Terms ending in punctuation/space match as substrings, short terms as whole
    words, and longer terms as word-prefix stems (encrypt -> encrypted)."""
    hits = []
    for term in terms:
        t = term.lower()
        if not t.strip():
            continue
        if t.endswith(" ") or not t[-1].isalnum() or not t[0].isalnum():
            ok = t in text_lower
        elif len(t) <= 3:
            ok = contains_phrase(text_lower, t)
        else:
            ok = contains_stem(text_lower, t)
        if ok:
            hits.append(term.strip())
    return hits


@lru_cache(maxsize=4096)
def stem(word: str) -> str:
    """A light suffix stripper (Porter-inspired) adequate for similarity matching."""
    w = word.lower()
    if len(w) <= 3:
        return w
    for suffix, repl in (("ational", "ate"), ("ization", "ize"), ("isation", "ize"), ("fulness", "ful"),
                         ("ousness", "ous"), ("iveness", "ive"), ("ements", "e"), ("ement", "e"),
                         ("ations", "ate"), ("ation", "ate"), ("ments", ""), ("ment", ""), ("ities", ""),
                         ("ity", ""), ("ness", ""), ("ingly", ""), ("edly", ""), ("ing", ""), ("ies", "y"),
                         ("ied", "y"), ("ed", ""), ("ers", ""), ("er", ""), ("es", ""), ("s", "")):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            w = w[: -len(suffix)] + repl
            break
    if len(w) > 4 and w[-1] == w[-2] and w[-1] not in "aeiouls":
        w = w[:-1]
    if w.endswith("e") and len(w) > 4:
        w = w[:-1]
    return w


_VARIANT_TO_CANON: list[tuple[str, str]] = sorted(
    ((variant, canon) for canon, variants in SYNONYM_GROUPS.items() for variant in variants),
    key=lambda item: -len(item[0]),
)


def canonicalize(text: str) -> str:
    """Map terminology variants to one canonical term (used for similarity only)."""
    lower = " " + normalize_space(text).lower() + " "
    for variant, canon in _VARIANT_TO_CANON:
        lower = _rx(r"(?<![a-z0-9])" + re.escape(variant) + r"(?![a-z0-9])").sub(canon, lower)
    return lower.strip()


def content_terms(text: str) -> list[str]:
    return [stem(w) for w in words(canonicalize(text)) if w not in STOPWORDS and len(w) > 2 and not w.isdigit()]


def terminology_variants(text: str) -> dict[str, set[str]]:
    """Which variant of each synonym group appears in the text."""
    lower = " " + normalize_space(text).lower() + " "
    found: dict[str, set[str]] = {}
    for canon, variants in SYNONYM_GROUPS.items():
        # Prefer the longest matching variant so 'end user' does not also count as 'user'.
        masked = lower
        for variant in sorted(variants, key=len, reverse=True):
            pattern = _rx(r"(?<![a-z0-9])" + re.escape(variant) + r"s?(?![a-z0-9])")
            if pattern.search(masked):
                found.setdefault(canon, set()).add(variant)
                masked = pattern.sub(" ", masked)
    return found


def truncate(text: str, limit: int) -> str:
    text = normalize_space(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def unique(items):
    return list(dict.fromkeys(item for item in items if item))
