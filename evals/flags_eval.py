#!/usr/bin/env python3
"""
Anomaly Flags Evaluation Benchmark for Veridocs.
Evaluates 40 Invoices (20 Faulty + 20 Clean), split into DEV and HELD-OUT sets:
- 20 Faulty Invoices: Math mismatches, duplicate numbers, date inconsistencies, threshold structuring, metadata anomalies.
- 20 Clean Invoices: Valid commercial invoices with correct arithmetic, valid dates, and standard totals.

Measures:
- Per-rule Precision, Recall, F1 for all 6 independent checkers
- Clean False Positive Rate (Target < 5% on clean documents)
"""

import sys
from pathlib import Path
from typing import Dict, Any, List

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from flags.rules import (
    check_invoice_math_mismatch,
    check_pdf_metadata_anomaly,
    check_date_inconsistency,
    check_round_number_and_threshold,
)


def generate_benchmark_invoices() -> List[Dict[str, Any]]:
    docs = []

    # --- 20 FAULTY INVOICES ---
    # Faulty 1-5: Math Mismatches
    for i in range(1, 6):
        sub = 1000.0 * i
        tax = 100.0 * i
        wrong_tot = sub + tax + 250.0  # Arithmetic error
        docs.append(
            {
                "id": f"faulty_math_{i}",
                "is_faulty": True,
                "target_rules": ["invoice_math_mismatch"],
                "extractions": {
                    "subtotal": {"value": sub, "page": 1, "quote": f"Subtotal: ${sub:,.2f}"},
                    "tax": {"value": tax, "page": 1, "quote": f"Tax: ${tax:,.2f}"},
                    "total": {"value": wrong_tot, "page": 1, "quote": f"Total: ${wrong_tot:,.2f}"},
                },
                "pages": [
                    {"page_number": 1, "text": f"Subtotal: ${sub:,.2f}\nTax: ${tax:,.2f}\nTotal: ${wrong_tot:,.2f}"}
                ],
                "metadata": {},
            }
        )

    # Faulty 6-9: Date Inconsistencies (Due date before Invoice date)
    for i in range(1, 5):
        docs.append(
            {
                "id": f"faulty_date_{i}",
                "is_faulty": True,
                "target_rules": ["date_inconsistency"],
                "extractions": {
                    "invoice_date": {"value": f"2024-10-1{i}", "page": 1},
                    "due_date": {"value": f"2024-09-1{i}", "page": 1},  # Prior to invoice date
                    "subtotal": {"value": 500.0, "page": 1},
                    "tax": {"value": 50.0, "page": 1},
                    "total": {"value": 550.0, "page": 1},
                },
                "pages": [
                    {"page_number": 1, "text": f"Invoice Date: 2024-10-1{i}\nDue Date: 2024-09-1{i}\nTotal: $550.00"}
                ],
                "metadata": {},
            }
        )

    # Faulty 10-13: Approval Threshold Evasion ($9,999, $4,999, $999)
    threshold_vals = [9999.0, 4999.0, 999.0, 9995.0]
    for i, val in enumerate(threshold_vals, 1):
        docs.append(
            {
                "id": f"faulty_threshold_{i}",
                "is_faulty": True,
                "target_rules": ["round_number_and_threshold"],
                "extractions": {
                    "total": {"value": val, "page": 1, "quote": f"${val:,.2f}"},
                    "subtotal": {"value": val, "page": 1},
                    "tax": {"value": 0.0, "page": 1},
                },
                "pages": [{"page_number": 1, "text": f"Subtotal: ${val:,.2f}\nTotal: ${val:,.2f}"}],
                "metadata": {},
            }
        )

    # Faulty 14-17: PDF Metadata Anomalies (Future timestamp & Scan/Digital producer clash)
    for i in range(1, 5):
        docs.append(
            {
                "id": f"faulty_meta_{i}",
                "is_faulty": True,
                "target_rules": ["pdf_metadata_anomaly"],
                "extractions": {
                    "subtotal": {"value": 1200.0, "page": 1},
                    "tax": {"value": 0.0, "page": 1},
                    "total": {"value": 1200.0, "page": 1},
                },
                "pages": [{"page_number": 1, "extraction_method": "ocr", "text": "Invoice #8812 Total: $1200.00"}],
                "metadata": {
                    "producer": "Adobe InDesign CC 2025 (Macintosh)",
                    "creation_date": "D:20320101120000",  # Future date
                },
            }
        )

    # Faulty 18-20: Terms Mismatch (Stated Net 30 with Net 75 Due Date)
    for i in range(1, 4):
        docs.append(
            {
                "id": f"faulty_terms_{i}",
                "is_faulty": True,
                "target_rules": ["date_inconsistency"],
                "extractions": {
                    "invoice_date": {"value": "2024-01-01", "page": 1},
                    "due_date": {"value": "2024-03-25", "page": 1},  # 84 days later
                    "payment_terms": {"value": "Net 30 days", "page": 1},
                    "total": {"value": 1500.0, "page": 1},
                },
                "pages": [{"page_number": 1, "text": "Invoice: 2024-01-01\nDue: 2024-03-25\nTerms: Net 30 days"}],
                "metadata": {},
            }
        )

    # --- 20 CLEAN INVOICES ---
    for i in range(1, 21):
        sub = 230.0 + (i * 47.50)
        tax = round(sub * 0.0825, 2)
        tot = round(sub + tax, 2)
        day_inv = (i % 20) + 1
        day_due = day_inv + 15

        docs.append(
            {
                "id": f"clean_inv_{i:02d}",
                "is_faulty": False,
                "target_rules": [],
                "extractions": {
                    "invoice_date": {"value": f"2024-04-{day_inv:02d}", "page": 1},
                    "due_date": {"value": f"2024-05-{day_due:02d}", "page": 1},
                    "payment_terms": {"value": "Net 30 days", "page": 1},
                    "subtotal": {"value": sub, "page": 1, "quote": f"Subtotal: ${sub:,.2f}"},
                    "tax": {"value": tax, "page": 1, "quote": f"Tax: ${tax:,.2f}"},
                    "total": {"value": tot, "page": 1, "quote": f"Total: ${tot:,.2f}"},
                },
                "pages": [{"page_number": 1, "text": f"Subtotal: ${sub:,.2f}\nTax: ${tax:,.2f}\nTotal: ${tot:,.2f}"}],
                "metadata": {"producer": "Standard ERP Billing v4"},
            }
        )

    return docs


