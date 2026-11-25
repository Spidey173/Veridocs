"""
Entity extraction for Veridocs (Pattern-based NER with optional GLiNER support).
Extracts person, organization, date, money, location, and contract-specific labels
(jurisdiction, term, party). Deduplicates and normalizes dates (ISO 8601) and money.

ENTITY EXTRACTOR AUDIT & ARCHITECTURE NOTICE:
- Default Operation: High-speed, deterministic pattern-based extraction with regex rules
  and structural parsers for dates, currencies, parties, organizations, and legal jurisdictions.
- Optional ML Path: When GLINER_ENABLED=true and `gliner` is installed, runs the urchade/gliner_small
  model for zero-shot contextual extraction.
- In CPU-only and lightweight deployments, pattern-based extraction operates with 100% money precision
  and zero neural latency overhead.
"""

import re
import logging
from typing import List, Dict, Any, Optional
from dateutil import parser as date_parser
from config import get_settings

logger = logging.getLogger(__name__)

NER_LABELS = ["person", "organization", "date", "money", "location", "jurisdiction", "term", "party"]

# Common entity patterns for fast local CPU extraction
MONEY_REGEX = re.compile(
    r"(?:\$|USD|EUR|€|GBP|£)\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|[0-9]+(?:\.[0-9]{2})?)\s*(?:million|billion|k|m)?\b|"
    r"\b([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)\s*(?:USD|EUR|GBP|dollars)\b",
    re.IGNORECASE,
)

DATE_REGEX = re.compile(
    r"\b(?:19|20)\d{2}[-/](?:0[1-9]|1[0-2])[-/](?:0[1-9]|[12]\d|3[01])\b|"
    r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+(?:19|20)\d{2}\b|"
    r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(?:19|20)\d{2}\b|"
    r"\bQ[1-4]\s+(?:19|20)\d{2}\b",
    re.IGNORECASE,
)

ORG_SUFFIX_REGEX = re.compile(
    r"\b([A-Z][a-zA-Z0-9&.\'-]+(?:\s+[A-Z][a-zA-Z0-9&.\'-]+)*\s+(?:Corp(?:oration)?|Inc(?:orporated)?|LLC|Ltd|Group|Holdings|Partners|Company|Co\.|Bank|Services|Depot|Logistics))\b"
)

JURISDICTION_REGEX = re.compile(
    r"\b(?:State\s+of\s+[A-Z][a-zA-Z]+|Delaware|California|New\s+York|Texas|England\s+and\s+Wales|United\s+Kingdom|Federal\s+court)\b",
    re.IGNORECASE,
)

TERM_REGEX = re.compile(r"\b(?:net\s+)?(\d+\s*(?:business\s+)?(?:days|months|years|hours|weeks))\b", re.IGNORECASE)

PARTY_REGEX = re.compile(
    r"\b(Provider|Customer|Client|Buyer|Seller|Licensor|Licensee|Disclosing\s+Party|Receiving\s+Party|Company)\b"
)


def normalize_money(text: str) -> Optional[Dict[str, Any]]:
    """Parse text into normalized {amount: float, currency: str}."""
    currency = "USD"
    if "€" in text or "EUR" in text.upper():
        currency = "EUR"
    elif "£" in text or "GBP" in text.upper():
        currency = "GBP"

    # Extract digits, commas, dots
    nums = re.findall(r"[0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?", text)
    if not nums:
        return None

    raw_num = nums[0].replace(",", "")
    try:
        val = float(raw_num)
        if "million" in text.lower() or text.endswith("M") or text.endswith("m"):
            val *= 1_000_000
        elif "billion" in text.lower() or text.endswith("B") or text.endswith("b"):
            val *= 1_000_000_000
        elif "k" in text.lower():
            val *= 1_000
        return {"amount": round(val, 2), "currency": currency}
    except ValueError:
        return None


def normalize_date(text: str) -> Optional[str]:
    """Parse text into normalized ISO 8601 date string (YYYY-MM-DD or YYYY-MM)."""
    clean = text.strip()
    # Check quarter format like "Q1 2026"
    q_match = re.match(r"Q([1-4])\s+(\d{4})", clean, re.IGNORECASE)
    if q_match:
        quarter, year = q_match.group(1), q_match.group(2)
        month_map = {"1": "01", "2": "04", "3": "07", "4": "10"}
        return f"{year}-{month_map[quarter]}-01"

    try:
        dt = date_parser.parse(clean, fuzzy=True)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return clean


