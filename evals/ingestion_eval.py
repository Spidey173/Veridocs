#!/usr/bin/env python3
"""
Ingestion Evaluation Benchmark for Veridocs.
Evaluates character accuracy, table cell accuracy, and OCR vs text-layer breakdown across fixtures.
Outputs results table to console and writes evals/results.md.
"""

import sys
import re
from pathlib import Path
from typing import Dict, Any, List

# Ensure backend is on sys.path
repo_root = Path(__file__).resolve().parent.parent
backend_dir = repo_root / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from ingestion.router import parse_document
from ingestion.base import ParsedDocument

FIXTURES_DIR = repo_root / "tests" / "fixtures"
EVALS_DIR = repo_root / "evals"
EVALS_DIR.mkdir(parents=True, exist_ok=True)


def levenshtein_distance(s1: str, s2: str) -> int:
    """Standard dynamic programming Levenshtein distance."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def normalize_text(text: str) -> str:
    """Normalize whitespace and lower case for fair character evaluation."""
    return " ".join(re.sub(r"[\r\n\t]+", " ", text).strip().split()).lower()


def compute_char_accuracy(extracted: str, ground_truth: str) -> float:
    norm_ext = normalize_text(extracted)
    norm_gt = normalize_text(ground_truth)
    if not norm_gt:
        return 1.0 if not norm_ext else 0.0

    dist = levenshtein_distance(norm_ext, norm_gt)
    max_len = max(len(norm_ext), len(norm_gt))
    if max_len == 0:
        return 1.0
    return max(0.0, 1.0 - (dist / max_len))


def compute_cell_accuracy(extracted_tables: list, expected_cells: List[List[str]]) -> float:
    """Calculate cell-by-cell accuracy against ground truth table cells."""
    if not expected_cells:
        return 1.0  # No tables expected

    if not extracted_tables:
        return 0.0

    total_expected = sum(len(row) for row in expected_cells)
    matched = 0

    # Collect all tokens from extracted tables
    extracted_text = " ".join([t.markdown for t in extracted_tables]).lower()

    for row in expected_cells:
        for cell in row:
            if cell.lower() in extracted_text:
                matched += 1

    return matched / max(total_expected, 1)


GROUND_TRUTH = {
    "digital_doc.pdf": {
        "text": "ACME Cloud Services Agreement Section 1. Payment Terms: Invoices are payable net 30 days. Section 2. Service Level: Monthly uptime SLA is 99.95 percent.",
        "tables": [],
        "expected_ocr": False,
    },
    "table_doc.pdf": {
        "text": "Pricing Tier Schedule | Tier | Storage | Monthly Cost | | Basic | 100 GB | $50 | | Pro | 1 TB | $250 | | Enterprise | Unlimited | $1200 |",
        "tables": [
            ["Tier", "Storage", "Monthly Cost"],
            ["Basic", "100 GB", "$50"],
            ["Pro", "1 TB", "$250"],
            ["Enterprise", "Unlimited", "$1200"],
        ],
        "expected_ocr": False,
    },
    "contract.txt": {
        "text": "MASTER SERVICES AGREEMENT SECTION 1. SCOPE OF SERVICES Provider agrees to deliver managed document AI processing and validation. SECTION 2. PRICING AND PAYMENTS Ingestion rate is $0.05 per document OCR. Storage rate is $0.20 monthly per GB. Invoices shall be payable within thirty (30) days of the date of invoice. SECTION 3. CONFIDENTIALITY Each party agrees to hold all confidential information in strict confidence.",
        "tables": [],
        "expected_ocr": False,
    },
    "scanned_doc.pdf": {
        "text": "CONFIDENTIAL DISCLOSURE NOTICE Authorized personnel only. Data retention: 7 years. Penalty for unauthorized disclosure: $100,000 fine.",
        "tables": [],
        "expected_ocr": True,
    },
    "scanned_receipt.pdf": {
        "text": "GROCERY DEPOT Receipt #8821 Date: 2026-11-20 Organic Milk $4.50 Whole Wheat Bread $3.25 Subtotal: $7.75 Tax: $0.62 Total: $8.37 Thank you for shopping with us!",
        "tables": [],
        "expected_ocr": True,
    },
    "noisy_form.pdf": {
        "text": "EMPLOYEE ENROLLMENT FORM Name: Jane Doe Department: Engineering Start Date: 2026-12-01 Status: Full-Time Approved by HR Operations.",
        "tables": [],
        "expected_ocr": True,
    },
    "scanned_letter.png": {
        "text": "GLOBAL LOGISTICS PARTNERS Board of Directors Resolution The board has unanimously resolved to approve the international fulfillment expansion plan effective Q1 2027.",
        "tables": [],
        "expected_ocr": True,
    },
    "scanned_invoice.png": {
        "text": "INVOICE #INV-2026-904 Customer: Globex Corporation Service: Enterprise Cloud License Amount Due: $14,500.00 Due Date: 2026-12-15",
        "tables": [],
        "expected_ocr": True,
    },
    "financial_report.pdf": {
        "text": "Quarterly Financial Statement | Metric | Q1 2026 | Q2 2026 | Q3 2026 | | Revenue | $12.4M | $14.1M | $15.8M | | Operating Expenses | $7.2M | $7.8M | $8.1M | | Net Income | $5.2M | $6.3M | $7.7M |",
        "tables": [
            ["Metric", "Q1 2026", "Q2 2026", "Q3 2026"],
            ["Revenue", "$12.4M", "$14.1M", "$15.8M"],
            ["Operating Expenses", "$7.2M", "$7.8M", "$8.1M"],
            ["Net Income", "$5.2M", "$6.3M", "$7.7M"],
        ],
        "expected_ocr": False,
    },
    "balance_sheet.pdf": {
        "text": "Consolidated Balance Sheet | Category | 2025 | 2026 | | Current Assets | $4,500,000 | $5,800,000 | | Total Liabilities | $1,800,000 | $2,100,000 | | Shareholder Equity | $2,700,000 | $3,700,000 |",
        "tables": [
            ["Category", "2025", "2026"],
            ["Current Assets", "$4,500,000", "$5,800,000"],
            ["Total Liabilities", "$1,800,000", "$2,100,000"],
            ["Shareholder Equity", "$2,700,000", "$3,700,000"],
        ],
        "expected_ocr": False,
    },
    "service_tiers.pdf": {
        "text": "Cloud Compute and Infrastructure Tiers | Plan | vCPU | RAM | Bandwidth | Price | | Starter | 2 | 4 GB | 1 TB | $20 | | Professional | 4 | 16 GB | 5 TB | $80 | | Dedicated | 16 | 64 GB | Unlimited | $350 |",
        "tables": [
            ["Plan", "vCPU", "RAM", "Bandwidth", "Price"],
            ["Starter", "2", "4 GB", "1 TB", "$20"],
            ["Professional", "4", "16 GB", "5 TB", "$80"],
            ["Dedicated", "16", "64 GB", "Unlimited", "$350"],
        ],
        "expected_ocr": False,
    },
}


def run_evaluation() -> Dict[str, Any]:
    results = []
    total_pages = 0
    pages_ocr = 0
    pages_text_layer = 0

    for fixture_name, gt in GROUND_TRUTH.items():
        fixture_path = FIXTURES_DIR / fixture_name
        if not fixture_path.exists():
            continue

        parsed: ParsedDocument = parse_document(fixture_path, filename=fixture_name)
        extracted_text = " ".join([p.text for p in parsed.pages])
        all_tables = [t for p in parsed.pages for t in p.tables]

        doc_ocr_pages = sum(1 for p in parsed.pages if p.extraction_method == "ocr")
        doc_text_pages = sum(1 for p in parsed.pages if p.extraction_method == "text_layer")

        total_pages += parsed.total_pages
        pages_ocr += doc_ocr_pages
        pages_text_layer += doc_text_pages

        char_acc = compute_char_accuracy(extracted_text, gt["text"])
        cell_acc = compute_cell_accuracy(all_tables, gt["tables"])

        results.append(
            {
                "fixture": fixture_name,
                "pages": parsed.total_pages,
                "char_accuracy": round(char_acc * 100, 1),
                "cell_accuracy": round(cell_acc * 100, 1) if gt["tables"] else "N/A",
                "extraction_methods": f"{doc_text_pages} Text / {doc_ocr_pages} OCR",
                "tables_found": len(all_tables),
            }
        )

    return {
        "items": results,
        "summary": {
            "total_documents": len(results),
            "total_pages": total_pages,
            "pages_ocr": pages_ocr,
            "pages_text_layer": pages_text_layer,
        },
    }


def format_markdown_table(data: Dict[str, Any]) -> str:
    lines = [
        "# Ingestion Evaluation Benchmark Results",
        "",
        "Evaluation across real digital documents, tables, contracts, and scanned fixtures.",
        "",
        "| Fixture | Pages | Character Accuracy | Table Cell Accuracy | Method Breakdown | Tables Detected |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ]

    for item in data["items"]:
        cell_acc_str = (
            f"{item['cell_accuracy']}%" if isinstance(item["cell_accuracy"], (int, float)) else item["cell_accuracy"]
        )
        lines.append(
            f"| `{item['fixture']}` | {item['pages']} | **{item['char_accuracy']}%** | {cell_acc_str} | {item['extraction_methods']} | {item['tables_found']} |"
        )

    s = data["summary"]
    lines.extend(
        [
            "",
            "### Ingestion Summary",
            f"- **Total Documents Evaluated**: {s['total_documents']}",
            f"- **Total Pages Processed**: {s['total_pages']}",
            f"- **Pages via Native Text Layer**: {s['pages_text_layer']}",
            f"- **Pages via OCR Fallback**: {s['pages_ocr']}",
            "",
            "> Ground truth evaluated via character-level normalized Levenshtein edit distance and structured cell token matching.",
        ]
    )
    return "\n".join(lines)


def main():
    data = run_evaluation()
    md_content = format_markdown_table(data)

    print("\n" + "=" * 80)
    print("VERIDOCS INGESTION BENCHMARK RESULTS")
    print("=" * 80)
    print(md_content)
    print("=" * 80 + "\n")

    out_file = EVALS_DIR / "results.md"
    out_file.write_text(md_content, encoding="utf-8")
    print(f"Results successfully saved to: {out_file}")


if __name__ == "__main__":
    main()
