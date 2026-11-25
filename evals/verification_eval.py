#!/usr/bin/env python3
"""
Verification & Grounding Evaluation Benchmark for Veridocs.
Evaluates ~60 labeled claim/source pairs comparing:
1. Naive n-gram lexical overlap
2. Veridocs Two-stage NLI Verifier (lexical screen + contradiction & entailment inference)
Measures Accuracy, Precision, Recall, F1, and confusion matrices.
"""

import sys
import re
from pathlib import Path
from typing import Dict, Any, List

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from verification import check_nli_entailment


# 60 Labeled Claim / Source Pairs (20 Supported, 20 Contradicted, 20 Unsupported)
LABELED_PAIRS = [
    # --- 20 SUPPORTED CLAIMS ---
    {
        "id": "sup_01",
        "premise": "The payment terms are strictly Net 30 days from the invoice issuance date.",
        "hypothesis": "Payment terms are Net 30 days from the invoice date.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_02",
        "premise": "Provider commits to maintaining a minimum monthly uptime SLA of 99.9%.",
        "hypothesis": "The monthly uptime commitment SLA is 99.9%.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_03",
        "premise": "The total contract liability shall not exceed $500,000.00.",
        "hypothesis": "Maximum cumulative liability is capped at $500,000.00.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_04",
        "premise": "Customer shall be billed $2,500 monthly for enterprise database hosting.",
        "hypothesis": "Enterprise database hosting costs $2,500 per month.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_05",
        "premise": "This agreement is governed by and construed under the laws of Delaware.",
        "hypothesis": "Governing law for this agreement is the state of Delaware.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_06",
        "premise": "The confidentiality obligations shall survive for a period of 5 years.",
        "hypothesis": "Confidentiality obligations continue for 5 years after termination.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_07",
        "premise": "All customer data is encrypted in transit using TLS 1.3 and at rest with AES-256.",
        "hypothesis": "Customer data is encrypted with TLS 1.3 and AES-256 at rest.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_08",
        "premise": "The initial term of this agreement is 36 months starting June 1, 2024.",
        "hypothesis": "The agreement has an initial 36-month term commencing June 1, 2024.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_09",
        "premise": "Late payments will accrue interest at the rate of 1.5% per month.",
        "hypothesis": "Late invoice payments incur a 1.5% monthly interest penalty.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_10",
        "premise": "Either party may terminate for convenience with 60 days prior written notice.",
        "hypothesis": "Termination for convenience requires 60 days advance written notice.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_11",
        "premise": "Figure on page 3: Quarterly Revenue. Description: Bar chart showing revenue grew from $10M in Q1 to $14M in Q4.",
        "hypothesis": "Revenue reached $14M in Q4 according to the chart.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_12",
        "premise": "Table on page 2: Enterprise Tier | 50 seats | $4,000/mo | Dedicated support",
        "hypothesis": "The Enterprise tier includes 50 seats with dedicated support for $4,000 monthly.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_13",
        "premise": "Vendor must notify customer within 24 hours of discovering a confirmed security breach.",
        "hypothesis": "Security incidents must be reported to the customer within 24 hours.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_14",
        "premise": "The research team evaluated 15,000 clinical samples across 4 medical centers.",
        "hypothesis": "A total of 15,000 clinical samples were evaluated across four medical centers.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_15",
        "premise": "Authorized representative Jane Doe signed the document on March 15, 2024.",
        "hypothesis": "Jane Doe executed the contract on March 15, 2024.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_16",
        "premise": "Invoice #4921 shows subtotal $1,200.00, sales tax $96.00, and balance due $1,296.00.",
        "hypothesis": "Invoice #4921 has a total balance due of $1,296.00.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_17",
        "premise": "Audit logs are retained in immutable storage for a minimum of 7 years.",
        "hypothesis": "System audit logs must be preserved for at least 7 years.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_18",
        "premise": "The proposed neural model achieved 92.4% F1 score on the biomedical benchmark.",
        "hypothesis": "The model obtained an F1 score of 92.4% on biomedical data.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_19",
        "premise": "Consulting services will be delivered remotely from Seattle, Washington.",
        "hypothesis": "The consulting engagement is conducted remotely out of Seattle.",
        "ground_truth": "supported",
    },
    {
        "id": "sup_20",
        "premise": "The security deposit of $10,000 is refundable within 30 days of lease expiration.",
        "hypothesis": "The $10,000 security deposit is returned within 30 days after lease expiry.",
        "ground_truth": "supported",
    },
    # --- 20 CONTRADICTED CLAIMS (Crucial: high lexical overlap but factual conflicts) ---
    {
        "id": "contra_01",
        "premise": "The payment terms are strictly Net 30 days from the invoice issuance date.",
        "hypothesis": "The payment terms are strictly Net 90 days from the invoice issuance date.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_02",
        "premise": "Provider commits to maintaining a minimum monthly uptime SLA of 99.9%.",
        "hypothesis": "Provider commits to maintaining a minimum monthly uptime SLA of 95.0%.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_03",
        "premise": "The total contract liability shall not exceed $500,000.00.",
        "hypothesis": "The total contract liability shall not exceed $5,000,000.00.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_04",
        "premise": "Customer shall be billed $2,500 monthly for enterprise database hosting.",
        "hypothesis": "Customer shall be billed $7,500 monthly for enterprise database hosting.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_05",
        "premise": "Vendor is strictly prohibited from sharing customer confidential information with third parties.",
        "hypothesis": "Vendor is permitted to share customer confidential information with third parties.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_06",
        "premise": "The confidentiality obligations shall survive for a period of 5 years.",
        "hypothesis": "The confidentiality obligations shall survive for a period of 1 year.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_07",
        "premise": "All customer data is encrypted in transit and at rest.",
        "hypothesis": "Customer data is not encrypted in transit or at rest.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_08",
        "premise": "The initial term of this agreement is 36 months starting June 1, 2024.",
        "hypothesis": "The initial term of this agreement is 12 months starting June 1, 2024.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_09",
        "premise": "Late payments will accrue interest at the rate of 1.5% per month.",
        "hypothesis": "Late payments will not accrue any interest penalties.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_10",
        "premise": "Either party may terminate for convenience with 60 days prior written notice.",
        "hypothesis": "Neither party may terminate the agreement for convenience prior to expiration.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_11",
        "premise": "Figure on page 3: Quarterly Revenue. Description: Bar chart showing revenue grew from $10M in Q1 to $14M in Q4.",
        "hypothesis": "Quarterly revenue declined sharply from $10M down to $2M in Q4.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_12",
        "premise": "Table on page 2: Enterprise Tier | 50 seats | $4,000/mo | Dedicated support",
        "hypothesis": "The Enterprise tier costs $12,000 monthly for 50 seats.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_13",
        "premise": "Vendor must notify customer within 24 hours of discovering a confirmed security breach.",
        "hypothesis": "Vendor is granted 30 business days before reporting security breaches to the customer.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_14",
        "premise": "The research team evaluated 15,000 clinical samples across 4 medical centers.",
        "hypothesis": "The study evaluated only 250 animal subjects in a single laboratory.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_15",
        "premise": "Authorized representative Jane Doe signed the document on March 15, 2024.",
        "hypothesis": "Jane Doe explicitly refused to sign the document on March 15, 2024.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_16",
        "premise": "Invoice #4921 shows subtotal $1,200.00, sales tax $96.00, and balance due $1,296.00.",
        "hypothesis": "Invoice #4921 has a total balance due of $8,500.00.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_17",
        "premise": "Audit logs are retained in immutable storage for a minimum of 7 years.",
        "hypothesis": "Audit logs are deleted automatically after 30 days.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_18",
        "premise": "The proposed neural model achieved 92.4% F1 score on the biomedical benchmark.",
        "hypothesis": "The proposed neural model achieved only 41.2% F1 score on the benchmark.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_19",
        "premise": "Consulting services will be delivered remotely from Seattle, Washington.",
        "hypothesis": "Consulting services require full-time on-site presence in Tokyo, Japan.",
        "ground_truth": "contradicted",
    },
    {
        "id": "contra_20",
        "premise": "The security deposit of $10,000 is refundable within 30 days of lease expiration.",
        "hypothesis": "The security deposit of $10,000 is completely non-refundable upon lease expiration.",
        "ground_truth": "contradicted",
    },
    # --- 20 UNSUPPORTED CLAIMS (Hallucinations / unmentioned topics) ---
    {
        "id": "unsup_01",
        "premise": "The payment terms are strictly Net 30 days from the invoice issuance date.",
        "hypothesis": "The customer plans to open three new retail locations in Chicago next summer.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_02",
        "premise": "Provider commits to maintaining a minimum monthly uptime SLA of 99.9%.",
        "hypothesis": "Provider employs 250 software engineers across four European offices.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_03",
        "premise": "The total contract liability shall not exceed $500,000.00.",
        "hypothesis": "The CEO of the vendor company previously worked at Microsoft.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_04",
        "premise": "Customer shall be billed $2,500 monthly for enterprise database hosting.",
        "hypothesis": "Database backups are stored in AWS S3 buckets in Frankfurt.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_05",
        "premise": "This agreement is governed by and construed under the laws of Delaware.",
        "hypothesis": "Delaware state corporate income tax rate increased by 2% this year.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_06",
        "premise": "The confidentiality obligations shall survive for a period of 5 years.",
        "hypothesis": "Both organizations agreed to sponsor an annual hackathon for college students.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_07",
        "premise": "All customer data is encrypted in transit using TLS 1.3 and at rest with AES-256.",
        "hypothesis": "Quantum computing hardware will break RSA cryptography within 10 years.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_08",
        "premise": "The initial term of this agreement is 36 months starting June 1, 2024.",
        "hypothesis": "Weather conditions in June caused flight delays throughout the Northeast corridor.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_09",
        "premise": "Late payments will accrue interest at the rate of 1.5% per month.",
        "hypothesis": "Federal Reserve lowered interest rates by 25 basis points yesterday.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_10",
        "premise": "Either party may terminate for convenience with 60 days prior written notice.",
        "hypothesis": "Email notifications are filtered automatically by spam detection filters.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_11",
        "premise": "Figure on page 3: Quarterly Revenue. Description: Bar chart showing revenue grew from $10M in Q1 to $14M in Q4.",
        "hypothesis": "The company's stock price reached an all-time high of $320 per share.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_12",
        "premise": "Table on page 2: Enterprise Tier | 50 seats | $4,000/mo | Dedicated support",
        "hypothesis": "Enterprise customers receive free branded coffee mugs during onboarding.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_13",
        "premise": "Vendor must notify customer within 24 hours of discovering a confirmed security breach.",
        "hypothesis": "The cybersecurity insurance policy covers ransomware extortion up to $5M.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_14",
        "premise": "The research team evaluated 15,000 clinical samples across 4 medical centers.",
        "hypothesis": "The research team was awarded a $2.5M NIH research grant for clinical trials.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_15",
        "premise": "Authorized representative Jane Doe signed the document on March 15, 2024.",
        "hypothesis": "Jane Doe graduated from Harvard Law School in 2012 with honors.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_16",
        "premise": "Invoice #4921 shows subtotal $1,200.00, sales tax $96.00, and balance due $1,296.00.",
        "hypothesis": "Accounting software was migrated to SAP S/4HANA last quarter.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_17",
        "premise": "Audit logs are retained in immutable storage for a minimum of 7 years.",
        "hypothesis": "Hard drive storage media is demagnetized before physical disposal.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_18",
        "premise": "The proposed neural model achieved 92.4% F1 score on the biomedical benchmark.",
        "hypothesis": "GPU cluster training consumed 400 megawatt-hours of renewable solar energy.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_19",
        "premise": "Consulting services will be delivered remotely from Seattle, Washington.",
        "hypothesis": "Seattle average annual rainfall exceeded historical records in 2024.",
        "ground_truth": "unsupported",
    },
    {
        "id": "unsup_20",
        "premise": "The security deposit of $10,000 is refundable within 30 days of lease expiration.",
        "hypothesis": "The commercial building features a rooftop solar panel installation.",
        "ground_truth": "unsupported",
    },
]


