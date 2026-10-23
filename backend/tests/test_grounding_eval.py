"""
Synthetic Grounding Heuristic Regression Suite for Veridocs.

This 16-case synthetic suite serves strictly as a deterministic unit/regression test
harness to verify that fast algorithmic heuristics (polarity inversion detection,
regex numeric mismatches, n-gram overlap) operate as designed on targeted edge cases.

It does NOT constitute or claim evidence of broad real-world factual accuracy
across unstructured, domain-complex, or noisy human documents.
"""

import pytest
from verification import calculate_grounding_score, evaluate_grounding_benchmark


class TestGroundingEvaluation:
    """Synthetic regression suite evaluating precision, recall, and category breakdowns."""

    @pytest.fixture
    def benchmark_cases(self):
        """Standardized synthetic regression cases for grounding heuristic."""
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

            # === Category 2: Paraphrased Claims (Expected: Supported / True Positive) ===
            {
                "id": "paraphrase-1",
                "category": "paraphrases",
                "answer": "Visual text layer coordinates are utilized by Veridocs to highlight source passages on document pages [Page 1].",
                "source_chunks": source_context,
                "expected_supported": True,
            },
            {
                "id": "paraphrase-2",
                "category": "paraphrases",
                "answer": "During fiscal year 2024, the business produced $14.5 million in annual revenue alongside 28% expansion [Page 2].",
                "source_chunks": source_context,
                "expected_supported": True,
            },

            # === Category 3: Negation Inversions (Expected: Unsupported / True Negative) ===
            {
                "id": "negation-1",
                "category": "negation",
                "answer": "The agreement does not remain in effect for 36 months under standard conditions.",
                "source_chunks": source_context,
                "expected_supported": False,
            },
            {
                "id": "negation-2",
                "category": "negation",
                "answer": "Dr. Sarah Connor was never appointed Chief Technology Officer in November 2023.",
                "source_chunks": source_context,
                "expected_supported": False,
            },
            {
                "id": "negation-3",
                "category": "negation",
                "answer": "The company reported no annual revenue in fiscal year 2024.",
                "source_chunks": source_context,
                "expected_supported": False,
            },

            # === Category 4: Role Reversal (Expected: Unsupported / True Negative) ===
            {
                "id": "role-reversal-1",
                "category": "role_reversal",
                "answer": "Chief Technology Officer Sarah Connor appointed the executive board in November 2023.",
                "source_chunks": source_context,
                "expected_supported": False,
            },

            # === Category 5: Altered Numbers (Expected: Unsupported / True Negative) ===
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

            # === Category 6: Subtle Unsupported / Fabricated Claims (Expected: Unsupported / True Negative) ===
            {
                "id": "unsupported-1",
                "category": "unrelated_claims",
                "answer": "Veridocs was completely acquired by Adobe to replace their PDF rendering engine.",
                "source_chunks": source_context,
                "expected_supported": False,
            },
            {
                "id": "unsupported-2",
                "category": "unrelated_claims",
                "answer": "The company filed for bankruptcy in 2024 due to catastrophic financial losses.",
                "source_chunks": source_context,
                "expected_supported": False,
            },
            {
                "id": "unsupported-3",
                "category": "unrelated_claims",
                "answer": "Dr. Sarah Connor resigned in disgrace after an internal audit investigation.",
                "source_chunks": source_context,
                "expected_supported": False,
            },
        ]

    def test_deterministic_grounding_metrics(self, benchmark_cases):
        """
        Run the grounding evaluation suite across 16 test cases, asserting precision and recall,
        and verifying category breakdowns across paraphrases, negations, role reversals, and altered numbers.
        """
        metrics = evaluate_grounding_benchmark(benchmark_cases)

        print("\n=== Grounding Heuristic Evaluation Report ===")
        print(f"Total Benchmark Cases: {metrics['total_cases']}")
        print(f"Precision:             {metrics['precision']:.3f} (TP={metrics['true_positives']}, FP={metrics['false_positives']})")
        print(f"Recall:                {metrics['recall']:.3f} (TP={metrics['true_positives']}, FN={metrics['false_negatives']})")
        print(f"Accuracy:              {metrics['accuracy']:.3f}")
        print(f"F1-Score:              {metrics['f1_score']:.3f}")
        print("Category Breakdown:")
        for cat, stats in metrics["category_breakdown"].items():
            print(f"  - {cat:20s}: {stats['correct']}/{stats['total']} correct ({stats['accuracy']*100:.1f}%)")

        # Performance assertions
        assert metrics["total_cases"] == 16
        assert metrics["recall"] >= 0.80, "Recall for factual and paraphrased grounded claims should be high"
        assert metrics["precision"] >= 0.80, "Precision must reject altered numbers, polar inversions, and unsupported claims"
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
