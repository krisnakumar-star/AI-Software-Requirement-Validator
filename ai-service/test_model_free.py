"""Regression tests for the provider-free SRS analysis service.

Run from the ai-service directory with:
    python -m unittest test_model_free.py
"""
import asyncio
import unittest

from main import AnalyzeRequest, BatchAnalyzeRequest, analyze, analyze_batch, health, home


class ModelFreeAnalyzerTests(unittest.TestCase):
    def test_health_identifies_provider_free_engine(self):
        result = health()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["provider"], "built-in NLP analysis engine")
        self.assertEqual(result["mode"], "model-free")
        self.assertFalse(result["external_provider_required"])
        self.assertEqual(result["version"], "9.1.0")

    def test_single_analysis_does_not_require_external_provider(self):
        result = asyncio.run(analyze(
            AnalyzeRequest(requirement="The system shall display the account balance within 2 seconds."),
            None,
        ))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["provider"], "built-in NLP analysis engine")
        self.assertIsNone(result["model"])
        self.assertIn("quality_score", result["analysis"])
        self.assertIn("expert_review", result["analysis"])

    def test_batch_analysis_returns_backend_compatible_results(self):
        request = BatchAnalyzeRequest(requirements=[
            "The system shall display the account balance within 2 seconds.",
            "The administrator shall create a user account.",
        ])
        result = asyncio.run(analyze_batch(request, None))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["provider"], "built-in NLP analysis engine")
        self.assertIsNone(result["model"])
        self.assertEqual(result["total_requirements"], 2)
        self.assertEqual(len(result["analyses"]), 2)
        required_fields = {
            "quality_score", "classification", "clarity", "completeness",
            "testability", "suggested_rewrite", "explanation",
            "ambiguities", "missing_information", "issues",
        }
        for item in result["analyses"]:
            self.assertTrue(required_fields.issubset(item.keys()))
            self.assertIn("expert_review", item)

    def test_home_identifies_provider_free_engine(self):
        result = home()
        self.assertEqual(result["provider"], "built-in NLP analysis engine")
        self.assertEqual(result["mode"], "model-free")
        self.assertFalse(result["external_provider_required"])


if __name__ == "__main__":
    unittest.main()
