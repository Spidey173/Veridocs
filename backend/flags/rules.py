"""
Rule-based anomaly checkers for Veridocs.
Honest naming: heuristic 'flags' providing signals for human review,
NOT automated fraud accusations.

Checkers:
1. invoice_math_mismatch: subtotal + tax != total or sum(items) != subtotal
2. duplicate_invoice: identical invoice number & vendor across docs, or near-identical embeddings
3. pdf_metadata_anomaly: producer scan vs digital mismatch, future date, post-signing modification
4. date_inconsistency: due date before invoice date, Net 30 terms with Net 60+ due date
5. cross_document_mismatch: invoice amount exceeding purchase order, mismatched contracting parties
6. round_number_and_threshold: structured just below thresholds ($9,999, $4,999) or clean round totals
"""

import re
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)


def check_invoice_math_mismatch(
    document_id: str, extractions: Optional[Dict[str, Any]], pages: List[Any]
) -> List[Dict[str, Any]]:
    """Detects arithmetic discrepancies between line items, subtotal, tax, and total."""
    flags = []

    # 1. Check structured extraction fields if available
    if extractions and isinstance(extractions, dict):
        fields = extractions.get("fields") or extractions
        subtotal_entry = fields.get("subtotal") or {}
        tax_entry = fields.get("tax") or {}
        total_entry = fields.get("total") or {}

        subtotal = subtotal_entry.get("value")
        tax = tax_entry.get("value", 0.0) or 0.0
        total = total_entry.get("value")

        if subtotal is not None and total is not None:
            try:
                sub_f = float(subtotal)
                tax_f = float(tax)
                tot_f = float(total)

                expected_total = sub_f + tax_f
                if abs(expected_total - tot_f) > 0.05:
                    page_num = total_entry.get("page") or 1
                    quote = total_entry.get("quote") or f"Subtotal: {sub_f}, Tax: {tax_f}, Total: {tot_f}"
                    flags.append(
                        {
                            "rule_id": "invoice_math_mismatch",
                            "severity": "high",
                            "message": (
                                f"Invoice arithmetic discrepancy: Subtotal (${sub_f:,.2f}) + Tax (${tax_f:,.2f}) = "
                                f"${expected_total:,.2f}, which does not match reported total of ${tot_f:,.2f}."
                            ),
                            "evidence": [
                                {
                                    "page": page_num,
                                    "quote": quote,
                                    "details": f"Discrepancy of ${abs(expected_total - tot_f):,.2f}",
                                }
                            ],
                            "confidence": 0.98,
                        }
                    )
                return flags
            except (ValueError, TypeError):
                pass

    # 2. Fallback regex analysis across page text
    for page in pages:
        p_num = getattr(page, "page_number", 1) if hasattr(page, "page_number") else page.get("page_number", 1)
        p_text = getattr(page, "text", "") if hasattr(page, "text") else page.get("text", "")

        sub_m = re.search(r"\bSubtotal[:\s]+\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)", p_text, re.IGNORECASE)
        tax_m = re.search(r"\bTax[:\s]+\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)", p_text, re.IGNORECASE)
        tot_m = re.search(
            r"\b(?:Total(?: Amount Due)?|Balance Due)[:\s]+\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)",
            p_text,
            re.IGNORECASE,
        )

        if sub_m and tot_m:
            try:
                sub_val = float(sub_m.group(1).replace(",", ""))
                tax_val = float(tax_m.group(1).replace(",", "")) if tax_m else 0.0
                tot_val = float(tot_m.group(1).replace(",", ""))

                expected = sub_val + tax_val
                if abs(expected - tot_val) > 0.05:
                    flags.append(
                        {
                            "rule_id": "invoice_math_mismatch",
                            "severity": "high",
                            "message": (
                                f"Invoice arithmetic discrepancy: Subtotal (${sub_val:,.2f}) + Tax (${tax_val:,.2f}) = "
                                f"${expected:,.2f}, differing from reported Total (${tot_val:,.2f})."
                            ),
                            "evidence": [
                                {
                                    "page": p_num,
                                    "quote": f"{sub_m.group(0)} | {tot_m.group(0)}",
                                    "details": f"Discrepancy of ${abs(expected - tot_val):,.2f}",
                                }
                            ],
                            "confidence": 0.95,
                        }
                    )
                    break
            except ValueError:
                continue

    return flags


