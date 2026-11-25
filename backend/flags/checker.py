"""
Anomaly flag runner and coordinator for Veridocs.
Runs all independent checkers, records flags into the database,
and formats responses with honest heuristic disclaimers.
"""

import time
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from config import get_settings
from models_db import Document, Extraction, Flag
from flags.rules import (
    check_invoice_math_mismatch,
    check_duplicate_invoice,
    check_pdf_metadata_anomaly,
    check_date_inconsistency,
    check_cross_document_mismatch,
    check_round_number_and_threshold,
)

logger = logging.getLogger(__name__)

DISCLAIMER_TEXT = "These are heuristic signals for human review, not automated fraud accusations."


class FlagCheckerService:
    """Coordinates execution and storage of document anomaly flags."""

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def run_all_checks(self, document_id: str, pdf_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Executes all independent anomaly rules and updates the flags table."""
        if not self.settings.FLAGS_ENABLED:
            return []

        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.warning(f"Document {document_id} not found for anomaly checking.")
            return []

        pages = doc.pages or []
        ext_record = self.db.query(Extraction).filter(Extraction.document_id == document_id).first()
        extractions = ext_record.json_data if ext_record else None

        collected_flags: List[Dict[str, Any]] = []

        # 1. Invoice Math Discrepancies
        collected_flags.extend(check_invoice_math_mismatch(document_id, extractions, pages))

        # 2. Duplicate Invoice Detection
        collected_flags.extend(check_duplicate_invoice(document_id, extractions, self.db))

        # 3. PDF Metadata Anomalies
        collected_flags.extend(check_pdf_metadata_anomaly(document_id, pages, pdf_metadata))

        # 4. Date Inconsistencies
        collected_flags.extend(check_date_inconsistency(document_id, extractions, pages))

        # 5. Cross-Document Discrepancies
        collected_flags.extend(check_cross_document_mismatch(document_id, extractions, self.db))

        # 6. Round Numbers and Threshold Evasion
        collected_flags.extend(check_round_number_and_threshold(document_id, extractions, pages))

        # Remove previous flags for document to avoid stale entries
        self.db.query(Flag).filter(Flag.document_id == document_id).delete()

        # Persist new flags
        persisted_flags = []
        for f in collected_flags:
            db_flag = Flag(
                document_id=document_id,
                rule_id=f["rule_id"],
                severity=f["severity"],
                message=f["message"],
                evidence=f.get("evidence", []),
                confidence=f.get("confidence", 1.0),
                created_at=time.time(),
            )
            self.db.add(db_flag)
            persisted_flags.append(db_flag)

        self.db.commit()
        return [f.to_dict() for f in persisted_flags]

    def get_flags(self, document_id: str) -> Dict[str, Any]:
        """Fetches stored flags for a document with summary counts and disclaimer."""
        flags = self.db.query(Flag).filter(Flag.document_id == document_id).order_by(Flag.created_at.desc()).all()

        flag_dicts = [f.to_dict() for f in flags]

        severity_counts = {"high": 0, "medium": 0, "low": 0}
        for f in flag_dicts:
            sev = f.get("severity", "low").lower()
            if sev in severity_counts:
                severity_counts[sev] += 1

        return {
            "document_id": document_id,
            "disclaimer": DISCLAIMER_TEXT,
            "total_flags": len(flag_dicts),
            "severity_counts": severity_counts,
            "flags": flag_dicts,
        }
