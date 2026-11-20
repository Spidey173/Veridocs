# LLM Evaluation Harness

The Veridocs evaluation harness (`tests/evals/`) evaluates factual grounding, hallucination detection, and alignment of the LLM evaluator against a curated benchmark of 40 labeled ground-truth cases.

---

## Architecture & Benchmark Overview

- **Dataset (`dataset.py`)**: 40 labeled benchmark cases spanning 10 distinct categories:
  1. `direct_grounded`: Factual, verbatim or near-verbatim claims.
  2. `paraphrased_grounded`: Complex paraphrases and synthesized phrasing.
  3. `multi_chunk_synthesis`: Cross-chunk information integration.
  4. `numeric_contradiction`: Adversarial number alterations and statistical exaggerations.
  5. `negation_inversion`: Adversarial polarity reversals (negations).
  6. `entity_role_reversal`: Adversarial entity, subject, or role swaps.
  7. `temporal_shift`: Adversarial date or time period alterations.
  8. `plausible_extrapolation`: Subtle out-of-context hallucinations.
  9. `unrelated_fabrication`: Completely fabricated out-of-domain assertions.
  10. `adversarial_injection`: Prompt injections and jailbreak attacks embedded in candidate answers.
- **Stochastic Multi-Run Evaluation**: Each case is evaluated $N$ times ($N=5$ by default, configurable) to measure output stability and variance under non-zero temperature.
- **Statistical Significance**:
  - **Mean & Standard Deviation**: Reported across runs for agreement rate, Cohen's kappa, precision, recall, and F1.
  - **95% Confidence Interval**: Computed via both **Student's $t$-distribution** (for small sample inference) and **1,000-sample bootstrap percentiles**.
  - **Inter-Rater Reliability (Cohen's Kappa)**: Measures observed agreement penalized by expected chance agreement:
    $$\kappa = \frac{P_o - P_e}{1 - P_e}$$
- **Threshold Gating**: The evaluation automatically fails if the **lower bound** of the 95% confidence interval for agreement rate drops below the configured threshold (default: `0.75`).
- **Reporting**: Full evaluation results, metadata, per-case predictions, and category breakdowns are saved as JSON artifacts in `tests/evals/reports/eval_report_<timestamp>.json` and `tests/evals/reports/latest.json`.

---

## Running the Evaluation

### Via Makefile
```bash
# Run with default settings (N=5 runs per case, threshold=0.75)
make eval

# Run with customized runs and threshold
make eval EVAL_RUNS=3 EVAL_THRESHOLD=0.80
```

### Via Pytest CLI
```bash
# Direct pytest execution targeting the live_eval marker
pytest -m live_eval backend/tests/evals

# Or passing environment variable overrides
EVAL_RUNS=5 EVAL_THRESHOLD=0.75 pytest -s -m live_eval backend/tests/evals
```

---

## Thresholds & Statistical Metrics

| Metric | Meaning | Target / Interpretation |
| :--- | :--- | :--- |
| **Agreement Rate** | Fraction of evaluator predictions matching human ground-truth labels. | $\ge 0.75$ lower 95% CI bound |
| **Cohen's Kappa ($\kappa$)** | Agreement above chance: <br>• $<0.20$: Slight<br>• $0.21-0.40$: Fair<br>• $0.41-0.60$: Moderate<br>• $0.61-0.80$: Substantial<br>• $0.81-1.00$: Near-perfect | $> 0.60$ indicates strong alignment beyond chance |
| **95% CI Lower Bound** | Conservative bound asserting that with 95% confidence the true expected performance exceeds this floor. | Used as the primary CI quality gate |
| **Category Accuracy** | Breakdown across direct claims, paraphrases, adversarial inversions, and prompt injections. | Used to detect category-specific regressions |