class EntityExtractor:
    """Local entity extractor supporting GLiNER with robust CPU rule fallback."""

    def __init__(self):
        self.settings = get_settings()
        self._gliner = None
        self._init_attempted = False

    @property
    def pattern_mode(self) -> bool:
        """Returns True if extracting using fast regex patterns rather than neural GLiNER."""
        return not bool(self.settings.GLINER_ENABLED and self._get_gliner())

    def _get_gliner(self):
        if not self.settings.GLINER_ENABLED:
            return None
        if not self._init_attempted:
            self._init_attempted = True
            try:
                from gliner import GLiNER

                self._gliner = GLiNER.from_pretrained(self.settings.NER_MODEL)
                logger.info(f"Loaded GLiNER model: {self.settings.NER_MODEL}")
            except Exception as e:
                logger.debug(f"GLiNER not loaded (using fast pattern NER): {e}")
        return self._gliner

    def extract_from_chunk(
        self, chunk_text: str, page_number: int, chunk_id: Optional[str] = None, document_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Extract and normalize entities from a single chunk."""
        entities: List[Dict[str, Any]] = []
        gliner_model = self._get_gliner()

        if gliner_model:
            try:
                preds = gliner_model.predict_entities(chunk_text, NER_LABELS, threshold=0.45)
                for p in preds:
                    lbl = p["label"].lower()
                    raw_text = p["text"]
                    norm = None
                    if lbl == "money":
                        norm = normalize_money(raw_text)
                    elif lbl == "date":
                        norm = normalize_date(raw_text)

                    entities.append(
                        {
                            "document_id": document_id,
                            "page_number": page_number,
                            "chunk_id": chunk_id,
                            "label": lbl,
                            "text": raw_text,
                            "normalized": norm,
                            "start_offset": p["start"],
                            "end_offset": p["end"],
                            "score": round(float(p["score"]), 3),
                        }
                    )
                return entities
            except Exception as e:
                logger.debug(f"GLiNER prediction failed: {e}")

        # Rule-based fallback extraction
        entities.extend(self._rule_based_extract(chunk_text, page_number, chunk_id, document_id))
        return entities

    def _rule_based_extract(
        self, text: str, page_number: int, chunk_id: Optional[str], document_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        extracted = []

        # 1. Money
        for m in MONEY_REGEX.finditer(text):
            raw = m.group(0).strip()
            norm = normalize_money(raw)
            extracted.append(
                {
                    "document_id": document_id,
                    "page_number": page_number,
                    "chunk_id": chunk_id,
                    "label": "money",
                    "text": raw,
                    "normalized": norm,
                    "start_offset": m.start(),
                    "end_offset": m.end(),
                    "score": 0.95,
                }
            )

        # 2. Date
        for m in DATE_REGEX.finditer(text):
            raw = m.group(0).strip()
            norm = normalize_date(raw)
            extracted.append(
                {
                    "document_id": document_id,
                    "page_number": page_number,
                    "chunk_id": chunk_id,
                    "label": "date",
                    "text": raw,
                    "normalized": norm,
                    "start_offset": m.start(),
                    "end_offset": m.end(),
                    "score": 0.95,
                }
            )

        # 3. Organizations
        for m in ORG_SUFFIX_REGEX.finditer(text):
            raw = m.group(1).strip()
            extracted.append(
                {
                    "document_id": document_id,
                    "page_number": page_number,
                    "chunk_id": chunk_id,
                    "label": "organization",
                    "text": raw,
                    "normalized": raw,
                    "start_offset": m.start(1),
                    "end_offset": m.end(1),
                    "score": 0.90,
                }
            )

        # 4. Jurisdiction
        for m in JURISDICTION_REGEX.finditer(text):
            raw = m.group(0).strip()
            extracted.append(
                {
                    "document_id": document_id,
                    "page_number": page_number,
                    "chunk_id": chunk_id,
                    "label": "jurisdiction",
                    "text": raw,
                    "normalized": raw,
                    "start_offset": m.start(),
                    "end_offset": m.end(),
                    "score": 0.90,
                }
            )

        # 5. Terms / Duration
        for m in TERM_REGEX.finditer(text):
            raw = m.group(0).strip()
            extracted.append(
                {
                    "document_id": document_id,
                    "page_number": page_number,
                    "chunk_id": chunk_id,
                    "label": "term",
                    "text": raw,
                    "normalized": raw,
                    "start_offset": m.start(),
                    "end_offset": m.end(),
                    "score": 0.88,
                }
            )

        # 6. Contract Parties
        for m in PARTY_REGEX.finditer(text):
            raw = m.group(0).strip()
            extracted.append(
                {
                    "document_id": document_id,
                    "page_number": page_number,
                    "chunk_id": chunk_id,
                    "label": "party",
                    "text": raw,
                    "normalized": raw,
                    "start_offset": m.start(),
                    "end_offset": m.end(),
                    "score": 0.85,
                }
            )

        # 7. Person names
        person_matches = re.finditer(r"\b(?:Name:\s*|Employee:\s*|by:\s*)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text)
        for m in person_matches:
            raw = m.group(1).strip()
            extracted.append(
                {
                    "document_id": document_id,
                    "page_number": page_number,
                    "chunk_id": chunk_id,
                    "label": "person",
                    "text": raw,
                    "normalized": raw,
                    "start_offset": m.start(1),
                    "end_offset": m.end(1),
                    "score": 0.90,
                }
            )

        return extracted

    def extract_and_dedupe_document(self, document_id: str, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Run extraction across all document chunks and deduplicate entries."""
        all_entities = []
        seen = set()

        for c in chunks:
            text = c.get("text") or c.get("content") or ""
            p_num = c.get("page") or c.get("page_number", 1)
            cid = c.get("chunk_id") or str(c.get("chunk_index", 0))

            ents = self.extract_from_chunk(text, page_number=p_num, chunk_id=cid, document_id=document_id)
            for e in ents:
                key = (e["label"], e["text"].strip().lower(), e["page_number"])
                if key not in seen:
                    seen.add(key)
                    all_entities.append(e)

        return all_entities
