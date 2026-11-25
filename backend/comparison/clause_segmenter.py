"""
Contract Clause Segmenter for Veridocs.
Segments contract documents into discrete clauses using numbering/heading patterns
with an LLM fallback when structure is unclear. Computes dense vector embeddings
for each clause to power Hungarian algorithm alignment.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from config import get_settings, get_model_registry

logger = logging.getLogger(__name__)

# Patterns matching clause headings and numbers
CLAUSE_HEADING_PATTERNS = [
    # Article / Section headers: "ARTICLE 1. DEFINITIONS", "SECTION 2 - TERM"
    re.compile(r"^(?:ARTICLE|SECTION)\s+([0-9IVXLCDM]+|[A-Z])[\.:\s\-]+(.*)$", re.IGNORECASE),
    # Standard decimal numbering: "1. Term", "1.1 Payment Schedule", "10. Miscellaneous"
    re.compile(r"^(?:Clause\s+)?(\d+(?:\.\d+)*)[\.\s\-]+(.*)$", re.IGNORECASE),
    # Parenthesized sub-clauses: "(a) Indemnification", "(1) Termination"
    re.compile(r"^\(([a-z0-9]+)\)[\s\-]+(.*)$", re.IGNORECASE),
    # Common formal sections: "Recitals", "Preamble", "Witnesseth"
    re.compile(
        r"^(Recitals|Preamble|Witnesseth|Signatures|Schedule\s+[A-Z0-9]+|Exhibit\s+[A-Z0-9]+):?$", re.IGNORECASE
    ),
]

# All-caps headings (must be short, on a line by itself, and not look like regular sentence text)
ALL_CAPS_HEADING_PATTERN = re.compile(r"^[A-Z][A-Z0-9\s,\'\-\&]{2,60}:?$")

EXCLUDED_ALL_CAPS = {
    "IN WITNESS WHEREOF",
    "NOW THEREFORE",
    "PAGE",
    "CONFIDENTIAL",
    "DRAFT",
    "BY AND BETWEEN",
    "TABLE OF CONTENTS",
}


class ClauseSegmenter:
    """Segments contract text into structured clauses with embeddings."""

    def __init__(self):
        self.settings = get_settings()

    def segment_pages(self, pages_data: List[Any], document_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Segment a list of pages into structured clauses.
        pages_data can be a list of Page OR dicts {"page_number": int, "text": str}.
        """
        # Prepare page stream: list of (line, page_number)
        line_stream: List[Tuple[str, int]] = []
        for p in pages_data:
            p_num = getattr(p, "page_number", None) or p.get("page_number", 1)
            p_text = getattr(p, "text", None) if hasattr(p, "text") else p.get("text", "")
            lines = p_text.splitlines()
            for line in lines:
                stripped = line.strip()
                if stripped:
                    line_stream.append((stripped, p_num))

        if not line_stream:
            return []

        # 1. Attempt regex-based rule segmentation
        clauses = self._regex_segmentation(line_stream, document_id)

        # 2. Check if structure was unclear (fewer than 2 clauses on substantial text)
        total_words = sum(len(line.split()) for line, _ in line_stream)
        if len(clauses) < 2 and total_words >= 100:
            logger.info("Unclear clause structure detected; running LLM segmentation fallback.")
            llm_clauses = self._llm_segmentation_fallback(line_stream, document_id)
            if len(llm_clauses) >= 2:
                clauses = llm_clauses

        # 3. If still single clause or no clauses, group by paragraphs
        if not clauses:
            clauses = self._paragraph_fallback(line_stream, document_id)

        # 4. Compute vector embeddings for all segmented clauses
        self._compute_embeddings(clauses)

        return clauses

    def _regex_segmentation(
        self, line_stream: List[Tuple[str, int]], document_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Identifies clause boundaries using numbering and title regex patterns."""
        clauses: List[Dict[str, Any]] = []
        current_clause: Optional[Dict[str, Any]] = None
        current_lines: List[str] = []

        for line, page_num in line_stream:
            number, heading = self._match_clause_header(line)

            if number or heading:
                # Close existing clause
                if current_clause and current_lines:
                    current_clause["text"] = "\n".join(current_lines).strip()
                    current_clause["page_end"] = page_num
                    if current_clause["text"]:
                        clauses.append(current_clause)

                # Start new clause
                current_clause = {
                    "document_id": document_id,
                    "clause_index": len(clauses),
                    "number": number,
                    "heading": heading or (number if not heading else None),
                    "text": "",
                    "page_start": page_num,
                    "page_end": page_num,
                    "embedding": None,
                }
                current_lines = [line]
            else:
                if current_clause is None:
                    # Preamble or introduction before first numbered clause
                    current_clause = {
                        "document_id": document_id,
                        "clause_index": 0,
                        "number": "Preamble",
                        "heading": "Preamble",
                        "text": "",
                        "page_start": page_num,
                        "page_end": page_num,
                        "embedding": None,
                    }
                    current_lines = [line]
                else:
                    current_lines.append(line)
                    current_clause["page_end"] = page_num

        if current_clause and current_lines:
            current_clause["text"] = "\n".join(current_lines).strip()
            if current_clause["text"]:
                clauses.append(current_clause)

        # Re-index clauses sequentially
        for idx, c in enumerate(clauses):
            c["clause_index"] = idx

        return clauses

    def _match_clause_header(self, line: str) -> Tuple[Optional[str], Optional[str]]:
        """Returns (number, heading) if the line matches a clause heading, else (None, None)."""
        clean = line.strip()

        # Check explicit numbering patterns
        for pat in CLAUSE_HEADING_PATTERNS:
            m = pat.match(clean)
            if m:
                groups = m.groups()
                if len(groups) == 1:
                    return groups[0].strip(), groups[0].strip()
                elif len(groups) >= 2:
                    num = groups[0].strip()
                    head = groups[1].strip() or None
                    return num, head

        # Check All-Caps standalone headings
        if clean.isupper() and 3 <= len(clean) <= 60:
            if ALL_CAPS_HEADING_PATTERN.match(clean) and clean not in EXCLUDED_ALL_CAPS:
                head = clean.rstrip(":")
                return None, head

        return None, None

    def _llm_segmentation_fallback(
        self, line_stream: List[Tuple[str, int]], document_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Invokes LLM when rule-based pattern matching fails to find clear clause boundaries."""
        try:
            from llm_service import call_llm_json

            # Construct condensed page text with page markers
            full_text = ""
            current_p = -1
            for line, p_num in line_stream:
                if p_num != current_p:
                    full_text += f"\n[Page {p_num}]\n"
                    current_p = p_num
                full_text += line + "\n"

            prompt = (
                "You are an expert legal contract analyst. Segment the following contract text into discrete, "
                "logical clauses or sections (e.g., Definitions, Term, Payment, Liability, Termination, Governing Law).\n"
                "Return a strict JSON array of objects with keys:\n"
                "- number: string (clause number like '1.', '2.1' or null)\n"
                "- heading: string (clause title or short topic)\n"
                "- text: string (exact verbatim clause text from the document)\n"
                "- page_start: integer (starting page number)\n"
                "- page_end: integer (ending page number)\n\n"
                f"DOCUMENT TEXT:\n{full_text[:6000]}"
            )

            result = call_llm_json(prompt)
            if isinstance(result, list) and len(result) >= 2:
                clauses = []
                for idx, item in enumerate(result):
                    if isinstance(item, dict) and item.get("text"):
                        clauses.append(
                            {
                                "document_id": document_id,
                                "clause_index": idx,
                                "number": item.get("number"),
                                "heading": item.get("heading"),
                                "text": item.get("text", "").strip(),
                                "page_start": int(item.get("page_start", 1)),
                                "page_end": int(item.get("page_end", 1)),
                                "embedding": None,
                            }
                        )
                return clauses
        except Exception as e:
            logger.warning(f"LLM clause segmentation fallback failed: {e}")

        return []

    def _paragraph_fallback(
        self, line_stream: List[Tuple[str, int]], document_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fallback: Group lines by double-newline paragraphs."""
        clauses = []
        current_lines = []
        start_p = 1
        end_p = 1

        for line, p_num in line_stream:
            if not current_lines:
                start_p = p_num
            end_p = p_num
            current_lines.append(line)

            if len(current_lines) >= 8 or line.endswith("."):
                text_block = "\n".join(current_lines).strip()
                first_line = current_lines[0]
                heading = first_line[:50] if len(first_line) > 50 else first_line
                clauses.append(
                    {
                        "document_id": document_id,
                        "clause_index": len(clauses),
                        "number": str(len(clauses) + 1),
                        "heading": heading,
                        "text": text_block,
                        "page_start": start_p,
                        "page_end": end_p,
                        "embedding": None,
                    }
                )
                current_lines = []

        if current_lines:
            text_block = "\n".join(current_lines).strip()
            clauses.append(
                {
                    "document_id": document_id,
                    "clause_index": len(clauses),
                    "number": str(len(clauses) + 1),
                    "heading": f"Section {len(clauses) + 1}",
                    "text": text_block,
                    "page_start": start_p,
                    "page_end": end_p,
                    "embedding": None,
                }
            )

        return clauses

    def _compute_embeddings(self, clauses: List[Dict[str, Any]]) -> None:
        """Computes dense 384-dimensional vector embeddings for all clauses."""
        if not clauses:
            return

        texts = [c["text"] for c in clauses]
        try:
            reg = get_model_registry()
            embeddings_iter = reg.embedding_model.embed(texts)
            for clause, emb in zip(clauses, embeddings_iter):
                emb_arr = np.array(emb, dtype=np.float32)
                norm = np.linalg.norm(emb_arr)
                if norm > 1e-6:
                    emb_arr = emb_arr / norm
                clause["embedding"] = emb_arr.tolist()
        except Exception as e:
            logger.warning(f"Failed to compute clause embeddings: {e}")
            for clause in clauses:
                clause["embedding"] = [0.0] * 384
