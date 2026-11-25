# Veridocs Schema Extraction & Evidence Verification Specification

Veridocs provides schema-based structured extraction for contracts, invoices, research papers, and resumes. Unlike typical RAG frameworks that produce ungrounded JSON dictionaries, Veridocs enforces a strict **verifiable evidence contract** and deterministic post-extraction verification.

---

## 1. The Evidence Contract (`FieldEvidence`)

Every extracted scalar or nested field is wrapped in a `FieldEvidence` schema:

```json
{
  "value": "Net 30 days",
  "page": 2,
  "quote": "Invoices are payable strictly Net 30 days from receipt.",
  "confidence": 0.95,
  "verified": true,
  "math_mismatch": false
}
```

### Fields Specification:
- **`value`** (`Any`): The extracted structured value (string, float, date, or list).
- **`page`** (`int`): The 1-indexed page number where the claim or value appears.
- **`quote`** (`str`): Verbatim excerpt (up to 200 characters) copied directly from the document source.
- **`confidence`** (`float`): Extraction confidence between `0.0` and `1.0`.
- **`verified`** (`bool`): Deterministically calculated. Set to `true` if and only if `quote` appears verbatim in the cited page text (case- and whitespace-normalized). If the quote is missing or hallucinated, `verified` is set to `false`.
- **`math_mismatch`** (`bool`): Flagged on financial fields when arithmetic sums do not balance within tolerance.

---

## 2. Supported Schemas

### 2.1 Invoice (`InvoiceExtraction`)
Targeted at accounts payable, invoices, and purchase orders.
- `vendor`: Vendor or service provider name (`FieldEvidence`).
- `vendor_address`: Physical or billing address of the vendor (`FieldEvidence`).
- `customer_name`: Recipient or bill-to customer name (`FieldEvidence`).
- `customer_address`: Customer billing or physical address (`FieldEvidence`).
- `invoice_number`: Unique invoice identifier or receipt number (`FieldEvidence`).
- `invoice_date`: Date of invoice issuance in ISO 8601 or text (`FieldEvidence`).
- `due_date`: Date by which payment is expected (`FieldEvidence`).
- `currency`: Currency code, e.g. USD, EUR, GBP (`FieldEvidence`).
- `line_items`: Array of line items (`InvoiceLineItem`):
  - `description`: Name or summary of service/product.
  - `quantity`: Quantity delivered/purchased.
  - `unit_price`: Rate per unit.
  - `amount`: Line item extended cost (`quantity * unit_price`).
  - `evidence`: Optional `FieldEvidence`.
- `subtotal`: Pre-tax line items subtotal (`FieldEvidence`).
- `tax`: Applicable sales tax, VAT, or GST (`FieldEvidence`).
- `total`: Total balance due (`FieldEvidence`).
- `payment_terms`: Payment duration or terms, e.g., Net 30 (`FieldEvidence`).

### 2.2 Contract (`ContractExtraction`)
Targeted at Master Service Agreements (MSAs), NDAs, commercial leases, and service agreements.
- `parties`: List of contracting corporate entities or individuals (`List[FieldEvidence]`).
- `effective_date`: Date contract takes legal effect (`FieldEvidence`).
- `term`: Duration of the agreement, e.g. 24 months, 3 years (`FieldEvidence`).
- `renewal`: Conditions for renewal or extension (`FieldEvidence`).
- `termination_clause`: Notice requirements and termination conditions (`FieldEvidence`).
- `governing_law`: Jurisdiction governing disputes, e.g. State of Delaware (`FieldEvidence`).
- `payment_terms`: Commercial payment cadence and late fees (`FieldEvidence`).
- `liability_cap`: Limitation of liability dollar limit or multiplier (`FieldEvidence`).
- `confidentiality`: Non-disclosure and trade secret restrictions (`FieldEvidence`).
- `deadlines`: Notice obligations and key contractual milestones (`List[DeadlineItem]`, each carrying `description`, `date`, `quote`, `page`, `verified`, `confidence`).
- `signatures`: Detected signature blocks and execution state (`List[FieldEvidence]`).

### 2.3 Research Paper (`ResearchPaperExtraction`)
Targeted at preprints, academic publications, and technical whitepapers.
- `title`: Paper title (`FieldEvidence`).
- `authors`: List of authors (`List[FieldEvidence]`).
- `venue`: Conference, journal, or workshop name (`FieldEvidence`).
- `year`: Publication year (`FieldEvidence`).
- `abstract`: Summary paragraph (`FieldEvidence`).
- `key_findings`: List of core experimental results or claims (`List[FieldEvidence]`).
- `datasets`: Benchmarks or datasets evaluated (`List[FieldEvidence]`).
- `limitations`: Stated model/methodology constraints (`List[FieldEvidence]`).

### 2.4 Resume (`ResumeExtraction`)
Targeted at candidate resumes and CVs.
- `candidate_name`: Candidate full name (`FieldEvidence`).
- `email`: Contact email address (`FieldEvidence`).
- `phone`: Telephone number (`FieldEvidence`).
- `current_role`: Current job title or role (`FieldEvidence`).
- `experience_years`: Total experience summary (`FieldEvidence`).
- `skills`: Technical competencies and tooling (`List[FieldEvidence]`).
- `education`: Universities, degrees, and graduation details (`List[FieldEvidence]`).

---

## 3. Deterministic Post-Extraction Checks

Veridocs never presents raw LLM JSON without post-processing verification.

### 3.1 Verbatim Quote In Page Text Verification
```python
def verify_quote_in_page_text(quote: str, page_text: str) -> bool:
    norm_page = " ".join(re.sub(r'[\r\n\t]+', ' ', page_text).split()).lower()
    norm_quote = " ".join(re.sub(r'[\r\n\t]+', ' ', quote).split()).lower()
    return norm_quote in norm_page
```
- Whitespace and linebreaks are collapsed.
- Punctuation-agnostic fallback ensures punctuation variance does not spuriously invalidate a genuine quote.
- If the quote does not exist on the cited page, `field.verified = false`.

### 3.2 Invoice Arithmetic Validation
Invoices are verified using standard arithmetic balancing:
1. **Line Items Check**:
   $$\left|\sum \text{line\_items.amount} - \text{subtotal}\right| \le 0.05$$
2. **Total Balance Check**:
   $$\left|\text{subtotal} + \text{tax} - \text{total}\right| \le 0.05$$

If either equation fails to balance within the \$0.05 tolerance, the respective field has `math_mismatch = true` and the frontend renders an amber math alert badge with an explanation.

---

## 4. User Corrections and Auditing

- Model outputs are **never** overwritten in place.
- User manual overrides submitted via `PUT /documents/{id}/extraction` are stored separately in the `user_edits` JSON column.
- The UI displays both model-derived values and human-audited values side by side.

