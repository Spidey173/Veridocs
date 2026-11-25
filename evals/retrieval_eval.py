#!/usr/bin/env python3
"""
Retrieval Evaluation Benchmark for Veridocs.
Compares:
1. Vector-Only (Dense FastEmbed Cosine Similarity)
2. BM25 / Full-Text Search (Sparse Lexical Ranking)
3. Hybrid RRF (Reciprocal Rank Fusion)
Measures Recall@5 and Mean Reciprocal Rank (MRR) across 20 labeled test queries.
"""

import sys
import re
from pathlib import Path
from typing import Dict, Any, List
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from config import get_model_registry
from vector_store import get_query_embedding, compute_rrf


# 20 Diverse Corpus Documents (Text, Tables, Figures, Invoices, Contracts)
CORPUS = [
    {
        "id": "c_01_sla",
        "doc": "contract_sla.pdf",
        "page": 1,
        "chunk_type": "text",
        "text": "Availability SLA. Provider guarantees a 99.9% uptime SLA for all core database services. Service credits apply for downtime exceeding 43 minutes per calendar month.",
    },
    {
        "id": "c_02_liability",
        "doc": "contract_sla.pdf",
        "page": 2,
        "chunk_type": "text",
        "text": "Limitation of Liability. Under no circumstances shall either party's aggregate liability exceed $500,000.00 for direct damages arising out of this agreement.",
    },
    {
        "id": "c_03_payment_terms",
        "doc": "contract_sla.pdf",
        "page": 3,
        "chunk_type": "text",
        "text": "Payment Terms and Invoicing. Invoices are issued on the first calendar day of each month and are payable strictly Net 30 days from invoice receipt.",
    },
    {
        "id": "c_04_encryption",
        "doc": "security_policy.pdf",
        "page": 1,
        "chunk_type": "text",
        "text": "Data Encryption Standards. All sensitive customer records must be encrypted using AES-256 for data at rest and TLS 1.3 for data in transit.",
    },
    {
        "id": "c_05_retention",
        "doc": "security_policy.pdf",
        "page": 2,
        "chunk_type": "text",
        "text": "Audit Log Retention. System audit logs, authentication records, and access histories must be archived in write-once-read-many storage for a minimum of 7 years.",
    },
    {
        "id": "c_06_pricing_table",
        "doc": "service_tiers.pdf",
        "page": 1,
        "chunk_type": "table",
        "text": "| Tier | Monthly Fee | Max Seats | Storage | Dedicated Support |\n| Starter | $499 | 10 | 100 GB | No |\n| Professional | $1,499 | 25 | 500 GB | Yes (Email) |\n| Enterprise | $3,999 | 100 | 2 TB | Yes (Dedicated CSM) |",
    },
    {
        "id": "c_07_balance_sheet_table",
        "doc": "balance_sheet.pdf",
        "page": 1,
        "chunk_type": "table",
        "text": "| Asset Category | Q1 2024 | Q2 2024 | Q3 2024 | Q4 2024 |\n| Cash and Equivalents | $12.4M | $14.1M | $16.8M | $18.2M |\n| Accounts Receivable | $4.2M | $4.8M | $5.1M | $5.5M |\n| Total Current Assets | $16.6M | $18.9M | $21.9M | $23.7M |",
    },
    {
        "id": "c_08_revenue_figure",
        "doc": "annual_report.pdf",
        "page": 4,
        "chunk_type": "figure",
        "text": "Figure on page 4: Annual Revenue Growth 2020-2024. Description: Line chart showing cloud subscription revenue accelerating from $45M in 2020 to $128M in 2024.",
    },
    {
        "id": "c_09_cloud_architecture_figure",
        "doc": "system_design.pdf",
        "page": 2,
        "chunk_type": "figure",
        "text": "Figure on page 2: Multi-Region Failover Architecture. Description: Diagram detailing automated traffic routing between US-East and US-West clusters with cross-region pgvector replication.",
    },
    {
        "id": "c_10_invoice_inv901",
        "doc": "invoice_inv901.pdf",
        "page": 1,
        "chunk_type": "text",
        "text": "INVOICE #INV-9012. Vendor: Acme Cloud Infrastructure. Bill to: Global Retail Corp. Cloud Virtual Machines: Qty 4 @ $600.00 = $2,400.00. Total Balance Due: $2,400.00.",
    },
    {
        "id": "c_11_invoice_inv882",
        "doc": "invoice_inv882.pdf",
        "page": 1,
        "chunk_type": "text",
        "text": "INVOICE #VT-8821. Vendor: Vertex Freight Logistics. International ocean freight forwarding: Qty 1 @ $8,750.00 = $8,750.00. Payment due upon receipt.",
    },
    {
        "id": "c_12_scanned_receipt",
        "doc": "scanned_receipt.pdf",
        "page": 1,
        "chunk_type": "text",
        "text": "OFFICE DEPOT STORE #402. Cash register transaction #9910. Ergonomic standing desk: $450.00. Desk mat: $35.00. Total paid via Mastercard: $485.00.",
    },
    {
        "id": "c_13_termination",
        "doc": "contract_sla.pdf",
        "page": 4,
        "chunk_type": "text",
        "text": "Termination for Convenience. Either party may terminate this agreement without cause by providing at least 60 calendar days advance written notice.",
    },
    {
        "id": "c_14_governing_law",
        "doc": "contract_sla.pdf",
        "page": 5,
        "chunk_type": "text",
        "text": "Jurisdiction and Governing Law. Any dispute, claim, or controversy shall be governed by and construed in accordance with the laws of the State of Delaware.",
    },
    {
        "id": "c_15_confidentiality",
        "doc": "nda_agreement.pdf",
        "page": 1,
        "chunk_type": "text",
        "text": "Confidentiality Obligations. The Receiving Party shall protect proprietary trade secrets with the same degree of care for a duration of 5 years from disclosure.",
    },
    {
        "id": "c_16_bio_paper",
        "doc": "crispr_study.pdf",
        "page": 1,
        "chunk_type": "text",
        "text": "CRISPR-Cas9 Therapeutic Precision. Synthetic guide RNA modifications increased on-target genomic cleavage efficiency by 38.4% across 1,200 cell cultures.",
    },
    {
        "id": "c_17_nli_paper",
        "doc": "nli_retrieval.pdf",
        "page": 1,
        "chunk_type": "text",
        "text": "Verifiable Document RAG via Two-Stage NLI. Combining cheap token screening with cross-encoder entailment prunes 94.2% of hallucinated citations without LLM cost.",
    },
    {
        "id": "c_18_employee_resume",
        "doc": "resume_smith.pdf",
        "page": 1,
        "chunk_type": "text",
        "text": "Lead Infrastructure Engineer with 10 years experience optimizing PostgreSQL, Redis, FastAPI, and Kubernetes cluster orchestration.",
    },
    {
        "id": "c_19_indemnification",
        "doc": "contract_sla.pdf",
        "page": 6,
        "chunk_type": "text",
        "text": "Intellectual Property Indemnification. Provider shall defend Customer against any third-party claims alleging that the software infringes any US patent or copyright.",
    },
    {
        "id": "c_20_service_credits",
        "doc": "contract_sla.pdf",
        "page": 1,
        "chunk_type": "text",
        "text": "Service Credit Calculation. Monthly uptime below 99.0% entitles Customer to a 25% credit against the applicable monthly service subscription fee.",
    },
]


