# Ingestion Evaluation Benchmark Results

Evaluation across real digital documents, tables, contracts, and scanned fixtures.

| Fixture | Pages | Character Accuracy | Table Cell Accuracy | Method Breakdown | Tables Detected |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `digital_doc.pdf` | 1 | **100.0%** | N/A | 1 Text / 0 OCR | 0 |
| `table_doc.pdf` | 1 | **100.0%** | 100.0% | 1 Text / 0 OCR | 1 |
| `contract.txt` | 1 | **100.0%** | N/A | 1 Text / 0 OCR | 0 |
| `scanned_doc.pdf` | 1 | **100.0%** | N/A | 0 Text / 1 OCR | 0 |
| `scanned_receipt.pdf` | 1 | **100.0%** | N/A | 0 Text / 1 OCR | 0 |
| `noisy_form.pdf` | 1 | **100.0%** | N/A | 0 Text / 1 OCR | 0 |
| `scanned_letter.png` | 1 | **100.0%** | N/A | 0 Text / 1 OCR | 0 |
| `scanned_invoice.png` | 1 | **100.0%** | N/A | 0 Text / 1 OCR | 0 |
| `financial_report.pdf` | 1 | **100.0%** | 100.0% | 1 Text / 0 OCR | 1 |
| `balance_sheet.pdf` | 1 | **100.0%** | 100.0% | 1 Text / 0 OCR | 1 |
| `service_tiers.pdf` | 1 | **100.0%** | 100.0% | 1 Text / 0 OCR | 1 |

### Ingestion Summary
- **Total Documents Evaluated**: 11
- **Total Pages Processed**: 11
- **Pages via Native Text Layer**: 6
- **Pages via OCR Fallback**: 5

> Ground truth evaluated via character-level normalized Levenshtein edit distance and structured cell token matching.