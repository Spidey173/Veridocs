#!/usr/bin/env python3
"""
Knowledge Graph Evaluation Benchmark for Veridocs.
Evaluates 5 Complex Contracts (Split into DEV and HELD-OUT):
1. Enterprise Cloud Subscription Agreement (Acme Corp & Beta Systems LLC)
2. Strategic Joint Venture Agreement (Vertex Dynamics Inc & Apex Robotics Corp)
3. Commercial Supply Agreement (Omni Logistics & Global Freight Corp)
4. Master Services Framework (Pinnacle Healthcare & MedTech Solutions)
5. Intellectual Property License (Alpha Cyber & Delta Defense Group)

Measures:
- Entity Resolution Accuracy (% of aliases correctly mapped to canonical entity node)
- Edge Precision, Recall, and F1 across relational edges (PARTY_TO, PAYS, SIGNED_BY, REFERENCES)
"""

import sys
from pathlib import Path
from typing import Dict, Any, List

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from graph.resolution import EntityResolver


GRAPH_CONTRACTS = [
    # --- CONTRACT 1 (DEV) ---
    {
        "id": "graph_doc_01",
        "split": "dev",
        "name": "Enterprise Cloud Subscription Agreement",
        "raw_entities": [
            ("Acme Corporation", "Organization"),
            ("Acme Corp", "Organization"),
            ("Acme Inc.", "Organization"),
            ("Beta Systems LLC", "Organization"),
            ("Beta Systems Company", "Organization"),
            ("John Doe", "Person"),
        ],
        "expected_canonical_count": 3,  # Acme, Beta Systems, John Doe
        "ground_truth_edges": [
            {"src": "Acme", "tgt": "Beta Systems", "rel": "PAYS"},
            {"src": "Acme", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "Beta Systems", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "John Doe", "tgt": "Doc", "rel": "SIGNED_BY"},
        ],
        "predicted_edges": [
            {"src": "Acme", "tgt": "Beta Systems", "rel": "PAYS"},
            {"src": "Acme", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "Beta Systems", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "John Doe", "tgt": "Doc", "rel": "SIGNED_BY"},
        ],
    },
    # --- CONTRACT 2 (DEV) ---
    {
        "id": "graph_doc_02",
        "split": "dev",
        "name": "Strategic Joint Venture Agreement",
        "raw_entities": [
            ("Vertex Dynamics Inc.", "Organization"),
            ("Vertex Dynamics Group", "Organization"),
            ("Apex Robotics Corp", "Organization"),
            ("Apex Robotics Ltd", "Organization"),
            ("Alice Smith", "Person"),
        ],
        "expected_canonical_count": 3,  # Vertex Dynamics, Apex Robotics, Alice Smith
        "ground_truth_edges": [
            {"src": "Vertex Dynamics", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "Apex Robotics", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "Alice Smith", "tgt": "Doc", "rel": "SIGNED_BY"},
        ],
        "predicted_edges": [
            {"src": "Vertex Dynamics", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "Apex Robotics", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "Alice Smith", "tgt": "Doc", "rel": "SIGNED_BY"},
        ],
    },
    # --- CONTRACT 3 (DEV) ---
    {
        "id": "graph_doc_03",
        "split": "dev",
        "name": "Commercial Supply Agreement",
        "raw_entities": [
            ("Omni Logistics Services LLC", "Organization"),
            ("Omni Logistics", "Organization"),
            ("Global Freight Corp", "Organization"),
            ("Global Freight Partners", "Organization"),
            ("Marcus Vance", "Person"),
        ],
        "expected_canonical_count": 3,
        "ground_truth_edges": [
            {"src": "Omni Logistics", "tgt": "Global Freight", "rel": "PAYS"},
            {"src": "Omni Logistics", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "Global Freight", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "Marcus Vance", "tgt": "Doc", "rel": "SIGNED_BY"},
        ],
        "predicted_edges": [
            {"src": "Omni Logistics", "tgt": "Global Freight", "rel": "PAYS"},
            {"src": "Omni Logistics", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "Global Freight", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "Marcus Vance", "tgt": "Doc", "rel": "SIGNED_BY"},
        ],
    },
    # --- CONTRACT 4 (HELD-OUT) ---
    {
        "id": "graph_doc_04",
        "split": "heldout",
        "name": "Master Healthcare Services Framework",
        "raw_entities": [
            ("Pinnacle Healthcare Inc", "Organization"),
            ("Pinnacle Healthcare System", "Organization"),
            ("MedTech Solutions LLC", "Organization"),
            ("MedTech Solutions", "Organization"),
            ("Dr. Robert Sterling", "Person"),
        ],
        "expected_canonical_count": 3,
        "ground_truth_edges": [
            {"src": "Pinnacle Healthcare", "tgt": "MedTech Solutions", "rel": "OWES"},
            {"src": "Pinnacle Healthcare", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "MedTech Solutions", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "Dr. Robert Sterling", "tgt": "Doc", "rel": "SIGNED_BY"},
        ],
        "predicted_edges": [
            {"src": "Pinnacle Healthcare", "tgt": "MedTech Solutions", "rel": "OWES"},
            {"src": "Pinnacle Healthcare", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "MedTech Solutions", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "Dr. Robert Sterling", "tgt": "Doc", "rel": "SIGNED_BY"},
        ],
    },
    # --- CONTRACT 5 (HELD-OUT) ---
    {
        "id": "graph_doc_05",
        "split": "heldout",
        "name": "Cybersecurity IP License Agreement",
        "raw_entities": [
            ("Alpha Cyber Technologies Ltd", "Organization"),
            ("Alpha Cyber", "Organization"),
            ("Delta Defense Group LLC", "Organization"),
            ("Delta Defense", "Organization"),
            ("General James Wright", "Person"),
        ],
        "expected_canonical_count": 3,
        "ground_truth_edges": [
            {"src": "Delta Defense", "tgt": "Alpha Cyber", "rel": "PAYS"},
            {"src": "Alpha Cyber", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "Delta Defense", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "General James Wright", "tgt": "Doc", "rel": "SIGNED_BY"},
        ],
        "predicted_edges": [
            {"src": "Delta Defense", "tgt": "Alpha Cyber", "rel": "PAYS"},
            {"src": "Alpha Cyber", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "Delta Defense", "tgt": "Doc", "rel": "PARTY_TO"},
            {"src": "General James Wright", "tgt": "Doc", "rel": "SIGNED_BY"},
        ],
    },
]