# 20 Realistic Test Queries with Ground Truth Target IDs
TEST_QUERIES = [
    {"query": "What is the guaranteed monthly uptime SLA?", "target": "c_01_sla"},
    {"query": "What is the maximum cumulative liability cap?", "target": "c_02_liability"},
    {"query": "What are the standard payment terms for invoices?", "target": "c_03_payment_terms"},
    {"query": "How is customer data encrypted at rest and in transit?", "target": "c_04_encryption"},
    {"query": "How long must system audit logs be retained?", "target": "c_05_retention"},
    {
        "query": "How much does the Enterprise tier cost and how many seats are included?",
        "target": "c_06_pricing_table",
    },
    {"query": "What was the total cash and equivalents in Q4 2024?", "target": "c_07_balance_sheet_table"},
    {"query": "What does the revenue growth chart show between 2020 and 2024?", "target": "c_08_revenue_figure"},
    {
        "query": "How does multi-region failover and pgvector replication work?",
        "target": "c_09_cloud_architecture_figure",
    },
    {"query": "What is the total balance due on invoice INV-9012?", "target": "c_10_invoice_inv901"},
    {"query": "What is the freight forwarding fee for invoice VT-8821?", "target": "c_11_invoice_inv882"},
    {"query": "How much was paid for the ergonomic standing desk at Office Depot?", "target": "c_12_scanned_receipt"},
    {"query": "How much advance notice is required to terminate for convenience?", "target": "c_13_termination"},
    {"query": "Which state's laws govern this contract agreement?", "target": "c_14_governing_law"},
    {"query": "How long do the confidentiality obligations survive?", "target": "c_15_confidentiality"},
    {"query": "By what percentage did modified guide RNA increase cleavage efficiency?", "target": "c_16_bio_paper"},
    {"query": "How does two-stage NLI prune hallucinated citations?", "target": "c_17_nli_paper"},
    {
        "query": "How many years of experience does the candidate have in PostgreSQL and Kubernetes?",
        "target": "c_18_employee_resume",
    },
    {
        "query": "Who is responsible for intellectual property patent infringement defense?",
        "target": "c_19_indemnification",
    },
    {
        "query": "What service credit percentage is provided if uptime drops below 99%?",
        "target": "c_20_service_credits",
    },
]


