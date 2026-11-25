"""
Cheap heuristics for per-page classification (no LLM required):
- has_figures: image blocks, large drawings, visual diagrams
- has_tables: grid borders, pipes, multiple column alignments
- has_signature_block: signature keywords and underline dashes near page bottom
"""

import re
from typing import Dict, Any, List, Optional


SIGNATURE_KEYWORDS = [
    r"\bsignature\b",
    r"\bsigned\s+by\b",
    r"\bauthorized\s+signature\b",
    r"\bauthorized\s+representative\b",
    r"\bby:\s*_{2,}",
    r"\bin\s+witness\s+whereof\b",
    r"\bfor\s+and\s+on\s+behalf\s+of\b",
    r"\bname:\s*_{2,}",
    r"\btitle:\s*_{2,}",
    r"\bdate:\s*_{2,}",
    r"\backnowledged\s+and\s+agreed\b",
]

FIGURE_KEYWORDS = [
    r"\[figure\s*\d+",
    r"\bfig\.\s*\d+",
    r"\bchart\s*\d+",
    r"\bdiagram\s*\d+",
    r"\bgraph\s*\d+",
    r"\bexhibit\s*[a-z0-9]+",
    r"\bflowchart\b",
]


def classify_page_heuristics(
    text: str,
    page_number: int = 1,
    tables: Optional[List[Any]] = None,
    image_count: int = 0,
    has_drawings: bool = False,
) -> Dict[str, bool]:
    """
    Classify page flags cheaply using regex patterns, structural cues, and table metadata.
    Returns:
        {
            "has_figures": bool,
            "has_tables": bool,
            "has_signature_block": bool
        }
    """
    text_clean = text or ""
    lower = text_clean.lower()
    lines = [line.strip() for line in text_clean.split("\n") if line.strip()]

    # 1. Has tables
    has_tables = bool(tables and len(tables) > 0)
    if not has_tables:
        pipe_lines = sum(1 for line in lines if "|" in line and line.count("|") >= 2)
        if pipe_lines >= 2:
            has_tables = True

    # 2. Has figures
    has_figures = (image_count > 0) or has_drawings
    if not has_figures:
        for pat in FIGURE_KEYWORDS:
            if re.search(pat, lower):
                has_figures = True
                break

    # 3. Has signature block (specifically inspect bottom ~35% of lines/text)
    has_sig = False
    bottom_lines = lines[-max(4, int(len(lines) * 0.35)) :] if lines else []
    bottom_text = " \n ".join(bottom_lines).lower()

    for pat in SIGNATURE_KEYWORDS:
        if re.search(pat, bottom_text):
            has_sig = True
            break

    if not has_sig:
        # Check for signature underscore lines like "________" or "--------" near bottom
        for line in bottom_lines:
            if re.search(r"_{4,}|-{4,}", line) and any(
                w in bottom_text for w in ["name", "date", "title", "by", "signature", "signed"]
            ):
                has_sig = True
                break

    return {
        "has_figures": has_figures,
        "has_tables": has_tables,
        "has_signature_block": has_sig,
    }
