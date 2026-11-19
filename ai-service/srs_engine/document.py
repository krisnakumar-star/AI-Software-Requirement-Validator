"""Document-level SRS analysis and report generation.

Duplicates, possible contradictions, dependencies, terminology, coverage,
missing requirements, traceability, risks, and an improvement plan. Every
finding lists the requirement IDs involved and the evidence used.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from .analyzer import RISK_CATEGORIES, SEVERITY_RANK, rescore
from .lexicon import ERROR_TERMS
from .similarity import Similarity
from .text import any_term, content_terms, terminology_variants, truncate, unique

CREATE_VERBS = {"create", "add", "register", "upload", "submit", "place", "generate", "open", "book", "post",
                "enroll", "import", "record", "reserve", "order", "publish"}
USE_VERBS = {"view", "update", "edit", "delete", "remove", "login", "search", "approve", "cancel", "pay",
             "download", "export", "checkout", "track", "review", "comment", "rate", "print", "modify",
             "share", "archive", "restore", "refund", "reject"}
ANTONYMS = [
    ({"allow", "permit", "enable", "grant"}, {"deny", "prevent", "block", "prohibit", "disable", "revoke"}),
    ({"mandatory", "required", "compulsory"}, {"optional"}),
    ({"encrypt", "encrypted", "hash", "hashed"}, {"plain text", "plaintext", "unencrypted", "clear text"}),
    ({"automatic", "automatically"}, {"manual", "manually"}),
    ({"public"}, {"private"}),
    ({"permanently delete", "permanently deleted", "purge"}, {"retain", "retained", "archive", "soft delete"}),
]
QUALIFIERS = re.compile(r"\b(own|other|others'?|unless|except|only|their own|not their)\b", re.I)


def _terms(text: str | None) -> set[str]:
    return set(content_terms(text or ""))


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _excerpt(item) -> str:
    return truncate(item["text"], 110)


def _finding(code, title, severity, dimension, message, evidence, recommendation, related):
    return {"code": code, "title": title, "severity": severity, "dimension": dimension,
            "secondary_dimension": None, "message": message, "evidence": evidence,
            "why_it_matters": "Detected by comparing this requirement with the rest of the SRS.",
            "recommendation": recommendation, "question": None, "related_requirements": related}


def analyze_document(items: list[dict]) -> dict:
    """items: [{id, text, analysis}] in SRS order. Mutates analyses with cross-references and rescoring."""
    n = len(items)
    sim = Similarity([it["text"] for it in items])
    s = [it["analysis"]["structure"] for it in items]
    obj_terms = [_terms(x.get("object")) for x in s]
    ids = [it["id"] for it in items]
    extra = defaultdict(list)
    duplicates, contradictions, dependencies = [], [], []
    lowers = [it["text"].lower() for it in items]
    antonym_hits = [[(bool(any_term(t, left)), bool(any_term(t, right))) for left, right in ANTONYMS] for t in lowers]
    has_only = ["only" in t for t in lowers]
    qualified_flags = [bool(QUALIFIERS.search(t)) for t in lowers]
    per_req_cap = defaultdict(int)

    for i in range(n):
        for j in range(i + 1, n):
            score = sim.score(i, j)
            same_action = s[i].get("action") and s[i].get("action") == s[j].get("action")
            obj_overlap = _jaccard(obj_terms[i], obj_terms[j])
            pair = [ids[i], ids[j]]

            if score >= 0.80 or (score >= 0.6 and same_action and obj_overlap >= 0.5):
                kind = "duplicate" if score >= 0.80 else "possible overlap"
                duplicates.append({
                    "type": kind, "requirements": pair, "similarity": round(score, 2),
                    "shared_terms": sim.shared_terms(i, j)[:8],
                    "explanation": f"{ids[i]} and {ids[j]} share most key terms (similarity {score:.2f})"
                                   + (" and the same action/object" if same_action else "") + ".",
                    "recommendation": "Merge them if they state the same obligation; otherwise make the difference (actor, condition, scope) explicit.",
                    "evidence": [_excerpt(items[i]), _excerpt(items[j])],
                })
                for a, b in ((i, j), (j, i)):
                    per_req_cap[a] += 1
                    if per_req_cap[a] > 5:
                        continue
                    extra[a].append(_finding("DUPLICATE_REQUIREMENT", "Possible duplicate", "medium" if kind == "duplicate" else "low",
                                             "consistency", f"This requirement {'duplicates' if kind == 'duplicate' else 'overlaps with'} {ids[b]} (similarity {score:.2f}).",
                                             _excerpt(items[b]), "Merge or differentiate the two requirements.", [ids[b]]))

            topic = score >= 0.35 or obj_overlap >= 0.5
            if not topic:
                continue
            reasons = []
            ti, tj = lowers[i], lowers[j]
            neg_i = s[i].get("obligation") == "prohibition"
            neg_j = s[j].get("obligation") == "prohibition"
            if same_action and neg_i != neg_j and obj_overlap >= 0.5:
                reasons.append(("polarity", f"one requires '{s[i]['action']}' and the other prohibits it on the same subject"))
            mi, mj = s[i].get("measures") or [], s[j].get("measures") or []
            for a in mi:
                for b in mj:
                    if a["family"] == b["family"] and a["value"] != b["value"] and (same_action or obj_overlap >= 0.5) \
                            and (a.get("comparator") or "") == (b.get("comparator") or "") and a["unit"].rstrip("s") == b["unit"].rstrip("s"):
                        reasons.append(("threshold", f"different limits for the same measure: '{a['text']}' vs '{b['text']}'"))
            if same_action and obj_overlap >= 0.5 and {s[i].get("obligation"), s[j].get("obligation")} >= {"mandatory", "optional"}:
                reasons.append(("obligation", "the same behaviour is mandatory in one and optional in the other"))
            for k_ant, (left, right) in enumerate(ANTONYMS):
                li, ri = antonym_hits[i][k_ant]
                lj, rj = antonym_hits[j][k_ant]
                if (li and rj) or (ri and lj):
                    if obj_overlap >= 0.5 or score >= 0.5:
                        reasons.append(("opposing terms", f"opposing terms on a similar subject ({'/'.join(sorted(left))[:30]} vs {'/'.join(sorted(right))[:30]})"))
                    break
            if same_action and obj_overlap >= 0.5 and (has_only[i] != has_only[j]) and s[i].get("actor") != s[j].get("actor"):
                reasons.append(("access", "one restricts the action to a specific role while the other grants it to a different actor"))
            if not reasons:
                continue
            qualified = qualified_flags[i] or qualified_flags[j]
            severity = "low" if qualified and reasons[0][0] in {"polarity", "access"} else "high" if reasons[0][0] in {"polarity", "threshold"} else "medium"
            text = "; ".join(r[1] for r in reasons)
            contradictions.append({
                "type": reasons[0][0], "requirements": pair, "severity": severity,
                "explanation": f"Possible contradiction between {ids[i]} and {ids[j]}: {text}."
                               + (" Qualifiers (own/other/only/unless) suggest the scopes may differ — confirm." if qualified else ""),
                "recommendation": "Confirm the intended rule with the requirement owner and align or explicitly scope both requirements.",
                "evidence": [_excerpt(items[i]), _excerpt(items[j])],
            })
            for a, b in ((i, j), (j, i)):
                extra[a].append(_finding("POSSIBLE_CONTRADICTION", "Possible contradiction", severity, "consistency",
                                         f"May conflict with {ids[b]}: {text}.", _excerpt(items[b]),
                                         "Resolve the conflict with the requirement owner.", [ids[b]]))

    # Dependencies: explicit references and inferred entity lifecycle.
    id_lookup = {i_.upper().replace(" ", "-"): k for k, i_ in enumerate(ids)}
    broken = []
    for k, item in enumerate(items):
        for ref in s[k].get("references") or []:
            if ref.lower().startswith("section"):
                continue
            target = id_lookup.get(ref.upper())
            if target is None:
                broken.append({"requirement": ids[k], "reference": ref})
                extra[k].append(_finding("BROKEN_REFERENCE", "Reference to unknown requirement", "medium", "traceability",
                                         f"References '{ref}', which is not in this SRS.", ref,
                                         "Correct the reference or add the missing requirement.", []))
            elif target != k:
                dependencies.append({"from": ids[k], "to": ids[target], "type": "explicit reference",
                                     "explanation": f"{ids[k]} explicitly references {ids[target]}."})
    creators = defaultdict(list)
    for k, x in enumerate(s):
        if x.get("action") in CREATE_VERBS:
            for t in obj_terms[k] or ({"account"} if x.get("action") == "register" else set()):
                creators[t].append(k)
        if x.get("action") == "register":
            creators["account"].append(k)
    login_reqs = [k for k, x in enumerate(s) if x.get("action") in {"login", "authenticate"} or re.search(r"\blog(s)? ?in\b|sign(s)? ?in", items[k]["text"].lower())]
    seen = set()
    for k, x in enumerate(s):
        uses = set(obj_terms[k]) if x.get("action") in USE_VERBS else set()
        if x.get("action") in {"login", "authenticate"}:
            uses |= {"account"}
        for t in uses:
            for c in creators.get(t, []):
                if c != k and (k, c) not in seen:
                    seen.add((k, c))
                    dependencies.append({"from": ids[k], "to": ids[c], "type": "inferred (data lifecycle)",
                                         "explanation": f"{ids[k]} uses '{t}', which is created in {ids[c]}."})
        if re.search(r"\b(logged[- ]in|authenticated|signed[- ]in)\b", items[k]["text"].lower()):
            for c in login_reqs:
                if c != k and (k, c) not in seen:
                    seen.add((k, c))
                    dependencies.append({"from": ids[k], "to": ids[c], "type": "inferred (precondition)",
                                         "explanation": f"{ids[k]} requires an authenticated user, provided by {ids[c]}."})

    # Terminology across the document.
    usage = defaultdict(lambda: defaultdict(list))
    for k, it in enumerate(items):
        for canon, variants in terminology_variants(it["text"]).items():
            for v in variants:
                usage[canon][v].append(ids[k])
    terminology = []
    for canon, variants in usage.items():
        if len(variants) >= 2:
            role_group = canon in {"user"}
            terminology.append({
                "concept": canon, "variants": {v: r[:8] for v, r in variants.items()},
                "severity": "low" if role_group else "medium",
                "explanation": f"The SRS uses {', '.join(repr(v) for v in variants)} for what may be the same concept."
                               + (" Confirm whether these are different roles." if role_group else ""),
                "recommendation": f"Choose one term (e.g. '{canon}'), define it in the glossary and use it consistently.",
            })
            if not role_group:
                for v, rids in variants.items():
                    for rid in rids:
                        extra[ids.index(rid)].append(_finding("INCONSISTENT_TERMINOLOGY", "Inconsistent terminology across SRS", "low",
                                                              "consistency", f"Uses '{v}' while other requirements use {', '.join(x for x in variants if x != v)}.",
                                                              v, f"Use one term consistently (e.g. '{canon}').", []))

    # Duplicate IDs.
    for rid, count in Counter(ids).items():
        if count > 1:
            for k in [k for k, x in enumerate(ids) if x == rid]:
                extra[k].append(_finding("DUPLICATE_ID", "Duplicate requirement ID", "high", "traceability",
                                         f"The ID {rid} is used by {count} requirements.", rid, "Assign unique IDs.", []))

    for k, fs in extra.items():
        unique_fs, keys = [], set()
        for f in fs:
            key = (f["code"], f["evidence"])
            if key not in keys:
                keys.add(key)
                unique_fs.append(f)
        items[k]["analysis"]["cross_references"] = [
            {"type": f["code"], "with": f["related_requirements"], "message": f["message"], "severity": f["severity"]} for f in unique_fs]
        rescore(items[k]["analysis"], unique_fs)

    return _report(items, duplicates, contradictions, dependencies, terminology, broken, sim.backend)


MISSING_RULES = [
    (r"\blog ?in|sign ?in|authenticat", r"\blog ?out|sign ?out", "Logout", "Login is specified but logging out is not."),
    (r"\blog ?in|sign ?in|password", r"reset password|password reset|forgot password|password recovery|recover password", "Password reset / recovery", "Users can log in but no requirement covers forgotten passwords."),
    (r"\blog ?in|sign ?in", r"lock|failed (login )?attempts|brute", "Failed-login handling / account lockout", "No requirement limits repeated failed login attempts."),
    (r"\bregist|sign ?up", r"verif|confirm(ation)? (email|link)|activation", "Account verification", "Registration is specified without verifying the user's identity or contact details."),
    (r"\bpay|payment|checkout", r"refund|cancel", "Refund / cancellation", "Payments are specified but refunds or cancellations are not."),
    (r"\bpay|payment|checkout", r"receipt|invoice|confirmation", "Payment confirmation / receipt", "No requirement states what the user receives after paying."),
    (r"\bupload", r"\b\d+\s*(kb|mb|gb)\b|file (size|type)|format", "Upload limits", "Uploads are specified without file size or type limits."),
    (r"\badmin|administrator|role", r"role|permission|privilege|access control", "Role and permission management", "Different roles exist but no requirement defines their permissions."),
    (r"\bnotif|email|sms|alert", r"opt[- ]?out|unsubscribe|preference", "Notification preferences", "Notifications are sent but users cannot manage or opt out of them."),
    (r"personal|email|phone|address|date of birth", r"privacy|consent|retention|gdpr|delete (my|their) (account|data)", "Personal-data handling", "Personal data is collected without privacy, consent or retention requirements."),
    (r"\bstore|save|database|record", r"backup|restore|recovery", "Backup and recovery", "Data is stored but backup and recovery are not specified."),
    (r"\badmin|delete|approve|payment", r"audit|log", "Audit logging", "Sensitive actions exist without audit-logging requirements."),
]


def _report(items, duplicates, contradictions, dependencies, terminology, broken, backend) -> dict:
    analyses = [it["analysis"] for it in items]
    ids = [it["id"] for it in items]
    n = len(items)
    all_text = " ".join(it["text"].lower() for it in items)
    status = Counter(a["status"] for a in analyses)
    primary = Counter(a["classification"] for a in analyses)
    categories = Counter(c for a in analyses for c in a["categories"])
    overall = round(sum(a["quality_score"] for a in analyses) / n)
    critical_ids = [a["requirement_id"] for a in analyses if a["priority"] == "Critical"]
    high_ids = [a["requirement_id"] for a in analyses if a["priority"] == "High"]
    finding_counts = Counter(f["title"] for a in analyses for f in a["detailed_findings"] if f["severity"] != "info")
    by_title = defaultdict(list)
    for a in analyses:
        for f in a["detailed_findings"]:
            by_title[f["title"]].append(a["requirement_id"])
    weaknesses = [{"issue": t, "count": c, "percent": round(100 * len(set(by_title[t])) / n),
                   "requirements": unique(by_title[t])[:8]} for t, c in finding_counts.most_common(6)]
    dims = {d: round(sum(a["dimension_scores"][d] for a in analyses) / n) for d in analyses[0]["dimension_scores"]}

    # Coverage
    nfr_present = {c for c in categories if c in {"Security", "Performance", "Availability", "Reliability", "Usability",
                                                  "Compatibility", "Maintainability", "Privacy", "Scalability"}}
    coverage_gaps = []
    if primary.get("Non-Functional", 0) == 0:
        coverage_gaps.append("No non-functional requirements (performance, security, usability, availability...) were found.")
    if "Security" not in nfr_present and re.search(r"log ?in|password|account|payment|personal", all_text):
        coverage_gaps.append("Accounts, payments or personal data are present but no security requirement exists.")
    if "Performance" not in nfr_present and n >= 5:
        coverage_gaps.append("No performance requirement (response time, throughput) is specified.")
    if not ({"Availability", "Reliability"} & nfr_present) and n >= 8:
        coverage_gaps.append("No availability or reliability requirement is specified.")
    if not any_term(all_text, ERROR_TERMS):
        coverage_gaps.append("No requirement describes error or exception handling.")

    missing_reqs = []
    for trigger, covered, name, why in MISSING_RULES:
        if re.search(trigger, all_text) and not re.search(covered, all_text):
            related = [ids[k] for k, it in enumerate(items) if re.search(trigger, it["text"].lower())][:6]
            missing_reqs.append({"missing": name, "reason": why, "related_requirements": related,
                                 "recommendation": f"Consider adding a requirement for: {name.lower()} (confirm with stakeholders)."})

    # Traceability
    generated = [a["requirement_id"] for a in analyses if any(f["code"] == "MISSING_ID" for f in a["detailed_findings"])]
    dup_ids = [rid for rid, c in Counter(ids).items() if c > 1]
    schemes = Counter(re.sub(r"[\d.\-_ ]+$", "", rid) for rid in ids)
    untestable = [a["requirement_id"] for a in analyses if any(f["code"] in {"NOT_TESTABLE", "MISSING_ACCEPTANCE_CRITERIA"} for f in a["detailed_findings"])]
    depends = defaultdict(list)
    depended = defaultdict(list)
    for d in dependencies:
        depends[d["from"]].append(d["to"])
        depended[d["to"]].append(d["from"])
    matrix = [{"id": a["requirement_id"], "section": a.get("section"), "type": a["classification"],
               "priority": a["priority"], "score": a["quality_score"], "depends_on": unique(depends[a["requirement_id"]]),
               "required_by": unique(depended[a["requirement_id"]]),
               "related": unique(r for x in a["cross_references"] for r in x["with"])} for a in analyses]
    traceability = {
        "generated_ids": generated, "duplicate_ids": dup_ids, "broken_references": broken,
        "mixed_id_schemes": len(schemes) > 1 and not generated, "id_schemes": dict(schemes),
        "without_section": [a["requirement_id"] for a in analyses if not a.get("section")][:20] if any(a.get("section") for a in analyses) else [],
        "lacking_acceptance_criteria": untestable, "matrix": matrix,
    }

    sec_gaps = [{"requirement": a["requirement_id"], "issue": f["message"]} for a in analyses for f in a["detailed_findings"]
                if f["code"] in {"MISSING_SECURITY_CONSTRAINT", "MISSING_AUTHORIZATION"}]
    perf_gaps = [{"requirement": a["requirement_id"], "issue": f["message"]} for a in analyses for f in a["detailed_findings"]
                 if f["code"] in {"MISSING_PERFORMANCE_THRESHOLD", "MISSING_MEASURABLE_TARGET"}]
    missing_info = defaultdict(list)
    for a in analyses:
        for f in a["detailed_findings"]:
            if f["code"].startswith("MISSING_") or f["code"] in {"INCOMPLETE", "UNCLEAR_TRIGGER", "INCOMPLETE_BUSINESS_RULE", "UNSPECIFIED_DATA_CONSTRAINTS"}:
                missing_info[f["title"]].append(a["requirement_id"])
    missing_info = [{"type": k, "requirements": unique(v)} for k, v in sorted(missing_info.items(), key=lambda kv: -len(kv[1]))]

    # Risks
    risks = []
    if contradictions:
        risks.append({"risk": "Contradictory requirements", "level": "High", "affected_requirements": unique(r for c in contradictions for r in c["requirements"]),
                      "impact": "Conflicting rules lead to rework and disputes at acceptance.", "mitigation": "Resolve each conflict with the requirement owner before design."})
    sensitive_poor = [a["requirement_id"] for a in analyses if set(a["categories"]) & RISK_CATEGORIES and a["status"] != "Good"]
    if sensitive_poor:
        risks.append({"risk": "Weak security / privacy / compliance requirements", "level": "High", "affected_requirements": sensitive_poor,
                      "impact": "Underspecified controls can cause vulnerabilities or compliance failures.", "mitigation": "Specify concrete controls and verification criteria."})
    if sec_gaps:
        risks.append({"risk": "Missing access-control or data-protection rules", "level": "High", "affected_requirements": unique(g["requirement"] for g in sec_gaps),
                      "impact": "Sensitive operations or data may be exposed.", "mitigation": "Add authorization and protection rules."})
    if untestable and len(untestable) / n >= 0.25:
        risks.append({"risk": "Many requirements are not verifiable", "level": "Medium", "affected_requirements": untestable,
                      "impact": "Acceptance becomes subjective; defects are found late.", "mitigation": "Add measurable Given/When/Then acceptance criteria."})
    for gap in coverage_gaps:
        risks.append({"risk": gap, "level": "Medium", "affected_requirements": [], "impact": "Important qualities may be missed in design and testing.",
                      "mitigation": "Elicit and add the missing requirement category."})
    dep_unknown = [a["requirement_id"] for a in analyses if any(f["code"] == "MISSING_DEPENDENCY" for f in a["detailed_findings"])]
    if dep_unknown:
        risks.append({"risk": "Unidentified external dependencies", "level": "Medium", "affected_requirements": dep_unknown,
                      "impact": "Integration effort and failure modes are unknown.", "mitigation": "Name each external system and its interface contract."})
    if broken or dup_ids:
        risks.append({"risk": "Traceability defects", "level": "Medium", "affected_requirements": unique([b["requirement"] for b in broken] + dup_ids),
                      "impact": "Changes cannot be traced reliably.", "mitigation": "Fix IDs and references."})

    poor_ratio = status.get("Poor", 0) / n
    if contradictions and any(c["severity"] == "high" for c in contradictions) or poor_ratio >= 0.4 or overall < 55:
        verdict = "High"
    elif poor_ratio >= 0.15 or critical_ids or overall < 75 or risks:
        verdict = "Moderate"
    else:
        verdict = "Low"
    verdict_reason = (f"Average quality {overall}/100; {status.get('Poor', 0)} poor requirement(s); "
                      f"{len(contradictions)} possible contradiction(s); {len(critical_ids)} critical-priority requirement(s).")
    risk_areas = unique([c for a in analyses if a["status"] != "Good" for c in a["categories"] if c not in {"Functional", "Unclassified"}])[:5]

    # Improvement plan
    plan = []

    def step(title, action, rids, why):
        if rids or not isinstance(rids, list):
            plan.append({"step": len(plan) + 1, "title": title, "action": action, "requirement_ids": unique(rids)[:15], "rationale": why})
    step("Resolve contradictions", "Confirm the intended rule for each conflicting pair and align the wording.",
         [r for c in contradictions for r in c["requirements"]], "Conflicts block design decisions.")
    step("Fix critical and high-priority requirements", "Address their high-severity findings first (see each requirement's problems).",
         critical_ids + high_ids, "These carry the most implementation and acceptance risk.")
    step("Close security and access-control gaps", "Add authorization rules and data-protection controls.",
         [g["requirement"] for g in sec_gaps], "Security gaps are expensive to fix after release.")
    step("Make quality requirements measurable", "Replace vague terms with metrics, thresholds, units and conditions.",
         [g["requirement"] for g in perf_gaps] + [a["requirement_id"] for a in analyses if any(f["code"] == "VAGUE_TERM" for f in a["detailed_findings"])],
         "Unmeasurable requirements cannot be accepted objectively.")
    step("Split compound requirements", "Give each obligation its own ID.",
         [a["requirement_id"] for a in analyses if any(f["code"] == "NON_ATOMIC" for f in a["detailed_findings"])], "Atomic requirements are traceable and testable.")
    step("Merge or differentiate duplicates", "Compare each pair and merge or clarify the difference.",
         [r for d in duplicates for r in d["requirements"]], "Duplicates drift apart over time.")
    if terminology:
        step("Unify terminology", "Create a glossary and use one term per concept.", unique(r for t in terminology for v in t["variants"].values() for r in v), "Synonyms create doubt about meaning.")
    if missing_reqs or coverage_gaps:
        plan.append({"step": len(plan) + 1, "title": "Add missing requirements", "action": "; ".join([m["missing"] for m in missing_reqs][:6] + coverage_gaps[:2]),
                     "requirement_ids": [], "rationale": "Gaps found by coverage analysis; confirm each with stakeholders."})
    step("Add acceptance criteria", "Write Given/When/Then criteria using the generated drafts as a starting point.", untestable, "Defines 'done' for each requirement.")
    step("Fix traceability", "Assign stable unique IDs and correct broken references.", generated + dup_ids + [b["requirement"] for b in broken], "Enables change and test traceability.")

    top_recs = [f"{p['title']}: {p['action']}" + (f" ({', '.join(p['requirement_ids'][:4])}{'…' if len(p['requirement_ids']) > 4 else ''})" if p["requirement_ids"] else "") for p in plan[:5]]
    narrative = (
        f"The SRS contains {n} requirement(s) with an average quality score of {overall}/100. "
        f"{status.get('Good', 0)} are good, {status.get('Needs Improvement', 0)} need improvement and {status.get('Poor', 0)} are poor. "
        + (f"The most common weaknesses are {', '.join(w['issue'].lower() for w in weaknesses[:3])}. " if weaknesses else "")
        + (f"{len(contradictions)} possible contradiction(s) and {len(duplicates)} duplicate/overlap pair(s) were found. " if contradictions or duplicates else "")
        + f"Overall risk is {verdict.lower()}."
    )

    return {
        "engine": {"name": "ReqValidator local SRS intelligence engine", "similarity_backend": backend,
                   "external_ai_services": False},
        "executive_summary": {
            "overall_score": overall, "overall_status": "Good" if overall >= 80 else "Needs Improvement" if overall >= 60 else "Poor",
            "total_requirements": n, "good": status.get("Good", 0), "needs_improvement": status.get("Needs Improvement", 0),
            "poor": status.get("Poor", 0), "critical_requirements": critical_ids, "high_priority_requirements": high_ids,
            "main_weaknesses": weaknesses, "main_risk_areas": risk_areas,
            "risk_verdict": {"level": verdict, "reason": verdict_reason}, "top_recommendations": top_recs, "narrative": narrative,
        },
        "quality_assessment": {
            "average_dimension_scores": dims, "status_distribution": dict(status),
            "severity_distribution": dict(Counter(f["severity"] for a in analyses for f in a["detailed_findings"])),
            "type_distribution": dict(primary), "category_distribution": dict(categories),
        },
        "project_findings": {
            "duplicates": duplicates, "contradictions": contradictions, "dependencies": dependencies,
            "terminology": terminology, "missing_information": missing_info, "missing_requirements": missing_reqs,
            "coverage": {"functional": primary.get("Functional", 0) + primary.get("User Story", 0) + primary.get("Business Rule", 0),
                         "non_functional": primary.get("Non-Functional", 0), "constraints": primary.get("Constraint", 0),
                         "categories_present": sorted(categories), "gaps": coverage_gaps},
            "security_gaps": sec_gaps, "performance_gaps": perf_gaps, "traceability": traceability,
        },
        "risks": risks,
        "priority_assessment": sorted(
            [{"id": a["requirement_id"], "priority": a["priority"], "score": a["quality_score"], "reason": a["priority_reason"]} for a in analyses],
            key=lambda r: ({"Critical": 0, "High": 1, "Medium": 2, "Low": 3}[r["priority"]], r["score"])),
        "improvement_plan": plan,
    }