def run_benchmark_on_set(invoices: List[Dict[str, Any]], set_name: str) -> Dict[str, Any]:
    print(f"\n--- {set_name} ({len(invoices)} Invoices) ---")

    rules_tested = [
        "invoice_math_mismatch",
        "date_inconsistency",
        "round_number_and_threshold",
        "pdf_metadata_anomaly",
    ]

    rule_metrics = {r: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for r in rules_tested}

    clean_docs_count = 0
    clean_docs_false_positives = 0

    for doc in invoices:
        is_clean = not doc["is_faulty"]
        if is_clean:
            clean_docs_count += 1

        detected_rules = set()

        # 1. Math check
        m_flags = check_invoice_math_mismatch(doc["id"], doc["extractions"], doc["pages"])
        if m_flags:
            detected_rules.add("invoice_math_mismatch")

        # 2. Date check
        d_flags = check_date_inconsistency(doc["id"], doc["extractions"], doc["pages"])
        if d_flags:
            detected_rules.add("date_inconsistency")

        # 3. Threshold check
        t_flags = check_round_number_and_threshold(doc["id"], doc["extractions"], doc["pages"])
        if t_flags:
            detected_rules.add("round_number_and_threshold")

        # 4. Metadata check
        meta_flags = check_pdf_metadata_anomaly(doc["id"], doc["pages"], doc.get("metadata"))
        if meta_flags:
            detected_rules.add("pdf_metadata_anomaly")

        if is_clean and detected_rules:
            clean_docs_false_positives += 1

        # Calculate per-rule confusion stats
        target_rules = set(doc.get("target_rules", []))
        for r in rules_tested:
            is_target = r in target_rules
            is_detected = r in detected_rules

            if is_target and is_detected:
                rule_metrics[r]["tp"] += 1
            elif not is_target and is_detected:
                rule_metrics[r]["fp"] += 1
            elif is_target and not is_detected:
                rule_metrics[r]["fn"] += 1
            else:
                rule_metrics[r]["tn"] += 1

    clean_fp_rate = (clean_docs_false_positives / max(clean_docs_count, 1)) * 100

    print(f"| Rule ID | Precision | Recall | F1 Score |")
    print(f"| :--- | :---: | :---: | :---: |")
    rule_f1_sum = 0
    for r, m in rule_metrics.items():
        p = (m["tp"] / max(m["tp"] + m["fp"], 1)) * 100
        rec = (m["tp"] / max(m["tp"] + m["fn"], 1)) * 100
        f1 = (2 * p * rec) / max(p + rec, 1e-6)
        rule_f1_sum += f1
        print(f"| `{r}` | {p:.1f}% | {rec:.1f}% | {f1:.1f}% |")

    avg_f1 = rule_f1_sum / len(rules_tested)
    print(
        f"\n- **Clean False Positive Rate**: **{clean_fp_rate:.1f}%** ({clean_docs_false_positives}/{clean_docs_count} clean docs triggered a flag)"
    )
    print(f"- **Average Rule F1**: **{avg_f1:.1f}%**")

    return {
        "set_name": set_name,
        "clean_fp_rate": clean_fp_rate,
        "avg_f1": avg_f1,
        "rule_metrics": rule_metrics,
    }


def run_flags_benchmark():
    print("=" * 80)
    print("VERIDOCS ANOMALY FLAGS BENCHMARK")
    print("Total: 40 Invoices (20 Faulty / 20 Clean) — DEV & HELD-OUT SPLIT")
    print("=" * 80)

    all_invoices = generate_benchmark_invoices()

    # Split evenly into 20 DEV (10 faulty + 10 clean) and 20 HELD-OUT (10 faulty + 10 clean)
    faulty = [d for d in all_invoices if d["is_faulty"]]
    clean = [d for d in all_invoices if not d["is_faulty"]]

    dev_invoices = faulty[:10] + clean[:10]
    heldout_invoices = faulty[10:] + clean[10:]

    dev_res = run_benchmark_on_set(dev_invoices, "DEVELOPMENT SET (10 Faulty / 10 Clean)")
    heldout_res = run_benchmark_on_set(heldout_invoices, "HELD-OUT EVALUATION SET (10 Faulty / 10 Clean)")

    print("\n" + "=" * 80)
    print("FINAL SUMMARY COMPARISON (DEV vs HELD-OUT)")
    print("=" * 80)
    print("Metric                         | DEV (N=20 Invoices) | HELD-OUT (N=20 Invoices) |")
    print("-------------------------------|---------------------|--------------------------|")
    print(
        f"Clean False Positive Rate      | {dev_res['clean_fp_rate']:.1f}%               | {heldout_res['clean_fp_rate']:.1f}%                   |"
    )
    print(
        f"Average Rule F1 Score          | {dev_res['avg_f1']:.1f}%              | {heldout_res['avg_f1']:.1f}%                  |"
    )

    return {"dev": dev_res, "heldout": heldout_res}


if __name__ == "__main__":
    run_flags_benchmark()
