#!/usr/bin/env python3
"""
Real-World Document Pipeline Runner for Veridocs.
Runs the complete ingestion, classification, entity, and extraction pipeline
on arbitrary real documents placed in `tests/real_docs/`.
Prints a detailed per-document diagnostics report:
- Parser backend selected (Docling vs PyMuPDF)
- Extraction methods and OCR confidence per page
- Tables reconstructed
- Document type classification & confidence
- Extracted structured fields with verified / unverified status
- Extracted entities & normalizations
- Any pipeline failures or warnings

No ground truth annotations required.
"""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from config import get_settings
from ingestion.router import parse_document, validate_and_detect_file_type
from classification.classifier import classify_document
from entities.extractor import EntityExtractor
from extraction.extractor import SchemaExtractor, run_invoice_math_checks


def run_pipeline_on_real_docs():
    settings = get_settings()
    real_docs_dir = ROOT_DIR / "tests" / "real_docs"

    if not real_docs_dir.exists():
        real_docs_dir.mkdir(parents=True, exist_ok=True)

    supported_exts = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".txt"}
    candidates = [
        p
        for p in real_docs_dir.iterdir()
        if p.is_file() and p.name != "README.md" and not p.name.startswith(".") and p.suffix.lower() in supported_exts
    ]

    print("=" * 80)
    print("VERIDOCS REAL-WORLD DOCUMENT EVALUATION RUNNER")
    print(f"Directory: {real_docs_dir}")
    print("=" * 80)

    if not candidates:
        print(f"\n[INFO] No documents found in '{real_docs_dir}'.")
        print("To test on real-world documents:")
        print("  1. Copy your real invoices, contracts, or research papers into 'tests/real_docs/'")
        print("  2. Re-run: python evals/run_on_real_docs.py")
        print("\nDemonstrating pipeline report using bundled fixture 'tests/fixtures/digital_doc.pdf':\n")
        fixture = ROOT_DIR / "tests" / "fixtures" / "digital_doc.pdf"
        if fixture.exists():
            candidates = [fixture]
        else:
            return

    extractor = EntityExtractor()
    schema_extractor = SchemaExtractor()

    for idx, doc_path in enumerate(candidates, 1):
        print("\n" + "#" * 80)
        print(f"DOCUMENT {idx}/{len(candidates)}: {doc_path.name}")
        print(f"File Size: {doc_path.stat().st_size / 1024:.1f} KB | Path: {doc_path}")
        print("#" * 80)

        # 1. Validation
        try:
            detected_format = validate_and_detect_file_type(doc_path)
            print(f"Format Validation: PASSED (Detected: {detected_format.upper()})")
        except ValueError as err:
            print(f"[REJECTED] Validation failed: {err}")
            continue

        # 2. Ingestion & Parsing
        try:
            parsed = parse_document(doc_path)
        except Exception as e:
            print(f"[ERROR] Parsing failed with exception: {e}")
            continue

        parser_name = parsed.metadata.get("parser_backend") or parsed.metadata.get("parser") or settings.PARSER_BACKEND
        print(f"Parser Backend Used: {parser_name.upper()}")
        print(f"Total Pages Extracted: {len(parsed.pages)}")

        # 3. Per-Page Breakdown (Text vs OCR)
        total_tables = 0
        text_pages = 0
        ocr_pages = 0
        ocr_confs = []

        print("\n--- Per-Page Extraction Breakdown ---")
        for p in parsed.pages:
            method = p.extraction_method
            conf_str = f"{p.ocr_confidence * 100:.1f}%" if p.ocr_confidence is not None else "N/A"
            t_count = len(p.tables) if p.tables else 0
            total_tables += t_count

            if method == "ocr":
                ocr_pages += 1
                if p.ocr_confidence is not None:
                    ocr_confs.append(p.ocr_confidence)
            else:
                text_pages += 1

            flags = []
            if p.has_figures:
                flags.append("has_figures")
            if p.has_tables:
                flags.append("has_tables")
            if getattr(p, "has_signature_block", False):
                flags.append("has_signatures")
            flag_str = f" [{', '.join(flags)}]" if flags else ""

            print(f"  Page {p.number:2d}: Method={method:<10} | OCR Conf={conf_str:<6} | Tables={t_count}{flag_str}")

        avg_ocr_conf = (sum(ocr_confs) / len(ocr_confs)) if ocr_confs else None
        print(f"Summary: {text_pages} native text pages, {ocr_pages} OCR pages.")
        if avg_ocr_conf is not None:
            print(f"Average OCR Confidence on scanned pages: {avg_ocr_conf * 100:.1f}%")

        # 4. Tables Extracted
        print(f"\n--- Tables Reconstructed ({total_tables} total) ---")
        if total_tables == 0:
            print("  No tables detected.")
        else:
            for p in parsed.pages:
                if p.tables:
                    for t_idx, tbl in enumerate(p.tables, 1):
                        lines = tbl.markdown.strip().split("\n")
                        print(f"  Page {p.number} Table {t_idx} ({len(lines)} lines):")
                        for line in lines[:4]:
                            print(f"    {line}")
                        if len(lines) > 4:
                            print(f"    ... [{len(lines) - 4} more rows]")

        # 5. Document Classification
        page_dicts = [{"page_number": p.number, "text": p.text} for p in parsed.pages]
        doc_type, conf = classify_document(page_dicts, filename=doc_path.name)
        print(f"\n--- Document Classification ---")
        print(f"  Classified Type: {doc_type.upper()} (Confidence: {conf * 100:.1f}%)")

        # 6. Entity Extraction
        full_text = "\n\n".join([p.text for p in parsed.pages])
        entities = extractor.extract_from_chunk(full_text, page_number=1, chunk_id=f"real_{idx}")
        print(f"\n--- Entities Extracted ({len(entities)} found) ---")
        by_label = {}
        for ent in entities:
            by_label.setdefault(ent["label"], []).append(ent)

        for lbl, items in sorted(by_label.items()):
            samples = [f"'{i['text']}'" + (f" -> {i['normalized']}" if i.get("normalized") else "") for i in items[:3]]
            more = f" ... and {len(items) - 3} more" if len(items) > 3 else ""
            print(f"  {lbl.capitalize():<14} ({len(items):2d}): {', '.join(samples)}{more}")

        # 7. Schema Extraction & Verbatim Evidence Verification
        print(f"\n--- Schema Extraction & Evidence Verification ({doc_type}) ---")
        extraction_res = schema_extractor.extract(
            document_id=f"real_{idx}",
            doc_type=doc_type,
            pages=page_dicts,
        )

        fields = extraction_res.get("fields", {})
        verified_count = 0
        total_fields = 0

        for f_name, f_data in fields.items():
            if isinstance(f_data, dict) and "value" in f_data:
                total_fields += 1
                is_ver = f_data.get("verified", False)
                if is_ver:
                    verified_count += 1
                ver_badge = "VERIFIED" if is_ver else "UNVERIFIED"
                val = str(f_data.get("value"))[:40]
                quote = str(f_data.get("quote", ""))[:45]
                print(f'  {f_name:<16}: [{ver_badge:<10}] {val:<40} (Quote: "{quote}")')

        if total_fields > 0:
            print(f"  Verification Ratio: {verified_count}/{total_fields} ({verified_count / total_fields * 100:.1f}%)")

        # 8. Invoice Math Checks if applicable
        if doc_type == "invoice":
            run_invoice_math_checks(fields)
            is_mismatch = fields.get("total", {}).get("math_mismatch", False)
            if is_mismatch:
                print(
                    "  [ALERT] Invoice Math Check: MISMATCH DETECTED (line items or subtotal/tax do not sum to total)"
                )
            else:
                print("  Invoice Math Check: BALANCED (subtotal + tax = total)")

    print("\n" + "=" * 80)
    print("REAL-WORLD RUN COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    run_pipeline_on_real_docs()
