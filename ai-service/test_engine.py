"""Tests for the local SRS analysis engine and API.

Run from ai-service:  python -m unittest -v
"""
import os
import unittest

os.environ.setdefault("SRS_API_KEY", "test-internal-key")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from srs_engine import analyze_batch, analyze_single  # noqa: E402

main.SRS_API_KEY = "test-internal-key"
client = TestClient(main.app)
HEADERS = {"x-api-key": "test-internal-key"}


def codes(analysis):
    return {f["code"] for f in analysis["detailed_findings"]}


class RequirementAnalysisTests(unittest.TestCase):
    def test_good_functional_requirement_scores_well(self):
        a = analyze_single("FR-1: When a registered user submits the login form with a valid email and password, the system "
                           "shall authenticate the user and display the dashboard within 2 seconds. If the credentials are "
                           "invalid, the system shall display an error message.")
        self.assertEqual(a["classification"], "Functional")
        self.assertGreaterEqual(a["quality_score"], 80)
        self.assertEqual(a["status"], "Good")
        self.assertTrue(a["strengths"])
        self.assertEqual(a["structure"]["inline_id"], "FR-1")

    def test_vague_requirement_detected_with_evidence(self):
        a = analyze_single("The application should be fast and user-friendly.")
        vague = [f for f in a["detailed_findings"] if f["code"] == "VAGUE_TERM"]
        self.assertEqual({f["evidence"] for f in vague}, {"fast", "user-friendly"})
        self.assertIn("MISSING_PERFORMANCE_THRESHOLD", codes(a))
        self.assertLess(a["quality_score"], 60)
        self.assertIn("[TBD", a["improved_requirement"])

    def test_incomplete_requirement(self):
        a = analyze_single("Users shall be able to register.")
        self.assertTrue({"MISSING_INPUTS", "MISSING_POSTCONDITION", "MISSING_EXCEPTION_HANDLING"} <= codes(a))
        self.assertLess(a["quality_score"], 80)

    def test_ambiguous_pronoun_actor(self):
        a = analyze_single("It must be secure.")
        self.assertIn("MISSING_ACTOR", codes(a))
        self.assertIn("MISSING_SECURITY_CONSTRAINT", codes(a))
        self.assertEqual(a["status"], "Poor")
        self.assertEqual(a["priority"], "Critical")

    def test_compound_requirement_is_non_atomic_and_split(self):
        a = analyze_single("The system shall create invoices. The system shall email invoices to customers and shall archive them monthly.")
        self.assertIn("NON_ATOMIC", codes(a))
        self.assertIn("(1)", a["improved_requirement"])

    def test_non_functional_classification_and_measurable(self):
        a = analyze_single("The system shall be available 99.9% of the time per calendar month, excluding planned maintenance.")
        self.assertEqual(a["classification"], "Non-Functional")
        self.assertIn("Availability", a["categories"])
        self.assertNotIn("MISSING_MEASURABLE_TARGET", codes(a))

    def test_unmeasurable_availability(self):
        a = analyze_single("The system shall be highly available.")
        self.assertIn("MISSING_MEASURABLE_TARGET", codes(a))

    def test_security_requirement_missing_authorization(self):
        a = analyze_single("The system shall allow users to delete customer records.")
        self.assertIn("MISSING_AUTHORIZATION", codes(a))

    def test_performance_requirement_with_threshold(self):
        a = analyze_single("The system shall display search results within 2 seconds for up to 1,000 concurrent users.")
        self.assertNotIn("MISSING_PERFORMANCE_THRESHOLD", codes(a))
        families = {m["family"] for m in a["structure"]["measures"]}
        self.assertEqual(families, {"time", "count"})
        self.assertTrue(any("1000" in t or "1,000" in t for t in a["test_scenarios"]["boundary"]))

    def test_missing_acceptance_criteria_and_trigger(self):
        a = analyze_single("The system shall generate reports.")
        self.assertIn("UNCLEAR_TRIGGER", codes(a))
        self.assertIn("MISSING_OUTPUTS", codes(a))
        self.assertTrue(a["acceptance_criteria"])

    def test_unrealistic_commitment(self):
        a = analyze_single("The system shall never fail and shall have zero downtime.")
        self.assertIn("UNREALISTIC", codes(a))

    def test_user_story(self):
        a = analyze_single("As a librarian, I want to search books by title so that I can find them quickly.")
        self.assertEqual(a["classification"], "User Story")
        self.assertNotIn("MISSING_PERFORMANCE_THRESHOLD", codes(a))

    def test_score_is_explainable(self):
        a = analyze_single("The system shall support various file formats such as PDF, DOCX, etc.")
        deducted = sum(d["points"] for row in a["score_breakdown"] for d in row["deductions"])
        self.assertGreater(deducted, 0)
        for row in a["score_breakdown"]:
            self.assertEqual(row["score"], max(0, 100 - sum(d["points"] for d in row["deductions"])))
        for f in a["detailed_findings"]:
            self.assertTrue(f["evidence"] and f["why_it_matters"] and f["recommendation"])