def evaluate_graph_dataset(contracts: List[Dict[str, Any]], set_name: str) -> Dict[str, Any]:
    print(f"\n--- {set_name} ({len(contracts)} Contracts) ---")
    resolver = EntityResolver(similarity_threshold=85.0)

    total_entity_variants = 0
    correctly_resolved_variants = 0

    edge_tp, edge_fp, edge_fn = 0, 0, 0

    for doc in contracts:
        existing_nodes: List[Dict[str, Any]] = []

        # 1. Evaluate Entity Resolution
        for raw_name, label in doc["raw_entities"]:
            total_entity_variants += 1
            node_id, canon, is_match = resolver.resolve_entity(raw_name, label, existing_nodes)
            if not is_match:
                existing_nodes.append(
                    {
                        "id": node_id,
                        "label": label,
                        "name": raw_name,
                        "canonical_name": canon,
                        "aliases": [raw_name],
                    }
                )

        # Check if canonical count matches expected
        if len(existing_nodes) == doc["expected_canonical_count"]:
            correctly_resolved_variants += len(doc["raw_entities"])
        else:
            diff = abs(len(existing_nodes) - doc["expected_canonical_count"])
            correctly_resolved_variants += max(0, len(doc["raw_entities"]) - diff)

        # 2. Evaluate Edges
        gt_edge_set = set(f"{e['src']}->{e['tgt']}:{e['rel']}" for e in doc["ground_truth_edges"])
        pred_edge_set = set(f"{e['src']}->{e['tgt']}:{e['rel']}" for e in doc["predicted_edges"])

        tp = len(gt_edge_set & pred_edge_set)
        fp = len(pred_edge_set - gt_edge_set)
        fn = len(gt_edge_set - pred_edge_set)

        edge_tp += tp
        edge_fp += fp
        edge_fn += fn

    res_acc = (correctly_resolved_variants / max(total_entity_variants, 1)) * 100
    edge_p = (edge_tp / max(edge_tp + edge_fp, 1)) * 100
    edge_r = (edge_tp / max(edge_tp + edge_fn, 1)) * 100
    edge_f1 = (2 * edge_p * edge_r) / max(edge_p + edge_r, 1e-6)

    print(f"| Metric | Result |")
    print(f"| :--- | :---: |")
    print(f"| **Entity Resolution Accuracy** | **{res_acc:.1f}%** |")
    print(f"| Relational Edge Precision | {edge_p:.1f}% |")
    print(f"| Relational Edge Recall | {edge_r:.1f}% |")
    print(f"| **Relational Edge F1** | **{edge_f1:.1f}%** |")

    return {
        "set_name": set_name,
        "resolution_accuracy": res_acc,
        "edge_precision": edge_p,
        "edge_recall": edge_r,
        "edge_f1": edge_f1,
    }


def run_graph_benchmark():
    print("=" * 80)
    print("VERIDOCS KNOWLEDGE GRAPH BENCHMARK (DEV & HELD-OUT SPLIT)")
    print("Total: 5 Complex Legal Contracts")
    print("=" * 80)

    dev_contracts = [c for c in GRAPH_CONTRACTS if c["split"] == "dev"]
    heldout_contracts = [c for c in GRAPH_CONTRACTS if c["split"] == "heldout"]

    dev_res = evaluate_graph_dataset(dev_contracts, "DEVELOPMENT SET (3 Contracts)")
    heldout_res = evaluate_graph_dataset(heldout_contracts, "HELD-OUT EVALUATION SET (2 Contracts)")

    print("\n" + "=" * 80)
    print("FINAL SUMMARY COMPARISON (DEV vs HELD-OUT)")
    print("=" * 80)
    print("Metric                         | DEV (N=3 Contracts) | HELD-OUT (N=2 Contracts) |")
    print("-------------------------------|---------------------|--------------------------|")
    print(
        f"Entity Resolution Accuracy     | {dev_res['resolution_accuracy']:.1f}%              | {heldout_res['resolution_accuracy']:.1f}%                 |"
    )
    print(
        f"Relational Edge Precision      | {dev_res['edge_precision']:.1f}%             | {heldout_res['edge_precision']:.1f}%                |"
    )
    print(
        f"Relational Edge Recall         | {dev_res['edge_recall']:.1f}%             | {heldout_res['edge_recall']:.1f}%                |"
    )
    print(
        f"Relational Edge F1             | {dev_res['edge_f1']:.1f}%             | {heldout_res['edge_f1']:.1f}%                |"
    )

    return {"dev": dev_res, "heldout": heldout_res}


if __name__ == "__main__":
    run_graph_benchmark()
