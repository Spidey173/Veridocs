"""
Shared heading hierarchy detection and section_path tracking for document parsers.
Produces hierarchical section paths such as "3 > 3.1 Payment Terms".
"""

import re
from typing import List, Tuple, Optional, Dict, Any

_DECIMAL_HEADING_RE = re.compile(r"^(?:Section\s+|Article\s+)?(\d+(?:\.\d+)*)\b[\.:\-\s]+(.+)$", re.IGNORECASE)
_KEYWORD_HEADING_RE = re.compile(
    r"^(SECTION|ARTICLE|CHAPTER|PART|APPENDIX|SCHEDULE|EXHIBIT)\s+([0-9IVXLCDM]+|[A-Z])\b[\.:\-\s]*(.*)$", re.IGNORECASE
)
_INLINE_KEYWORD_TITLE_RE = re.compile(
    r"^((?:SECTION|ARTICLE|CHAPTER|PART)\s+(?:[0-9IVXLCDM]+|[A-Z])(?:\.\d+)*[\.:\-\s]+[^:.\n]{2,55}):\s+.+$",
    re.IGNORECASE,
)


def infer_heading_from_text(
    line: str, is_bold: bool = False, font_size: Optional[float] = None, median_font_size: Optional[float] = None
) -> Tuple[bool, Optional[int], str]:
    """
    Determine whether a line/block is a heading, its hierarchy level (1..4), and clean title.
    Returns (is_heading, level, clean_title).
    """
    clean = " ".join(line.split()).strip()
    if not clean or len(clean) > 220:
        return False, None, clean

    # 1a. Inline keyword heading followed by colon + body sentence, e.g. "Section 1. Payment Terms: Invoices..."
    m_inline = _INLINE_KEYWORD_TITLE_RE.match(clean)
    if m_inline:
        title = m_inline.group(1).strip().rstrip(":")
        return True, 1, title

    if len(clean) > 120:
        return False, None, clean

    # 1b. Explicit SECTION / ARTICLE / CHAPTER keyword headings
    m_kw = _KEYWORD_HEADING_RE.match(clean)
    if m_kw and not clean.endswith("."):
        return True, 1, clean.rstrip(":")

    # 2. Decimal numbered headings like "3. Commercial Terms" or "3.1 Payment Terms" or "3.1.2 Fees"
    m_dec = _DECIMAL_HEADING_RE.match(clean)
    if m_dec and len(clean) <= 90:
        num_part = m_dec.group(1)
        rest = m_dec.group(2).strip()
        # Avoid matching normal sentences starting with a year or quantity like "2026 revenues grew..."
        if (
            len(num_part) <= 8
            and rest
            and not rest[0].islower()
            and (
                not clean.endswith(".")
                or is_bold
                or (font_size and median_font_size and font_size > median_font_size * 1.08)
            )
        ):
            depth = min(num_part.count(".") + 1, 4)
            return True, depth, clean.rstrip(":")

    # 3. Font-size or bold standalone headings in PDFs
    if (
        font_size
        and median_font_size
        and font_size >= median_font_size * 1.18
        and len(clean) <= 90
        and not clean.endswith(".")
    ):
        level = 1 if font_size >= median_font_size * 1.35 else 2
        return True, level, clean.rstrip(":")

    if is_bold and len(clean) <= 70 and not clean.endswith(".") and len(clean.split()) <= 10:
        return True, 2, clean.rstrip(":")

    # 4. Short ALL-CAPS standalone headings
    if clean.isupper() and 4 <= len(clean) <= 60 and not clean.endswith("."):
        return True, 1, clean.rstrip(":")

    return False, None, clean


class SectionTracker:
    """Maintains an active heading hierarchy stack and computes section_path strings."""

    def __init__(self) -> None:
        self._stack: List[Tuple[int, str]] = []

    @property
    def current_path(self) -> Optional[str]:
        if not self._stack:
            return None
        return " > ".join(title for _, title in self._stack)

    def push(self, level: int, title: str) -> str:
        clean = " ".join(title.split()).strip().rstrip(":")
        while self._stack and self._stack[-1][0] >= level:
            self._stack.pop()
        self._stack.append((level, clean))
        return " > ".join(t for _, t in self._stack)

    def process_line(
        self,
        line: str,
        is_bold: bool = False,
        font_size: Optional[float] = None,
        median_font_size: Optional[float] = None,
    ) -> Dict[str, Any]:
        is_heading, level, clean = infer_heading_from_text(
            line,
            is_bold=is_bold,
            font_size=font_size,
            median_font_size=median_font_size,
        )
        if is_heading and level is not None:
            sec_path = self.push(level, clean)
        else:
            sec_path = self.current_path

        return {
            "text": line.strip(),
            "section_path": sec_path,
            "is_heading": is_heading,
            "heading_level": level,
        }