class DocumentAnalysisTests(unittest.TestCase):
    SRS = [
        {"text": "The system shall allow users to register with an email address and password.", "requirement_id": "FR-1"},
        {"text": "Users shall be able to log in with their email and password.", "requirement_id": "FR-2"},
        {"text": "The system shall allow users to sign in using their email and password.", "requirement_id": "FR-3"},
        {"text": "Passwords shall contain at least 8 characters.", "requirement_id": "FR-4"},
        {"text": "Passwords shall contain at least 12 characters.", "requirement_id": "FR-5"},
        {"text": "Administrators shall be able to export user data.", "requirement_id": "FR-6"},
        {"text": "Administrators shall not be able to export user data.", "requirement_id": "FR-7"},
        {"text": "Logged-in users shall be able to view their order history, as described in FR-99.", "requirement_id": "FR-8"},
        {"text": "The system shall process payments.", "requirement_id": "FR-9"},
    ]

    @classmethod
    def setUpClass(cls):
        cls.result = analyze_batch(cls.SRS, "Shop")
        cls.report = cls.result["document_report"]
        cls.findings = cls.report["project_findings"]

    def test_duplicate_detection(self):
        pairs = [set(d["requirements"]) for d in self.findings["duplicates"]]
        self.assertIn({"FR-2", "FR-3"}, pairs)

    def test_contradiction_detection(self):
        pairs = {frozenset(c["requirements"]): c for c in self.findings["contradictions"]}
        self.assertIn(frozenset({"FR-4", "FR-5"}), pairs)
        self.assertEqual(pairs[frozenset({"FR-4", "FR-5"})]["type"], "threshold")
        self.assertIn(frozenset({"FR-6", "FR-7"}), pairs)
        self.assertNotIn(frozenset({"FR-1", "FR-9"}), pairs)

    def test_contradiction_lowers_consistency(self):
        fr4 = next(a for a in self.result["analyses"] if a["requirement_id"] == "FR-4")
        self.assertLess(fr4["dimension_scores"]["consistency"], 100)
        self.assertTrue(any(x["type"] == "POSSIBLE_CONTRADICTION" for x in fr4["cross_references"]))

    def test_terminology_and_broken_reference(self):
        concepts = {t["concept"] for t in self.findings["terminology"]}
        self.assertIn("log in", concepts)
        self.assertEqual(self.findings["traceability"]["broken_references"][0]["reference"], "FR-99")

    def test_dependencies_and_missing_requirements(self):
        deps = {(d["from"], d["to"]) for d in self.findings["dependencies"]}
        self.assertTrue(any(f == "FR-8" for f, _ in deps))
        missing = {m["missing"] for m in self.findings["missing_requirements"]}
        self.assertIn("Logout", missing)
        self.assertIn("Refund / cancellation", missing)

    def test_report_sections(self):
        summary = self.report["executive_summary"]
        self.assertEqual(summary["total_requirements"], len(self.SRS))
        self.assertEqual(summary["good"] + summary["needs_improvement"] + summary["poor"], len(self.SRS))
        self.assertIn(summary["risk_verdict"]["level"], {"Low", "Moderate", "High"})
        self.assertTrue(self.report["improvement_plan"])
        self.assertFalse(self.report["engine"]["external_ai_services"])

    def test_generated_ids_flag_traceability(self):
        result = analyze_batch([{"text": "The system shall log all failed login attempts."}])
        self.assertEqual(result["analyses"][0]["requirement_id"], "REQ-001")
        self.assertIn("REQ-001", result["document_report"]["project_findings"]["traceability"]["generated_ids"])


class ApiTests(unittest.TestCase):
    def test_health_has_no_external_provider(self):
        body = client.get("/health").json()
        self.assertEqual(body["status"], "ok")
        self.assertFalse(body["external_provider_required"])
        self.assertFalse(body["external_ai_services"])
        self.assertEqual(body["backend"], "tfidf")

    def test_auth_required(self):
        self.assertEqual(client.post("/analyze", json={"requirement": "x"}).status_code, 401)

    def test_single_analysis_backward_compatible(self):
        r = client.post("/analyze", json={"requirement": "The system shall display the account balance within 2 seconds."}, headers=HEADERS)
        self.assertEqual(r.status_code, 200)
        a = r.json()["analysis"]
        for field in ("quality_score", "classification", "clarity", "completeness", "testability", "suggested_rewrite",
                      "explanation", "ambiguities", "missing_information", "issues", "expert_review"):
            self.assertIn(field, a)

    def test_batch_accepts_spring_payload(self):
        payload = {"requirements": [
            {"requirement": "The system shall display the account balance within 2 seconds.", "source": "Bank", "section_number": "REQ-001"},
            {"requirement": "The administrator shall create a user account.", "source": "Bank", "section_number": "REQ-002"},
        ]}
        r = client.post("/analyze-batch", json=payload, headers=HEADERS)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["total_requirements"], 2)
        self.assertEqual([a["requirement_id"] for a in body["analyses"]], ["REQ-001", "REQ-002"])
        self.assertEqual([a["requirement_number"] for a in body["analyses"]], [1, 2])
        self.assertIn("document_report", body)

    def test_request_validation(self):
        self.assertEqual(client.post("/analyze-batch", json={"requirements": []}, headers=HEADERS).status_code, 422)
        self.assertEqual(client.post("/analyze-batch", json={"requirements": ["  "]}, headers=HEADERS).status_code, 422)
        self.assertEqual(client.post("/analyze-batch", json={"requirements": [123]}, headers=HEADERS).status_code, 422)
        too_many = {"requirements": ["The system shall log events."] * (main.MAX_BATCH_REQUIREMENTS + 1)}
        self.assertEqual(client.post("/analyze-batch", json=too_many, headers=HEADERS).status_code, 422)
        self.assertEqual(client.post("/analyze", json={"requirement": ""}, headers=HEADERS).status_code, 400)
        self.assertEqual(client.post("/analyze", json={"requirement": "x" * (main.MAX_REQUIREMENT_CHARS + 1)}, headers=HEADERS).status_code, 413)

    def test_large_batch_performance(self):
        import time
        reqs = [f"The system shall allow users to create report type {i} within {i % 9 + 1} seconds." for i in range(300)]
        start = time.time()
        r = client.post("/analyze-batch", json={"requirements": reqs}, headers=HEADERS)
        self.assertEqual(r.status_code, 200)
        self.assertLess(time.time() - start, 30)


if __name__ == "__main__":
    unittest.main()
