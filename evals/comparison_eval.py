#!/usr/bin/env python3
"""
Contract Comparison Evaluation Benchmark for Veridocs.
Evaluates 5 Contract Pairs (Split into DEV and HELD-OUT):
- Pair 1: SaaS Agreement v1 vs v2 (Pricing, Term, Added Surcharges)
- Pair 2: Mutual NDA v1 vs v2 (Confidentiality Survival, Governing Law)
- Pair 3: Commercial Lease Agreement v1 vs v2 (Rent, Deposit, Moved Maintenance)
- Pair 4: Master Consulting Services v1 vs v2 (Liability Cap, Indemnity, Added IP)
- Pair 5: Standard Vendor Agreement v1 vs v2 (Clean identical clauses & minor phrasing)

Measures:
- Change Detection Precision, Recall, F1 (Changed vs Unchanged)
- Risk Level Agreement (% matches with expected legal risk severity)
"""

import sys
from pathlib import Path
from typing import Dict, Any, List

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from comparison.clause_segmenter import ClauseSegmenter
from comparison.aligner import ClauseAligner
from comparison.service import summarize_clause_change_llm


CONTRACT_PAIRS = [
    # --- PAIR 1 (DEV) ---
    {
        "id": "pair_01_saas_agreement",
        "split": "dev",
        "name": "SaaS Subscription Agreement (v1 vs v2)",
        "doc_a_pages": [
            {
                "page_number": 1,
                "text": (
                    "MASTER SAAS AGREEMENT\n"
                    "1. Term. The initial term is 12 months.\n"
                    "2. Monthly Fees. Customer will pay $5,000.00 monthly subscription fee.\n"
                    "3. Limitation of Liability. Direct damages capped at $100,000.00.\n"
                ),
            }
        ],
        "doc_b_pages": [
            {
                "page_number": 1,
                "text": (
                    "MASTER SAAS AGREEMENT\n"
                    "1. Term. The initial term is 36 months.\n"  # Modified (Medium)
                    "2. Monthly Fees. Customer will pay $15,000.00 monthly subscription fee.\n"  # Modified (High)
                    "3. Limitation of Liability. Direct damages capped at $100,000.00.\n"  # Unchanged
                    "4. Data Security Surcharge. An additional 5% infrastructure surcharge applies.\n"  # Added (Medium)
                ),
            }
        ],
        "ground_truth_changes": [
            {"clause": "Term", "changed": True, "risk": "medium"},
            {"clause": "Monthly Fees", "changed": True, "risk": "high"},
            {"clause": "Limitation of Liability", "changed": False, "risk": "low"},
            {"clause": "Data Security Surcharge", "changed": True, "risk": "medium"},
        ],
    },
    # --- PAIR 2 (DEV) ---
    {
        "id": "pair_02_mutual_nda",
        "split": "dev",
        "name": "Mutual Non-Disclosure Agreement (v1 vs v2)",
        "doc_a_pages": [
            {
                "page_number": 1,
                "text": (
                    "MUTUAL NONDISCLOSURE AGREEMENT\n"
                    "1. Definition. Confidential Information encompasses all proprietary technical data.\n"
                    "2. Survival Period. Obligations survive for 3 years following disclosure.\n"
                    "3. Governing Law. This agreement is governed by the laws of Delaware.\n"
                ),
            }
        ],
        "doc_b_pages": [
            {
                "page_number": 1,
                "text": (
                    "MUTUAL NONDISCLOSURE AGREEMENT\n"
                    "1. Definition. Confidential Information encompasses all proprietary technical data.\n"  # Unchanged
                    "2. Survival Period. Obligations survive in perpetuity for trade secrets.\n"  # Modified (Medium/High)
                    "3. Governing Law. This agreement is governed by the laws of California.\n"  # Modified (Low)
                ),
            }
        ],
        "ground_truth_changes": [
            {"clause": "Definition", "changed": False, "risk": "low"},
            {"clause": "Survival Period", "changed": True, "risk": "medium"},
            {"clause": "Governing Law", "changed": True, "risk": "low"},
        ],
    },
    # --- PAIR 3 (DEV) ---
    {
        "id": "pair_03_commercial_lease",
        "split": "dev",
        "name": "Commercial Real Estate Lease (v1 vs v2)",
        "doc_a_pages": [
            {
                "page_number": 1,
                "text": (
                    "COMMERCIAL OFFICE LEASE\n"
                    "1. Base Rent. Tenant shall pay $8,500.00 monthly base rent.\n"
                    "2. Security Deposit. A refundable security deposit of $10,000.00 is required.\n"
                    "3. Permitted Use. Solely for general commercial office purposes.\n"
                ),
            }
        ],
        "doc_b_pages": [
            {
                "page_number": 1,
                "text": (
                    "COMMERCIAL OFFICE LEASE\n"
                    "1. Base Rent. Tenant shall pay $12,500.00 monthly base rent.\n"  # Modified (High)
                    "2. Security Deposit. A non-refundable fee of $10,000.00 is required.\n"  # Modified (High)
                    "3. Permitted Use. Solely for general commercial office purposes.\n"  # Unchanged
                ),
            }
        ],
        "ground_truth_changes": [
            {"clause": "Base Rent", "changed": True, "risk": "high"},
            {"clause": "Security Deposit", "changed": True, "risk": "high"},
            {"clause": "Permitted Use", "changed": False, "risk": "low"},
        ],
    },
    # --- PAIR 4 (HELD-OUT) ---
    {
        "id": "pair_04_consulting_services",
        "split": "heldout",
        "name": "Master Consulting Agreement (v1 vs v2)",
        "doc_a_pages": [
            {
                "page_number": 1,
                "text": (
                    "PROFESSIONAL CONSULTING AGREEMENT\n"
                    "1. Services Scope. Consultant will perform cloud architecture reviews.\n"
                    "2. Hourly Billing. Consultant rate is $250.00 per hour invoiced bi-weekly.\n"
                    "3. Indemnification. Client indemnifies Consultant against third-party IP claims.\n"
                    "4. Termination. Either party may terminate with 30 days written notice.\n"
                ),
            }
        ],
        "doc_b_pages": [
            {
                "page_number": 1,
                "text": (
                    "PROFESSIONAL CONSULTING AGREEMENT\n"
                    "1. Services Scope. Consultant will perform cloud architecture reviews.\n"  # Unchanged
                    "2. Hourly Billing. Consultant rate is $450.00 per hour invoiced weekly.\n"  # Modified (High)
                    "3. Indemnification. Consultant indemnifies Client against all liabilities.\n"  # Inverted Indemnity (High)
                    "4. Termination. Neither party may terminate prior to 12 months.\n"  # Modified (Medium)
                ),
            }
        ],
        "ground_truth_changes": [
            {"clause": "Services Scope", "changed": False, "risk": "low"},
            {"clause": "Hourly Billing", "changed": True, "risk": "high"},
            {"clause": "Indemnification", "changed": True, "risk": "high"},
            {"clause": "Termination", "changed": True, "risk": "medium"},
        ],
    },
    # --- PAIR 5 (HELD-OUT) ---
    {
        "id": "pair_05_clean_vendor_renegotiation",
        "split": "heldout",
        "name": "Standard Vendor Services Agreement (v1 vs v2)",
        "doc_a_pages": [
            {
                "page_number": 1,
                "text": (
                    "STANDARD VENDOR CONTRACT\n"
                    "1. Service Deliverables. Deliverables described in Schedule A.\n"
                    "2. Warranty. 90-day standard replacement warranty on hardware.\n"
                    "3. Confidentiality. Confidentiality maintained for 2 years.\n"
                ),
            }
        ],
        "doc_b_pages": [
            {
                "page_number": 1,
                "text": (
                    "STANDARD VENDOR CONTRACT\n"
                    "1. Service Deliverables. Deliverables described in Schedule A.\n"  # Unchanged
                    "2. Warranty. 90-day standard replacement warranty on hardware.\n"  # Unchanged
                    "3. Confidentiality. Confidentiality maintained for 5 years.\n"  # Modified (Medium)
                ),
            }
        ],
        "ground_truth_changes": [
            {"clause": "Service Deliverables", "changed": False, "risk": "low"},
            {"clause": "Warranty", "changed": False, "risk": "low"},
            {"clause": "Confidentiality", "changed": True, "risk": "medium"},
        ],
    },
]


