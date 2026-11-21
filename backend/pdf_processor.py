"""
Document processing and text extraction for Veridocs (PDF and TXT).
Fast, reliable, and lightweight extraction using pypdf.
"""

import io
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Union, Optional
import pypdf

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_input: Union[bytes, str, Path]) -> List[Dict[str, Any]]:
    """Extract text page-by-page from a PDF file."""
    if isinstance(file_input, (str, Path)):
        reader = pypdf.PdfReader(str(file_input))
    else:
        reader = pypdf.PdfReader(io.BytesIO(file_input))

    pages = []
    for idx, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as e:
            logger.warning(f"Failed to extract text from page {idx + 1}: {e}")
            text = ""

        # Clean excess null bytes or erratic whitespace
        clean_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        clean_text = re.sub(r'\n{3,}', '\n\n', clean_text).strip()

        if clean_text:
            pages.append({
                "page": idx + 1,
                "text": clean_text
            })

    if not pages:
        raise ValueError("No extractable text found in PDF.")

    return pages


def extract_text_from_txt(file_input: Union[bytes, str, Path]) -> List[Dict[str, Any]]:
    """Extract text from a TXT file, splitting into virtual pages for long documents."""
    if isinstance(file_input, (str, Path)):
        raw = Path(file_input).read_bytes()
    else:
        raw = file_input

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    text = text.strip()
    if not text:
        raise ValueError("Text file is empty.")

    # Split into virtual pages of roughly 2500 characters
    page_size = 2500
    pages = []
    total_len = len(text)
    page_num = 1
    start = 0

    while start < total_len:
        end = min(start + page_size, total_len)
        # Find clean boundary (paragraph or sentence)
        if end < total_len:
            boundary = text.rfind("\n\n", start, end)
            if boundary != -1 and boundary > start + 1000:
                end = boundary + 2
            else:
                space_boundary = text.rfind(". ", start, end)
                if space_boundary != -1 and space_boundary > start + 1000:
                    end = space_boundary + 2

        chunk_str = text[start:end].strip()
        if chunk_str:
            pages.append({
                "page": page_num,
                "text": chunk_str
            })
            page_num += 1
        start = end

    return pages