def evaluate_dataset(dataset_name: str, pairs: List[Dict[str, Any]]):
    print(f"\n--- {dataset_name} ({len(pairs)} Pairs) ---")
    stopwords = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "with",
        "for",
        "of",
        "in",
        "on",
        "to",
        "at",
        "by",
        "from",
        "it",
        "its",
        "as",
        "that",
        "this",
        "these",
        "those",
    }

    classes = ["supported", "contradicted", "unsupported"]
    ngram_cm = {gt: {pr: 0 for pr in classes} for gt in classes}
    nli_heuristic_cm = {gt: {pr: 0 for pr in classes} for gt in classes}
    nli_model_cm = {gt: {pr: 0 for pr in classes} for gt in classes}

    for item in pairs:
        gt = item["ground_truth"]
        premise = item["premise"]
        hypothesis = item["hypothesis"]

        # Word overlap
        hyp_tokens = set(re.findall(r"\b[a-z0-9]{3,}\b", hypothesis.lower())) - stopwords
        prem_tokens = set(re.findall(r"\b[a-z0-9]{3,}\b", premise.lower())) - stopwords
        overlap = len(hyp_tokens & prem_tokens) / max(len(hyp_tokens), 1)

        # Baseline 1: Naive N-Gram Overlap
        ngram_pred = "supported" if overlap >= 0.35 else "unsupported"
        ngram_cm[gt][ngram_pred] += 1

        # Baseline 2: Heuristic NLI Screen
        heur_status, _, _ = check_nli_entailment(premise, hypothesis, overlap, force_heuristic=True)
        nli_heuristic_cm[gt][heur_status] += 1

        # Baseline 3: Trained CrossEncoder NLI (with heuristic fallback if unconfigured)
        model_status, _, _ = check_nli_entailment(premise, hypothesis, overlap, force_heuristic=False)
        nli_model_cm[gt][model_status] += 1

    def calc_metrics(cm):
        total = sum(sum(row.values()) for row in cm.values())
        correct = sum(cm[c][c] for c in classes)
        accuracy = (correct / total) * 100

        tp = cm["supported"]["supported"]
        fp = cm["contradicted"]["supported"] + cm["unsupported"]["supported"]
        fn = cm["supported"]["contradicted"] + cm["supported"]["unsupported"]
        prec = (tp / max(tp + fp, 1)) * 100
        rec = (tp / max(tp + fn, 1)) * 100
        f1 = (2 * prec * rec) / max(prec + rec, 1e-6)

        c_tp = cm["contradicted"]["contradicted"]
        c_fn = cm["contradicted"]["supported"] + cm["contradicted"]["unsupported"]
        c_rec = (c_tp / max(c_tp + c_fn, 1)) * 100

        return {
            "accuracy": accuracy,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "contra_recall": c_rec,
        }

    m_ngram = calc_metrics(ngram_cm)
    m_heur = calc_metrics(nli_heuristic_cm)
    m_model = calc_metrics(nli_model_cm)

    print("| Engine | Accuracy | Support Precision | Support Recall | Support F1 | Contradiction Catch Rate |")
    print("| :--- | :---: | :---: | :---: | :---: | :---: |")
    print(
        f"| Naive N-Gram Overlap | {m_ngram['accuracy']:.1f}% | {m_ngram['precision']:.1f}% | {m_ngram['recall']:.1f}% | {m_ngram['f1']:.1f}% | {m_ngram['contra_recall']:.1f}% |"
    )
    print(
        f"| **Veridocs Heuristic NLI** | **{m_heur['accuracy']:.1f}%** | **{m_heur['precision']:.1f}%** | **{m_heur['recall']:.1f}%** | **{m_heur['f1']:.1f}%** | **{m_heur['contra_recall']:.1f}%** |"
    )
    print(
        f"| **Veridocs Model/CrossEncoder** | **{m_model['accuracy']:.1f}%** | **{m_model['precision']:.1f}%** | **{m_model['recall']:.1f}%** | **{m_model['f1']:.1f}%** | **{m_model['contra_recall']:.1f}%** |"
    )

    return m_heur


def run_verification_eval():
    print("=" * 80)
    print("VERIDOCS CLAIM GROUNDING & NLI VERIFICATION BENCHMARK")
    print(f"Total: {len(LABELED_PAIRS)} Labeled Pairs (Split into 30 Dev / 30 Held-Out)")
    print("=" * 80)

    # Split into Dev (pairs 1-10) and Held-Out (pairs 11-20)
    dev_pairs = [p for p in LABELED_PAIRS if int(p["id"].split("_")[1]) <= 10]
    held_out_pairs = [p for p in LABELED_PAIRS if int(p["id"].split("_")[1]) > 10]

    evaluate_dataset("DEVELOPMENT SET (Tuning & Validation)", dev_pairs)
    evaluate_dataset("HELD-OUT EVALUATION SET (Final Test - Never Tuned On)", held_out_pairs)


if __name__ == "__main__":
    run_verification_eval()
