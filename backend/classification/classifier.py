"""
Document type classification:
Classifies documents as 'invoice' | 'contract' | 'research_paper' | 'resume' | 'other'
using LLM structured output with deterministic heuristic fallback.
"""

import json
import logging
from typing import Tuple, List, Dict, Any

try:
    import openai
except ImportError:
    openai = None
from config import get_settings

logger = logging.getLogger(__name__)

DOC_TYPES = ["invoice", "contract", "research_paper", "resume", "other"]

CLASSIFICATION_PROMPT = """You are an expert document classification engine.
Analyze the following text sample from the first two pages of a document and classify its document type into exactly one of:
- "invoice" (bills, invoices, purchase orders, fee statements, receipts)
- "contract" (agreements, NDAs, terms of service, MSAs, licenses, leases)
- "research_paper" (academic papers, conference proceedings, preprints, technical reports)
- "resume" (curriculum vitae, resumes, professional profiles)
- "other" (general correspondence, marketing flyers, reports, notes)

Output a strict JSON object with:
{
  "doc_type": "invoice" | "contract" | "research_paper" | "resume" | "other",
  "confidence": float between 0.0 and 1.0,
  "reasoning": "brief justification"
}
"""


def classify_document(pages: List[Dict[str, Any]], filename: str = "") -> Tuple[str, float]:
    """
    Classify document type using first ~2 pages of text.
    Returns (doc_type, confidence).
    """
    settings = get_settings()

    # Collect sample text from first 2 pages
    sample_pages = pages[:2]
    sample_text = "\n\n--- PAGE BREAK ---\n\n".join([p.get("text", "") for p in sample_pages]).strip()

    if not sample_text:
        return "other", 0.5

    # 1. Try LLM classification if configured
    if settings.is_llm_configured():
        try:
            client = openai.OpenAI(base_url=settings.LLM_BASE_URL, api_key=settings.LLM_API_KEY, timeout=12.0)

            prompt = f"Filename: {filename}\n\nDocument Content:\n{sample_text[:3000]}"
            response = client.chat.completions.create(
                model=settings.EXTRACTION_MODEL or settings.LLM_MODEL or "gpt-4o-mini",
                messages=[{"role": "system", "content": CLASSIFICATION_PROMPT}, {"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=150,
            )

            raw = response.choices[0].message.content or "{}"
            parsed = json.loads(raw)
            dt = str(parsed.get("doc_type", "other")).lower().strip()
            conf = float(parsed.get("confidence", 0.85))

            if dt in DOC_TYPES:
                logger.info(f"LLM classified '{filename}' as {dt} (confidence: {conf:.2f})")
                return dt, round(conf, 2)
        except Exception as e:
            logger.debug(f"LLM classification failed for '{filename}': {e}. Using heuristic classifier.")

    # 2. Deterministic heuristic fallback
    return classify_document_heuristics(sample_text, filename)


def classify_document_heuristics(text: str, filename: str = "") -> Tuple[str, float]:
    """Fast deterministic rule-based classifier matching keywords and structural cues."""
    t = text.lower()
    fn = filename.lower()

    # Invoice indicators
    invoice_score = 0
    if any(k in fn for k in ["invoice", "inv-", "receipt", "bill", "order"]):
        invoice_score += 3
    if "invoice" in t or "receipt" in t:
        invoice_score += 2
    if "invoice #" in t or "invoice number" in t or "invoice:" in t or "receipt number" in t:
        invoice_score += 4
    if "due date" in t or "payment due" in t or "due on receipt" in t:
        invoice_score += 3
    if "amount due" in t or "balance due" in t or "total amount due" in t:
        invoice_score += 3
    if "subtotal" in t and "total" in t:
        invoice_score += 4
    if "remit to" in t or "bill to" in t or "payment terms" in t:
        invoice_score += 2

    # Contract indicators
    contract_score = 0
    if any(k in fn for k in ["agreement", "contract", "nda", "msa", "terms", "lease"]):
        contract_score += 3
    if any(
        p in t
        for p in [
            "master services agreement",
            "services agreement",
            "non-disclosure agreement",
            "lease agreement",
            "license agreement",
            "master software",
            "mutual non-disclosure",
        ]
    ):
        contract_score += 5
    if "confidential information" in t or "confidentiality period" in t:
        contract_score += 3
    if "in witness whereof" in t or "parties hereby agree" in t or "by and between" in t:
        contract_score += 4
    if "governing law" in t or "jurisdiction" in t:
        contract_score += 3
    if "term and termination" in t or "limitation of liability" in t or "lease term" in t:
        contract_score += 3

    # Research paper indicators
    paper_score = 0
    if any(k in fn for k in ["paper", "arxiv", "proceedings", "conference", "journal"]):
        paper_score += 3
    if "abstract" in t:
        paper_score += 3
    if "abstract" in t and any(
        w in t for w in ["introduction", "references", "key findings", "datasets", "limitations", "venue"]
    ):
        paper_score += 5
    if "methodology" in t or "experimental setup" in t or "dataset" in t:
        paper_score += 3
    if "related work" in t or "conclusion" in t or "authors:" in t:
        paper_score += 2

    # Resume indicators
    resume_score = 0
    if any(k in fn for k in ["resume", "cv", "curriculum_vitae"]):
        resume_score += 4
    if "education" in t and ("experience" in t or "employment" in t):
        resume_score += 4
    if "skills" in t and ("projects" in t or "certifications" in t):
        resume_score += 3

    scores = {
        "invoice": invoice_score,
        "contract": contract_score,
        "research_paper": paper_score,
        "resume": resume_score,
    }

    best_type, best_score = max(scores.items(), key=lambda x: x[1])
    if best_score >= 4:
        confidence = min(0.98, 0.65 + (best_score * 0.05))
        return best_type, round(confidence, 2)

    return "other", 0.60
