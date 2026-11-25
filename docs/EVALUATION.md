# Veridocs Evaluation Report

All numbers below were reproduced directly from the scripts under [`evals/`](../evals/) running offline (`LLM_API_KEY` / external providers disabled). Run any suite individually or all together:

```bash
.venv/bin/python evals/ingestion_eval.py
.venv/bin/python evals/retrieval_eval.py
.venv/bin/python evals/verification_eval.py
.venv/bin/python evals/extraction_eval.py
.venv/bin/python evals/comparison_eval.py
.venv/bin/python evals/flags_eval.py
.venv/bin/python evals/graph_eval.py
```

## Summary Across Suites

| Capability | Script | Dataset Scope | Primary Held-Out Result |
| :--- | :--- | :--- | :--- |
| Ingestion & OCR | `evals/ingestion_eval.py` | 11 fixtures (6 text-layer, 5 OCR) | 100.0% char accuracy, 100.0% table cell accuracy (4 tables) |
| Hybrid Retrieval | `evals/retrieval_eval.py` | 20 chunks, 20 queries (10 dev / 10 held-out) | Held-out Recall@5 = 100.0%, MRR = 1.000 |
| Claim Verification | `evals/verification_eval.py` | 60 claim/source pairs (30 dev / 30 held-out) | Held-out accuracy = 83.3%, Support F1 = 90.9%, Contradiction catch = 60.0% |
| Extraction & Entities | `evals/extraction_eval.py` | 10 docs (5 dev / 5 held-out) | Held-out DocType = 100.0%, Quote verified ratio = 100.0%, Entity F1 = 77.8% |
| Contract Comparison | `evals/comparison_eval.py` | 5 contract pairs (3 dev / 2 held-out) | Held-out Change Detection F1 = 100.0%, Risk Agreement = 100.0% |
| Anomaly Flags | `evals/flags_eval.py` | 40 invoices (20 dev / 20 held-out) | Held-out Clean FPR = 0.0%, Avg Rule F1 = 75.0% |
| Knowledge Graph | `evals/graph_eval.py` | 5 contracts (3 dev / 2 held-out) | Held-out Entity Resolution = 100.0%, Edge F1 = 100.0% |

## Detailed Observations

- **Verification (`evals/verification_eval.py`)**: On the 30 held-out claim pairs, heuristic NLI outperformed naive n-gram overlap on accuracy (`83.3%` vs `63.3%`), support F1 (`90.9%` vs `74.1%`), and contradiction catch rate (`60.0%` vs `0.0%`). Remaining misses are semantic paraphrases or subtle contradictions requiring a cross-encoder (`NLI_ENABLED=true`). In offline mode without a cross-encoder downloaded, both verifier rows report the same heuristic scores.
- **Extraction & Entities (`evals/extraction_eval.py`)**: On the 5 held-out docs, document classification, evidence quote verification, and invoice math checks reached `100.0%`, while average entity F1 was `77.8%` (Money `100.0%`, Organization `88.9%`, Date `44.4%` F1 due to regex date pattern recall misses on unconventional formats).
- **Anomaly Flags (`evals/flags_eval.py`)**: Clean false positive rate was `0.0%` across both dev (0/10) and held-out (0/10) invoices. Average rule F1 was `75.0%` per split because specific defect types were concentrated in either the dev or held-out subset (e.g., held-out contained 0 `invoice_math_mismatch` fault cases while catching `100.0%` on `date_inconsistency`, `round_number_and_threshold`, and `pdf_metadata_anomaly`).
- **Scope Caveat**: `tests/fixtures` and `evals/*` use synthetic contracts, invoices, scans, and curated claim pairs for deterministic offline CI verification rather than large proprietary enterprise corpora.

