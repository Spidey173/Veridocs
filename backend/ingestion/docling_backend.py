"""
Docling parser backend for advanced layout analysis, table recognition, and OCR.
Gracefully defers to PyMuPDFBackend if docling is not installed in the environment.
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from ingestion.base import ParserBackend, ParsedDocument, Page, TableData
from ingestion.pymupdf_backend import PyMuPDFBackend
from ingestion.headings import SectionTracker, infer_heading_from_text

logger = logging.getLogger(__name__)


class DoclingBackend(ParserBackend):
    """
    Docling backend using IBM Deep Search Docling.
    Extracts deep document layout, formulas, and high-fidelity structured tables.
    """

    def __init__(self):
        self.fallback = PyMuPDFBackend()
        self._converter = None
        try:
            from docling.document_converter import DocumentConverter

            self._converter = DocumentConverter()
            logger.info("Docling DocumentConverter initialized successfully.")
        except Exception as e:
            logger.info(f"Docling not available ({e}). Using PyMuPDF + OCR fallback.")

    def parse(self, file_path: Path, filename: Optional[str] = None) -> ParsedDocument:
        fname = filename or file_path.name

        if self._converter is None:
            return self.fallback.parse(file_path, fname)

        try:
            result = self._converter.convert(file_path)
            doc = result.document

            pages: List[Page] = []
            tracker = SectionTracker()
            blocks_by_page: Dict[int, List[Dict[str, Any]]] = {}
            table_sections_by_page: Dict[int, List[Optional[str]]] = {}
            page_numbers = set()

            for item, _ in doc.iterate_items():
                p_no = 1
                prov = getattr(item, "prov", None)
                if isinstance(prov, list) and prov:
                    p_no = getattr(prov[0], "page_no", 1) or 1
                elif prov is not None and hasattr(prov, "page_no"):
                    p_no = getattr(prov, "page_no", 1) or 1
                page_numbers.add(p_no)

                label_val = str(getattr(getattr(item, "label", ""), "value", getattr(item, "label", ""))).lower()
                text_val = (getattr(item, "text", "") or "").strip()

                if "title" in label_val or "section_header" in label_val or "heading" in label_val:
                    if text_val:
                        level = getattr(item, "level", None)
                        if level is None:
                            _, inferred_lvl, _ = infer_heading_from_text(text_val, is_bold=True)
                            level = inferred_lvl or (0 if "title" in label_val else 1)
                        sec_path = tracker.push(int(level), text_val)
                        blocks_by_page.setdefault(p_no, []).append(
                            {
                                "text": text_val,
                                "section_path": sec_path,
                                "is_heading": True,
                                "heading_level": int(level),
                            }
                        )
                elif "table" in label_val:
                    table_sections_by_page.setdefault(p_no, []).append(tracker.current_path)
                elif text_val:
                    blk = tracker.process_line(text_val)
                    blocks_by_page.setdefault(p_no, []).append(blk)

            total_pages = max(page_numbers) if page_numbers else 1

            for p_num in range(1, total_pages + 1):
                p_text = doc.export_to_text(page_no=p_num) if hasattr(doc, "export_to_text") else ""
                tables: List[TableData] = []
                page_table_secs = table_sections_by_page.get(p_num, [])
                tbl_idx = 0

                # Extract tables on this page
                if hasattr(doc, "tables"):
                    for t in doc.tables:
                        t_prov = getattr(t, "prov", None)
                        if isinstance(t_prov, list) and t_prov:
                            t_page = getattr(t_prov[0], "page_no", 1)
                        else:
                            t_page = getattr(t_prov, "page_no", 1) if t_prov is not None else 1
                        if t_page == p_num:
                            md = t.export_to_markdown() if hasattr(t, "export_to_markdown") else ""
                            rows = t.export_to_dict() if hasattr(t, "export_to_dict") else {}
                            tbl_sec = (
                                page_table_secs[tbl_idx] if tbl_idx < len(page_table_secs) else tracker.current_path
                            )
                            tbl_idx += 1
                            tables.append(
                                TableData(
                                    page_number=p_num,
                                    markdown=md,
                                    json_data=rows,
                                    bbox=None,
                                    section_path=tbl_sec,
                                )
                            )

                pages.append(
                    Page(
                        number=p_num,
                        text=p_text,
                        blocks=blocks_by_page.get(p_num, []),
                        tables=tables,
                        extraction_method="text_layer",
                        ocr_confidence=0.95,
                        has_tables=len(tables) > 0,
                    )
                )

            if not pages:
                return self.fallback.parse(file_path, fname)

            return ParsedDocument(filename=fname, pages=pages, total_pages=len(pages))

        except Exception as e:
            logger.warning(f"Docling parse failed on {fname} ({e}). Falling back to PyMuPDF backend.")
            return self.fallback.parse(file_path, fname)