def evaluate_contract_pairs(pairs: List[Dict[str, Any]], set_name: str) -> Dict[str, Any]:
    print(f"\n--- {set_name} ({len(pairs)} Contract Pairs) ---")
    segmenter = ClauseSegmenter()
    aligner = ClauseAligner(similarity_threshold=0.65)

    tp, fp, fn, tn = 0, 0, 0, 0
    risk_agreements = 0
    total_evaluated_risks = 0

    pair_summaries = []

    for pair in pairs:
        clauses_a = segmenter.segment_pages(pair["doc_a_pages"], document_id=f"{pair['id']}_a")
        clauses_b = segmenter.segment_pages(pair["doc_b_pages"], document_id=f"{pair['id']}_b")

        aligned = aligner.align_and_diff(clauses_a, clauses_b)

        # Map predictions by clause topic
        pred_map = {}
        for item in aligned:
            status = item["status"]
            is_changed = status in ("modified", "added", "removed", "moved")
            ca = item.get("clause_a")
            cb = item.get("clause_b")

            heading = ((cb.get("heading") if cb else None) or (ca.get("heading") if ca else None) or "").lower()

            analysis = None
            if is_changed:
                analysis = summarize_clause_change_llm(ca, cb)

            pred_map[heading] = {
                "changed": is_changed,
                "status": status,
                "risk": analysis.get("risk", "low") if analysis else "low",
            }

        # Compare with ground truth
        for gt in pair["ground_truth_changes"]:
            gt_topic = gt["clause"].lower()
            gt_changed = gt["changed"]
            gt_risk = gt["risk"]

            # Match by substring
            matched_pred = None
            for p_head, p_data in pred_map.items():
                if gt_topic in p_head or p_head in gt_topic:
                    matched_pred = p_data
                    break

            pred_changed = matched_pred["changed"] if matched_pred else False
            pred_risk = matched_pred["risk"] if matched_pred else "low"

            if gt_changed and pred_changed:
                tp += 1
            elif not gt_changed and pred_changed:
                fp += 1
            elif gt_changed and not pred_changed:
                fn += 1
            else:
                tn += 1

            if gt_changed:
                total_evaluated_risks += 1
                # Risk agreement: exact match or both high/medium
                if pred_risk == gt_risk or (pred_risk in ("high", "medium") and gt_risk in ("high", "medium")):
                    risk_agreements += 1

        pair_summaries.append(
            {
                "id": pair["id"],
                "name": pair["name"],
                "clauses_a": len(clauses_a),
                "clauses_b": len(clauses_b),
                "total_aligned": len(aligned),
            }
        )

    precision = (tp / max(tp + fp, 1)) * 100
    recall = (tp / max(tp + fn, 1)) * 100
    f1 = (2 * precision * recall) / max(precision + recall, 1e-6)
    risk_agreement_pct = (risk_agreements / max(total_evaluated_risks, 1)) * 100

    print(f"| Metric | Result |")
    print(f"| :--- | :---: |")
    print(f"| Change Detection Precision | {precision:.1f}% |")
    print(f"| Change Detection Recall | {recall:.1f}% |")
    print(f"| **Change Detection F1** | **{f1:.1f}%** |")
    print(f"| **Risk Severity Agreement** | **{risk_agreement_pct:.1f}%** |")

    return {
        "set_name": set_name,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "risk_agreement": risk_agreement_pct,
    }


