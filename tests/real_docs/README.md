# Real-World Document Validation Directory

This directory is intended for dropping in real, unlabelled production documents (PDF, TIFF, PNG, JPG, TXT) to validate the end-to-end Veridocs pipeline under real-world conditions without requiring synthetic fixtures or ground-truth annotations.

---

## How to Test Real Documents

1. **Drop files into this folder**:
   Copy any real PDF, scanned agreement, receipt, invoice, or technical paper into this directory:
   ```bash
   cp /path/to/my_vendor_contract.pdf tests/real_docs/
   cp /path/to/scanned_receipt.jpg tests/real_docs/
   ```

2. **Run the evaluation script**:
   ```bash
   python evals/run_on_real_docs.py
   ```

3. **What the report will inspect**:
   For every document detected in `tests/real_docs/`, the script executes the entire pipeline:
   - **Parser Selection**: Whether Docling or PyMuPDF was used
   - **Text vs. OCR Decision**: Page-by-page breakdown and OCR confidence scores
   - **Tables Reconstructed**: Count and preview of markdown/JSON tables
   - **Vision Figures Detected**: Charts, diagrams, and signatures identified
   - **Document Classification**: Classified document category (`invoice`, `contract`, `research_paper`, `resume`, `other`)
   - **Structured Fields**: Extracted fields and verbatim evidence verification status (`verified` vs `unverified`)
   - **Entities Extracted**: Money, date, organization, and jurisdiction entities with normalization
   - **Failures / Errors**: Any stage errors or degradation notices

*All files in this folder (except this README) are strictly ignored by Git.*