def extract_text_from_file(
    file_input: Union[bytes, str, Path],
    filename: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Extract text based on file extension."""
    fname = filename or (Path(file_input).name if isinstance(file_input, (str, Path)) else "document.pdf")
    ext = Path(fname).suffix.lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_input)
    elif ext == ".txt":
        return extract_text_from_txt(file_input)
    else:
        raise ValueError(f"Unsupported file type '{ext}'. Supported formats: .pdf, .txt")


def chunk_text(
    pages: List[Dict[str, Any]],
    chunk_size: int = 550,
    chunk_overlap: int = 100,
    document_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Split extracted pages into granular passage chunks (~500-600 characters with overlap),
    splitting on natural paragraph/sentence boundaries so citations highlight exact passages.
    Preserves page number metadata for every chunk.
    """
    all_chunks = []
    doc_prefix = f"[Document: {document_name}] " if document_name else ""

    for page_data in pages:
        page_num = page_data["page"]
        text = page_data["text"].strip()
        if not text:
            continue

        paragraphs = [p.strip() for p in re.split(r'\n+', text) if p.strip()]
        current_chunk = ""

        for para in paragraphs:
            if not current_chunk:
                current_chunk = para
            elif len(current_chunk) + len(para) + 1 <= chunk_size:
                current_chunk += " " + para
            else:
                all_chunks.append({
                    "source_file": document_name or "document",
                    "page": page_num,
                    "text": f"{doc_prefix}{current_chunk}",
                })
                # Overlap to maintain context across chunk boundaries
                overlap = current_chunk[-chunk_overlap:] if len(current_chunk) > chunk_overlap else ""
                if " " in overlap:
                    overlap = overlap[overlap.find(" ") + 1:]
                current_chunk = f"{overlap} {para}".strip() if overlap else para

        if current_chunk:
            all_chunks.append({
                "source_file": document_name or "document",
                "page": page_num,
                "text": f"{doc_prefix}{current_chunk}",
            })

    return all_chunks


def get_document_metadata(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Return basic metadata about the uploaded document."""
    ext = Path(filename).suffix.lower()
    num_pages = 1
    if ext == ".pdf":
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            num_pages = len(reader.pages)
        except Exception:
            num_pages = 1

    return {
        "filename": filename,
        "file_size_bytes": len(file_bytes),
        "num_pages": num_pages,
    }


def generate_sample_pdf_bytes() -> bytes:
    """Generate a realistic 6-page Master Cloud Services Agreement in PDF format."""
    pages_data = [
        ("Page 1: PARTIES & RECITALS", [
            "MASTER CLOUD SERVICES AGREEMENT",
            "This Master Cloud Services Agreement (the Agreement) is entered into as of January 15, 2025 by and between:",
            "Veridocs Systems Inc. (Vendor), a Delaware corporation with offices at 100 Enterprise Way, Suite 400, San Francisco, CA 94105, and",
            "Acme Global Logistics LLC (Customer), a Delaware limited liability company with offices at 500 Commerce Blvd, Chicago, IL 60601.",
            "",
            "RECITALS:",
            "WHEREAS, Vendor provides an enterprise document intelligence and retrieval-augmented verification software-as-a-service platform; and",
            "WHEREAS, Customer desires to subscribe to and utilize the Platform for its corporate logistics operations under the terms and conditions set forth herein.",
            "NOW, THEREFORE, in consideration of the mutual covenants herein contained, the parties agree as follows:"
        ]),
        ("Page 2: SUBSCRIPTION SCOPE & ACCESS TERMS", [
            "SECTION 1: SCOPE OF SERVICES & ACCESS RIGHTS",
            "1.1 Subscription Grant. Vendor grants Customer a non-exclusive, non-transferable, worldwide subscription to access and use the Veridocs Platform during the Subscription Term.",
            "1.2 Authorized Users. Access is limited to Customer employees and contractors designated as Authorized Users, not to exceed 250 named seats without additional licensing fees.",
            "1.3 Permitted Data Types. Customer may upload PDF, TXT, and related unstructured documents for parsing, vector embedding, and real-time semantic verification.",
            "1.4 Prohibited Use. Customer shall not reverse engineer, decompile, or attempt to derive the underlying vector retrieval algorithms, nor use the platform for high-risk autonomous defense systems."
        ]),
        ("Page 3: PAYMENT TERMS, INVOICING & FEES", [
            "SECTION 2: FEES, TAXES & PAYMENT SCHEDULE",
            "2.1 Annual Subscription Fee. The baseline annual platform fee is USD $120,000, invoiced annually in advance on thirty (30) days payment terms.",
            "2.2 Overages. Ingestion volume exceeding 50,000 document pages per calendar month shall be billed at $0.02 per indexed page.",
            "2.3 Late Penalties. Any undisputed invoice unpaid after thirty (30) calendar days from receipt shall accrue interest at 1.5% per month or the statutory maximum.",
            "2.4 Taxes. All amounts payable are exclusive of federal, state, local, or value-added taxes, which remain the sole responsibility of Customer."
        ]),
        ("Page 4: SERVICE LEVEL AGREEMENT & AVAILABILITY", [
            "SECTION 3: SERVICE LEVEL AGREEMENT (SLA) & UPTIME",
            "3.1 Guaranteed Availability. Vendor guarantees a Monthly Uptime Percentage of at least 99.9% across all production API and web interfaces.",
            "3.2 Exclusions. Downtime shall exclude Scheduled Maintenance (not to exceed 4 hours per calendar month with 48 hours advance notice) and Force Majeure events.",
            "3.3 Service Credits. If Monthly Uptime drops below 99.9%, Customer is eligible for service credits as follows:",
            "    - 99.0% to 99.89%: 10% credit of monthly billing equivalent",
            "    - 95.0% to 98.99%: 25% credit of monthly billing equivalent",
            "    - Below 95.0%: 50% credit of monthly billing equivalent."
        ]),
        ("Page 5: DATA SECURITY, PRIVACY & CONFIDENTIALITY", [
            "SECTION 4: DATA PROTECTION & PRIVACY",
            "4.1 Customer Data Ownership. Customer retains all right, title, and ownership in Customer Data uploaded to the Platform.",
            "4.2 Security Controls. Vendor implements AES-256 encryption at rest and TLS 1.3 in transit. Customer document vectors are stored in isolated SQLite partition databases.",
            "4.3 LLM Data Isolation. Vendor warrants that Customer Data and query texts are never utilized to train third-party foundation models without express written authorization.",
            "4.4 Data Retention & Deletion. Upon contract termination, Vendor shall permanently expunge all Customer documents and vector embeddings within thirty (30) days."
        ]),
        ("Page 6: INDEMNIFICATION & LIMITATION OF LIABILITY", [
            "SECTION 5: LIMITATION OF LIABILITY & GOVERNING LAW",
            "5.1 Liability Cap. Under no circumstances shall either party aggregate cumulative liability arising out of this Agreement exceed USD $500,000.",
            "5.2 Consequential Damages Waiver. Neither party shall be liable for lost profits, loss of goodwill, punitive, or consequential damages.",
            "5.3 IP Indemnification. Vendor shall defend and indemnify Customer against third-party claims alleging that the Platform infringes any US patent or copyright.",
            "5.4 Governing Law. This Agreement shall be governed by and construed in accordance with the laws of the State of Delaware, without regard to conflict of laws principles."
        ])
    ]

    font_obj = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    num_pages = len(pages_data)
    catalog = "<< /Type /Catalog /Pages 2 0 R >>"
    pages_kids = " ".join([f"{4 + 2*i} 0 R" for i in range(num_pages)])
    pages_obj = f"<< /Type /Pages /Kids [{pages_kids}] /Count {num_pages} >>"
    all_objs = {1: catalog, 2: pages_obj, 3: font_obj}

    for i, (title, lines) in enumerate(pages_data):
        page_id = 4 + 2 * i
        content_id = 5 + 2 * i
        stream_lines = ["BT", "/F1 11 Tf", "50 750 Td"]
        for line in lines:
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            stream_lines.append(f"({escaped}) Tj")
            stream_lines.append("0 -20 Td")
        stream_lines.append("ET")
        stream_text = "\n".join(stream_lines)
        stream_bytes = stream_text.encode("latin1")

        content_str = f"<< /Length {len(stream_bytes)} >>\nstream\n{stream_text}\nendstream"
        page_str = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {content_id} 0 R /Resources << /Font << /F1 3 0 R >> >> >>"
        all_objs[page_id] = page_str
        all_objs[content_id] = content_str

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = {}
    for oid in sorted(all_objs.keys()):
        offsets[oid] = out.tell()
        out.write(f"{oid} 0 obj\n{all_objs[oid]}\nendobj\n".encode("latin1"))

    xref_offset = out.tell()
    total_objs = max(all_objs.keys()) + 1
    out.write(f"xref\n0 {total_objs}\n0000000000 65535 f \n".encode("latin1"))
    for oid in range(1, total_objs):
        out.write(f"{offsets[oid]:010d} 00000 n \n".encode("latin1"))

    out.write(f"trailer\n<< /Size {total_objs} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin1"))
    return out.getvalue()