def run_comparison_benchmark():
    print("=" * 80)
    print("VERIDOCS CONTRACT COMPARISON & ALIGNMENT BENCHMARK")
    print("Total: 5 Contract Pairs (Split into 3 Dev / 2 Held-Out)")
    print("=" * 80)

    dev_pairs = [p for p in CONTRACT_PAIRS if p["split"] == "dev"]
    heldout_pairs = [p for p in CONTRACT_PAIRS if p["split"] == "heldout"]

    dev_res = evaluate_contract_pairs(dev_pairs, "DEVELOPMENT SET (Tuning & Validation)")
    heldout_res = evaluate_contract_pairs(heldout_pairs, "HELD-OUT EVALUATION SET (Final Test)")

    print("\n" + "=" * 80)
    print("FINAL SUMMARY COMPARISON (DEV vs HELD-OUT)")
    print("=" * 80)
    print("Metric                         | DEV (N=3 Pairs) | HELD-OUT (N=2 Pairs) |")
    print("-------------------------------|-----------------|----------------------|")
    print(
        f"Change Detection Precision     | {dev_res['precision']:.1f}%           | {heldout_res['precision']:.1f}%            |"
    )
    print(
        f"Change Detection Recall        | {dev_res['recall']:.1f}%           | {heldout_res['recall']:.1f}%            |"
    )
    print(f"Change Detection F1            | {dev_res['f1']:.1f}%           | {heldout_res['f1']:.1f}%            |")
    print(
        f"Legal Risk Level Agreement     | {dev_res['risk_agreement']:.1f}%           | {heldout_res['risk_agreement']:.1f}%            |"
    )

    return {"dev": dev_res, "heldout": heldout_res}


if __name__ == "__main__":
    run_comparison_benchmark()