def evaluate_retrieval_dataset(
    dataset_name: str, queries: List[Dict[str, Any]], corpus_embeddings, chunk_ids, stopwords
):
    print(f"\n--- {dataset_name} ({len(queries)} Queries) ---")

    metrics = {
        "vector_only": {"hits_top5": 0, "reciprocal_ranks": []},
        "bm25_sparse": {"hits_top5": 0, "reciprocal_ranks": []},
        "hybrid_rrf": {"hits_top5": 0, "reciprocal_ranks": []},
    }

    for item in queries:
        query = item["query"]
        target = item["target"]

        # 1. Vector Dense Cosine Ranking
        q_emb = get_query_embedding(query)
        dense_scores = np.dot(corpus_embeddings, q_emb)
        dense_ranked_indices = np.argsort(dense_scores)[::-1]
        dense_ranked_ids = [chunk_ids[i] for i in dense_ranked_indices]

        # 2. Sparse Lexical BM25/FTS Ranking
        q_tokens = set(re.findall(r"\b[a-z0-9]{2,}\b", query.lower())) - stopwords
        sparse_scores = []
        for c in CORPUS:
            c_tokens = set(re.findall(r"\b[a-z0-9]{2,}\b", c["text"].lower()))
            overlap = len(q_tokens & c_tokens)
            # Boost exact phrase / code matches like "INV-9012" or "99.9%"
            for qt in q_tokens:
                if len(qt) >= 4 and qt in c["text"].lower():
                    overlap += 2
            sparse_scores.append(overlap)
        sparse_ranked_indices = np.argsort(np.array(sparse_scores))[::-1]
        sparse_ranked_ids = [chunk_ids[i] for i in sparse_ranked_indices if sparse_scores[i] > 0]

        # 3. Hybrid RRF Ranking
        rrf_dict = compute_rrf(dense_ranked_ids, sparse_ranked_ids, k=60)
        hybrid_ranked_ids = sorted(rrf_dict.keys(), key=lambda cid: rrf_dict[cid], reverse=True)

        # Evaluate Vector Only
        top5_dense = dense_ranked_ids[:5]
        if target in top5_dense:
            metrics["vector_only"]["hits_top5"] += 1
            rank = dense_ranked_ids.index(target) + 1
            metrics["vector_only"]["reciprocal_ranks"].append(1.0 / rank)
        else:
            metrics["vector_only"]["reciprocal_ranks"].append(0.0)

        # Evaluate BM25/Sparse Only
        top5_sparse = sparse_ranked_ids[:5]
        if target in top5_sparse:
            metrics["bm25_sparse"]["hits_top5"] += 1
            rank = sparse_ranked_ids.index(target) + 1
            metrics["bm25_sparse"]["reciprocal_ranks"].append(1.0 / rank)
        else:
            metrics["bm25_sparse"]["reciprocal_ranks"].append(0.0)

        # Evaluate Hybrid RRF
        top5_hybrid = hybrid_ranked_ids[:5]
        if target in top5_hybrid:
            metrics["hybrid_rrf"]["hits_top5"] += 1
            rank = hybrid_ranked_ids.index(target) + 1
            metrics["hybrid_rrf"]["reciprocal_ranks"].append(1.0 / rank)
        else:
            metrics["hybrid_rrf"]["reciprocal_ranks"].append(0.0)

    n_q = len(queries)

    v_recall = (metrics["vector_only"]["hits_top5"] / n_q) * 100
    v_mrr = float(np.mean(metrics["vector_only"]["reciprocal_ranks"]))

    b_recall = (metrics["bm25_sparse"]["hits_top5"] / n_q) * 100
    b_mrr = float(np.mean(metrics["bm25_sparse"]["reciprocal_ranks"]))

    h_recall = (metrics["hybrid_rrf"]["hits_top5"] / n_q) * 100
    h_mrr = float(np.mean(metrics["hybrid_rrf"]["reciprocal_ranks"]))

    print(f"| Strategy | Recall@5 | MRR |")
    print(f"| :--- | :---: | :---: |")
    print(f"| Vector-Only | {v_recall:.1f}% | {v_mrr:.3f} |")
    print(f"| BM25/Sparse | {b_recall:.1f}% | {b_mrr:.3f} |")
    print(f"| **Hybrid RRF** | **{h_recall:.1f}%** | **{h_mrr:.3f}** |")

    return {
        "dataset": dataset_name,
        "vector_only": {"recall@5": v_recall, "mrr": v_mrr},
        "bm25_sparse": {"recall@5": b_recall, "mrr": b_mrr},
        "hybrid_rrf": {"recall@5": h_recall, "mrr": h_mrr},
    }