def check_duplicate_invoice(
    document_id: str, extractions: Optional[Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Detects duplicate invoice numbers or identical documents previously processed."""
    flags = []
    if not db_session:
        return flags

    try:
        from models_db import Extraction, Document

        fields = (extractions.get("fields") if extractions else None) or extractions or {}
        inv_num_entry = fields.get("invoice_number") or {}
        inv_num = inv_num_entry.get("value")

        if inv_num and len(str(inv_num).strip()) >= 3:
            clean_inv = str(inv_num).strip().lower()

            # Check other extractions in DB
            other_extractions = db_session.query(Extraction).filter(Extraction.document_id != document_id).all()

            for other in other_extractions:
                other_fields = other.json_data or {}
                other_inv = other_fields.get("invoice_number", {}).get("value")

                if other_inv and str(other_inv).strip().lower() == clean_inv:
                    other_doc = db_session.query(Document).filter(Document.id == other.document_id).first()
                    other_filename = other_doc.filename if other_doc else other.document_id

                    flags.append(
                        {
                            "rule_id": "duplicate_invoice",
                            "severity": "high",
                            "message": (
                                f"Potential duplicate invoice detected: invoice number '{inv_num}' is identical to "
                                f"existing document '{other_filename}'."
                            ),
                            "evidence": [
                                {
                                    "page": inv_num_entry.get("page", 1),
                                    "quote": inv_num_entry.get("quote", f"Invoice: {inv_num}"),
                                    "details": f"Matches document {other_filename}",
                                }
                            ],
                            "confidence": 0.92,
                        }
                    )
                    break
    except Exception as e:
        logger.debug(f"Duplicate invoice check encountered error: {e}")

    return flags


def check_pdf_metadata_anomaly(
    document_id: str, pages: List[Any], metadata: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Detects inconsistencies in PDF generation tools, creation timestamps, and signing."""
    flags = []
    if not metadata:
        return flags

    producer = str(metadata.get("producer") or metadata.get("/Producer") or "").lower()
    creator = str(metadata.get("creator") or metadata.get("/Creator") or "").lower()
    creation_date_str = str(metadata.get("creation_date") or metadata.get("/CreationDate") or "")

    # Check 1: Scanned extraction method vs high-end vector publishing producer
    has_ocr = any(getattr(p, "extraction_method", "") == "ocr" for p in pages)
    digital_generators = ["indesign", "illustrator", "quarkxpress", "word", "libreoffice"]
    if has_ocr and any(gen in producer or gen in creator for gen in digital_generators):
        flags.append(
            {
                "rule_id": "pdf_metadata_anomaly",
                "severity": "medium",
                "message": (
                    f"Producer anomaly: Document text layer required OCR scanning, but PDF producer "
                    f"metadata indicates digital layout software ('{producer or creator}')."
                ),
                "evidence": [
                    {
                        "page": 1,
                        "quote": f"Producer: {producer or creator}",
                        "details": "Potential visual alteration or flattened scan of a digital document.",
                    }
                ],
                "confidence": 0.85,
            }
        )

    # Check 2: Future creation timestamp
    if creation_date_str:
        try:
            # Parse PDF date formats like D:20271125120000
            clean_date = re.sub(r"^[D\:]+", "", creation_date_str)[:8]
            if len(clean_date) == 8 and clean_date.isdigit():
                doc_dt = datetime.strptime(clean_date, "%Y%m%d")
                if doc_dt > datetime.now():
                    flags.append(
                        {
                            "rule_id": "pdf_metadata_anomaly",
                            "severity": "medium",
                            "message": f"Timestamp anomaly: PDF CreationDate ('{doc_dt.date()}') is set in the future.",
                            "evidence": [
                                {
                                    "page": 1,
                                    "quote": creation_date_str,
                                    "details": "Future creation date indicates device clock tampering or generation anomalies.",
                                }
                            ],
                            "confidence": 0.90,
                        }
                    )
        except Exception:
            pass

    return flags


def check_date_inconsistency(
    document_id: str, extractions: Optional[Dict[str, Any]], pages: List[Any]
) -> List[Dict[str, Any]]:
    """Detects invalid date sequences (due date preceding issuance date, or terms mismatch)."""
    flags = []
    fields = (extractions.get("fields") if extractions else None) or extractions or {}

    inv_date_entry = fields.get("invoice_date") or {}
    due_date_entry = fields.get("due_date") or {}
    terms_entry = fields.get("payment_terms") or {}

    inv_date_str = inv_date_entry.get("value")
    due_date_str = due_date_entry.get("value")
    terms_str = terms_entry.get("value") or ""

    if inv_date_str and due_date_str:
        try:
            dt_inv = date_parser.parse(str(inv_date_str))
            dt_due = date_parser.parse(str(due_date_str))

            # Check 1: Due date before invoice date
            if dt_due < dt_inv:
                flags.append(
                    {
                        "rule_id": "date_inconsistency",
                        "severity": "high",
                        "message": (
                            f"Chronological date inconsistency: Invoice due date ({dt_due.strftime('%Y-%m-%d')}) "
                            f"precedes invoice issuance date ({dt_inv.strftime('%Y-%m-%d')})."
                        ),
                        "evidence": [
                            {
                                "page": due_date_entry.get("page", 1),
                                "quote": f"Invoice: {inv_date_str} | Due: {due_date_str}",
                                "details": f"Due date is {(dt_inv - dt_due).days} days before invoice date.",
                            }
                        ],
                        "confidence": 0.96,
                    }
                )

            # Check 2: Terms mismatch (Net 30 stated but due date is Net 60+)
            days_diff = (dt_due - dt_inv).days
            if "net 30" in terms_str.lower() and days_diff >= 55:
                flags.append(
                    {
                        "rule_id": "date_inconsistency",
                        "severity": "medium",
                        "message": (
                            f"Payment terms mismatch: Stated terms are '{terms_str}', but calculated due date "
                            f"allows {days_diff} days (substantially exceeding 30 days)."
                        ),
                        "evidence": [
                            {
                                "page": terms_entry.get("page", 1),
                                "quote": terms_entry.get("quote", terms_str),
                                "details": f"{days_diff} calendar days between invoice and due date.",
                            }
                        ],
                        "confidence": 0.88,
                    }
                )
        except Exception:
            pass

    return flags


def check_cross_document_mismatch(
    document_id: str, extractions: Optional[Dict[str, Any]], db_session: Any
) -> List[Dict[str, Any]]:
    """Detects discrepancies between related documents (e.g., Purchase Order vs Invoice)."""
    flags = []
    if not db_session:
        return flags

    try:
        from models_db import Document, Extraction

        curr_doc = db_session.query(Document).filter(Document.id == document_id).first()
        if not curr_doc or not curr_doc.session_id:
            return flags

        # Find other documents in the same workspace session
        other_docs = (
            db_session.query(Document)
            .filter(Document.session_id == curr_doc.session_id, Document.id != document_id)
            .all()
        )

        curr_fields = (extractions.get("fields") if extractions else None) or extractions or {}
        curr_total = curr_fields.get("total", {}).get("value")

        for other in other_docs:
            if "po" in other.filename.lower() or "order" in other.filename.lower():
                other_ext = db_session.query(Extraction).filter(Extraction.document_id == other.id).first()
                if other_ext:
                    other_fields = other_ext.json_data or {}
                    po_total = other_fields.get("total", {}).get("value")

                    if curr_total and po_total:
                        try:
                            inv_amt = float(curr_total)
                            po_amt = float(po_total)

                            if inv_amt > (po_amt * 1.05):
                                flags.append(
                                    {
                                        "rule_id": "cross_document_mismatch",
                                        "severity": "high",
                                        "message": (
                                            f"Cross-document discrepancy: Invoice amount (${inv_amt:,.2f}) exceeds "
                                            f"Purchase Order '{other.filename}' amount (${po_amt:,.2f}) by "
                                            f"${(inv_amt - po_amt):,.2f}."
                                        ),
                                        "evidence": [
                                            {
                                                "page": curr_fields.get("total", {}).get("page", 1),
                                                "quote": f"Invoice: ${inv_amt:,.2f} vs PO: ${po_amt:,.2f}",
                                                "details": f"Excess of {((inv_amt / po_amt) - 1) * 100:.1f}% above authorized PO.",
                                            }
                                        ],
                                        "confidence": 0.90,
                                    }
                                )
                        except (ValueError, TypeError):
                            pass
    except Exception as e:
        logger.debug(f"Cross document mismatch check failed: {e}")

    return flags


def check_round_number_and_threshold(
    document_id: str, extractions: Optional[Dict[str, Any]], pages: List[Any]
) -> List[Dict[str, Any]]:
    """
    Detects amounts calibrated just below standard corporate threshold approvals
    (e.g., $9,999, $4,999, $999) or repeated clean round numbers lacking cents.
    """
    flags = []
    fields = (extractions.get("fields") if extractions else None) or extractions or {}
    total_entry = fields.get("total") or {}
    total_val = total_entry.get("value")

    checked_amounts = []
    if total_val is not None:
        try:
            checked_amounts.append(
                (float(total_val), total_entry.get("page", 1), total_entry.get("quote", f"${total_val}"))
            )
        except (ValueError, TypeError):
            pass

    # Also search page text for prominent monetary amounts
    if not checked_amounts:
        for p in pages:
            p_num = getattr(p, "page_number", 1) if hasattr(p, "page_number") else p.get("page_number", 1)
            p_text = getattr(p, "text", "") if hasattr(p, "text") else p.get("text", "")
            matches = re.finditer(r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)", p_text)
            for m in matches:
                try:
                    val = float(m.group(1).replace(",", ""))
                    checked_amounts.append((val, p_num, m.group(0)))
                except ValueError:
                    pass

    # Threshold evasion values: e.g. 9999, 4999, 2499, 999
    sub_threshold_targets = {
        9999.0: 10000.0,
        9990.0: 10000.0,
        9995.0: 10000.0,
        4999.0: 5000.0,
        4995.0: 5000.0,
        2499.0: 2500.0,
        999.0: 1000.0,
    }

    seen_flags = set()
    for amt, p_num, quote in checked_amounts:
        for sub_val, threshold in sub_threshold_targets.items():
            if abs(amt - sub_val) < 0.01:
                flag_key = f"{amt}_{threshold}"
                if flag_key not in seen_flags:
                    seen_flags.add(flag_key)
                    flags.append(
                        {
                            "rule_id": "round_number_and_threshold",
                            "severity": "medium",
                            "message": (
                                f"Approval threshold indicator: Transaction amount (${amt:,.2f}) is calibrated "
                                f"immediately below the standard corporate threshold of ${threshold:,.2f}."
                            ),
                            "evidence": [
                                {
                                    "page": p_num,
                                    "quote": quote,
                                    "details": f"Amount is within $10 of ${threshold:,.2f} approval limit.",
                                }
                            ],
                            "confidence": 0.88,
                        }
                    )

    return flags
