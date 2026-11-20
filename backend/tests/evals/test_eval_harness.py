"""
Pytest integration for the live LLM evaluation harness.

Marked with @pytest.mark.live_eval so it is skipped during regular fast unit test runs,
and executes only via `make eval` or when running with pytest -m live_eval.
"""

import os
from pathlib import Path
import pytest

from tests.evals.dataset import EVAL_DATASET
from tests.evals.evaluator import (
    EvaluationHarness,
    LLMGroundingEvaluator,
    calculate_cohens_kappa,
    calculate_t_interval,
    calculate_bootstrap_interval
)


class TestEvaluationStatisticsUnit:
    """Fast deterministic unit checks for statistical metrics calculation."""

    def test_cohens_kappa_perfect_agreement(self):
        """Verify Cohen's kappa equals 1.0 when rater and ground truth agree completely."""
        y_true = [1, 1, 0, 0, 1, 0, 1, 0]
        y_pred = [1, 1, 0, 0, 1, 0, 1, 0]
        kappa = calculate_cohens_kappa(y_true, y_pred)
        assert pytest.approx(kappa, 0.001) == 1.0

    def test_cohens_kappa_chance_or_disagreement(self):
        """Verify Cohen's kappa penalizes chance agreement."""
        y_true = [1, 1, 1, 1, 0, 0, 0, 0]
        y_pred = [0, 0, 0, 0, 1, 1, 1, 1]  # total disagreement
        kappa = calculate_cohens_kappa(y_true, y_pred)
        assert kappa < 0.0

    def test_student_t_interval_bounds(self):
        """Verify 95% Student's t confidence interval bounds."""
        values = [0.85, 0.88, 0.86, 0.89, 0.87]
        lower, upper = calculate_t_interval(values, confidence=0.95)
        assert 0.80 <= lower <= 0.87
        assert 0.87 <= upper <= 0.95
        assert lower <= upper

    def test_bootstrap_interval_bounds(self):
        """Verify 95% bootstrap confidence interval."""
        values = [0.85, 0.88, 0.86, 0.89, 0.87]
        lower, upper = calculate_bootstrap_interval(values, n_bootstrap=500)
        assert 0.80 <= lower <= 0.88
        assert 0.86 <= upper <= 0.95
        assert lower <= upper

    def test_dataset_size_and_adversarial_coverage(self):
        """Ensure benchmark dataset contains at least 30-50 cases with edge cases and adversarial examples."""
        assert len(EVAL_DATASET) >= 30, f"Expected at least 30 benchmark cases, got {len(EVAL_DATASET)}"
        adversarial_cases = [c for c in EVAL_DATASET if c.get("is_adversarial")]
        assert len(adversarial_cases) >= 15, "Expected at least 15 adversarial / edge cases"
        categories = {c["category"] for c in EVAL_DATASET}
        assert len(categories) >= 8, f"Expected broad categorical diversity, got {categories}"


@pytest.mark.live_eval
class TestLiveLLMEvaluation:
    """Live LLM evaluation suite executed on demand via `make eval` or CI."""

    def test_live_llm_grounding_benchmark(self):
        """
        Execute the live LLM evaluation harness against the labeled benchmark:
        - Runs each case N times (default N=5, configurable via EVAL_RUNS)
        - Reports mean score, std dev, and 95% confidence intervals per metric
        - Evaluates Cohen's kappa and agreement rate against human labels
        - Asserts lower CI bound meets or exceeds configured threshold
        - Validates that report is cached under tests/evals/reports/
        """
        runs = int(os.getenv("EVAL_RUNS", "5"))
        threshold = float(os.getenv("EVAL_THRESHOLD", "0.75"))

        evaluator = LLMGroundingEvaluator()
        harness = EvaluationHarness(evaluator=evaluator, n_runs=runs, threshold=threshold)

        report = harness.run_benchmark(EVAL_DATASET)

        # Print human-readable summary
        metrics = report["summary_metrics"]
        print("\n=======================================================")
        print(f"       LIVE LLM EVALUATION REPORT ({report['provider']}/{report['model']})")
        print("=======================================================")
        print(f"Total Test Cases:       {report['total_benchmark_cases']}")
        print(f"Stochastic Runs / Case: {report['runs_per_case']}")
        print(f"Target CI Threshold:    {report['threshold_configured']:.3f}")
        print("-------------------------------------------------------")
        for name, data in metrics.items():
            mean = data["mean"]
            std = data["std_dev"]
            ci_t = data["ci_95_t"]
            print(f"{name:16s}: Mean={mean:.4f}  Std={std:.4f}  95% CI (t-dist)=[{ci_t[0]:.4f}, {ci_t[1]:.4f}]")
        print("-------------------------------------------------------")
        print("Category Breakdown:")
        for cat, stats in report["category_breakdown"].items():
            print(f"  - {cat:24s}: {stats['correct_judgments']}/{stats['total_judgments']} ({stats['accuracy']*100:.1f}%)")
        print("=======================================================")

        # Assert report file was written
        reports_dir = Path(__file__).parent / "reports"
        latest_file = reports_dir / "latest.json"
        assert latest_file.exists(), "Latest evaluation report JSON file must exist"

        # Assert lower 95% CI bound meets threshold
        lower_bound = report["lower_bound_ci_95"]
        assert report["passed"], (
            f"Eval FAILED: Lower 95% CI bound for agreement rate ({lower_bound:.4f}) "
            f"dropped below required threshold ({threshold:.4f})."
        )