def run_retrieval_benchmark():
    print("=" * 80)
    print("VERIDOCS RETRIEVAL EVALUATION BENCHMARK (DEV & HELD-OUT SPLIT)")
    print(f"Corpus: {len(CORPUS)} Chunks (Text, Tables, Figures)")
    print(f"Total Queries: {len(TEST_QUERIES)} Labeled Questions")
    print("=" * 80)

    reg = get_model_registry()
    texts = [c["text"] for c in CORPUS]
    raw_embeddings = list(reg.embedding_model.embed(texts))
    corpus_embeddings = np.array([e / np.linalg.norm(e) for e in raw_embeddings], dtype=np.float32)

    chunk_ids = [c["id"] for c in CORPUS]

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
        "how",
        "what",
        "which",
        "does",
        "do",
        "and",
    }

    # Split into 10 DEV queries and 10 HELD-OUT queries
    dev_queries = TEST_QUERIES[:10]
    heldout_queries = TEST_QUERIES[10:]

    dev_results = evaluate_retrieval_dataset(
        "DEV SET (Tuning/Reference)", dev_queries, corpus_embeddings, chunk_ids, stopwords
    )
    heldout_results = evaluate_retrieval_dataset(
        "HELD-OUT SET (Generalization Evaluation)", heldout_queries, corpus_embeddings, chunk_ids, stopwords
    )

    print("\n" + "=" * 80)
    print("FINAL SUMMARY COMPARISON (DEV vs HELD-OUT)")
    print("=" * 80)
    print(f"Retrieval Strategy             | DEV Recall@5 / MRR | HELD-OUT Recall@5 / MRR |")
    print(f"-------------------------------|--------------------|-------------------------|")
    print(
        f"Vector-Only (Dense Cosine)     | {dev_results['vector_only']['recall@5']:.1f}% / {dev_results['vector_only']['mrr']:.3f}    | {heldout_results['vector_only']['recall@5']:.1f}% / {heldout_results['vector_only']['mrr']:.3f}       |"
    )
    print(
        f"BM25 / Sparse Keyword          | {dev_results['bm25_sparse']['recall@5']:.1f}% / {dev_results['bm25_sparse']['mrr']:.3f}    | {heldout_results['bm25_sparse']['recall@5']:.1f}% / {heldout_results['bm25_sparse']['mrr']:.3f}       |"
    )
    print(
        f"**Hybrid RRF (Dense + Sparse)**| **{dev_results['hybrid_rrf']['recall@5']:.1f}% / {dev_results['hybrid_rrf']['mrr']:.3f}** | **{heldout_results['hybrid_rrf']['recall@5']:.1f}% / {heldout_results['hybrid_rrf']['mrr']:.3f}**   |"
    )

    return {
        "dev": dev_results,
        "heldout": heldout_results,
    }


if __name__ == "__main__":
    run_retrieval_benchmark()
