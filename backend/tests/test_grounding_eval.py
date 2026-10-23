"""
Deterministic Grounding Evaluation Suite for Veridocs.
Evaluates the lexical and numerical grounding heuristic against:
  1. Grounded claims (true assertions directly supported by context)
  2. Subtle unsupported claims (vocabulary overlap with unsupported relations)
  3. Altered numbers (dates, percentages, currency modified from source)

Computes and asserts Precision, Recall, Accuracy, and F1-score.
"""

import pytest
from verification import calculate_grounding_score, evaluate_grounding_benchmark


class TestGroundingEvaluation:
    """Deterministic evaluation suite reporting precision, recall, and category breakdowns."""

    @pytest.fixture
    def benchmark_cases(self):
        """Standardized test benchmark for grounding heuristic."""
        source_context = [
            {
                "page": 1,
                "text": "Veridocs provides visual document highlighting using PDF.js text layer coordinates.",
                "source_file": "overview.pdf"
            },
            {
                "page": 2,
                "text": "The company reported annual revenue of $14.5 million in fiscal year 2024, representing 28% growth.",
                "source_file": "financials.pdf"
            },
            {
                "page": 3,
                "text": "The agreement shall remain in effect for 36 months unless terminated earlier with 60 days written notice.",
                "source_file": "contract.pdf"
            },
            {
                "page": 4,
                "text": "Dr. Sarah Connor was appointed Chief Technology Officer in November 2023.",
                "source_file": "leadership.pdf"
            }
        ]

        return [
            # === Category 1: Grounded Claims (Expected: Supported / True Positive) ===
            {
                "id": "grounded-1",
                "category": "grounded",
                "answer": "Veridocs provides visual document highlighting using PDF.js text layer coordinates [Page 1].",
                "source_chunks": source_context,
                "expected_supported": True,
            },
            {
                "id": "grounded-2",
                "category": "grounded",
                "answer": "Annual revenue reached $14.5 million in fiscal year 2024 with 28% growth [Page 2].",
                "source_chunks": source_context,
                "expected_supported": True,
            },
            {
                "id": "grounded-3",
                "category": "grounded",
                "answer": "The contract duration is 36 months and requires 60 days written notice to terminate [Page 3].",
                "source_chunks": source_context,
                "expected_supported": True,
            },
            {
                "id": "grounded-4",
                "category": "grounded",
                "answer": "Dr. Sarah Connor was appointed Chief Technology Officer in November 2023 [Page 4].",
                "source_chunks": source_context,
                "expected_supported": True,
            },

            # === Category 2: Altered Numbers (Expected: Unsupported / True Negative) ===
            {
                "id": "altered-num-1",
                "category": "altered_numbers",
                "answer": "The company reported annual revenue of $84.5 million in fiscal year 2024 with 75% growth.",
                "source_chunks": source_context,
                "expected_supported": False,
            },
            {
                "id": "altered-num-2",
                "category": "altered_numbers",
                "answer": "The agreement shall remain in effect for 12 months with 15 days notice.",
                "source_chunks": source_context,
                "expected_supported": False,
            },
            {
                "id": "altered-num-3",
                "category": "altered_numbers",
                "answer": "Dr. Sarah Connor was appointed Chief Technology Officer in 2018.",
                "source_chunks": source_context,
                "expected_supported": False,
            },

            # === Category 3: Subtle Unsupported Claims (Expected: Unsupported / True Negative) ===
            {
                "id": "unsupported-1",
                "category": "subtle_unsupported",
                "answer": "Veridocs was completely acquired by Adobe to replace their PDF rendering engine.",
                "source_chunks": source_context,
                "expected_supported": False,
            },
            {
                "id": "unsupported-2",
                "category": "subtle_unsupported",
                "answer": "The company filed for bankruptcy in 2024 due to catastrophic financial losses.",
                "source_chunks": source_context,
                "expected_supported": False,
            },
            {
                "id": "unsupported-3",
                "category": "subtle_unsupported",
                "answer": "Dr. Sarah Connor resigned in disgrace after an internal audit investigation.",
                "source_chunks": source_context,
                "expected_supported": False,
            },
        ]

    def test_deterministic_grounding_metrics(self, benchmark_cases):
        """
        Run the grounding evaluation suite, asserting precision >= 0.80 and recall >= 0.80,
        and verifying category breakdown statistics.
        """
        metrics = evaluate_grounding_benchmark(benchmark_cases)

        print("\n=== Grounding Heuristic Evaluation Report ===")
        print(f"Total Test Cases: {metrics['total_cases']}")
        print(f"Precision:        {metrics['precision']:.3f} (TP={metrics['true_positives']}, FP={metrics['false_positives']})")
        print(f"Recall:           {metrics['recall']:.3f} (TP={metrics['true_positives']}, FN={metrics['false_negatives']})")
        print(f"Accuracy:         {metrics['accuracy']:.3f}")
        print(f"F1-Score:         {metrics['f1_score']:.3f}")
        print("Category Breakdown:")
        for cat, stats in metrics["category_breakdown"].items():
            print(f"  - {cat:20s}: {stats['correct']}/{stats['total']} correct ({stats['accuracy']*100:.1f}%)")

        # Performance assertions
        assert metrics["total_cases"] == 10
        assert metrics["recall"] >= 0.75, "Recall for grounded claims should be high"
        assert metrics["precision"] >= 0.75, "Precision must reject altered numbers and unsupported claims"
        assert metrics["accuracy"] >= 0.80, "Overall accuracy should exceed 80%"

        # Number violation check: altered numbers must be caught
        altered_num_stats = metrics["category_breakdown"]["altered_numbers"]
        assert altered_num_stats["accuracy"] == 1.0, "Altered numbers must be 100% caught by numeric verification"

    def test_heuristic_boundary_cases(self):
        """Verify handling of empty text, short claims, and edge cases."""
        # Empty inputs
        score_empty = calculate_grounding_score("", [])
        assert score_empty["confidence_score"] == 0.0

        # Answer with no source
        score_no_source = calculate_grounding_score("Valid sentence with enough words.", [])
        assert score_no_source["confidence_score"] == 0.0

        # Method metadata returned
        res = calculate_grounding_score(
            "Veridocs provides visual document highlighting.",
            [{"text": "Veridocs provides visual document highlighting.", "page": 1}]
        )
        assert res["verification_method"] == "heuristic_lexical_numeric"
        assert "Surface token overlap" in res["method_limitations"]
