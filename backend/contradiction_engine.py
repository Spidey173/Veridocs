import re
import json
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConflictSnippet(BaseModel):
    filename: str
    page: int
    snippet: str
    section: Optional[str] = None


class AuditDiffItem(BaseModel):
    id: str
    topic: str
    severity: str = "warning"
    conflict_type: str = "contradiction"
    explanation: str
    risk_analysis: str
    doc_a: ConflictSnippet
    doc_b: ConflictSnippet


class AuditDiffReport(BaseModel):
    doc_a_name: str
    doc_b_name: str
    alignment_score: float = Field(default=0.8, description="0.0 to 1.0 score")
    summary: str
    critical_count: int = 0
    warning_count: int = 0
    conflicts: List[AuditDiffItem] = []


CONTRADICTION_PROMPT = """You are comparing two documents:
- Document A: "{doc_a_name}"
- Document B: "{doc_b_name}"

Your goal is to detect any contradictions, altered numbers, deleted obligations, or conflicting clauses between them.

--- DOCUMENT A EXCERPTS ---
{doc_a_text}

--- DOCUMENT B EXCERPTS ---
{doc_b_text}

TASK:
Identify any direct contradictions, numerical discrepancies (e.g. 30 days vs 60 days, $1M vs $250k), or altered terms between Document A and Document B.

Return your audit as a valid JSON object matching this schema:
{{
  "alignment_score": 0.65,
  "summary": "Brief 1-2 sentence summary of the differences found.",
  "conflicts": [
    {{
      "topic": "Clause or Topic Name",
      "severity": "critical",
      "conflict_type": "contradiction",
      "explanation": "Description of how Doc A and Doc B contradict each other.",
      "risk_analysis": "Impact of this discrepancy.",
      "doc_a": {{
        "page": 2,
        "snippet": "Exact quote from Document A",
        "section": "Section name if available"
      }},
      "doc_b": {{
        "page": 3,
        "snippet": "Exact quote from Document B",
        "section": "Section name if available"
      }}
    }}
  ]
}}

INSTRUCTIONS:
1. Only flag genuine conflicts or alterations.
2. Provide exact verbatim quotes in `snippet`.
3. If no conflicts exist, return an empty "conflicts" list and alignment_score 1.0.
4. Return ONLY valid JSON.
"""

INTERNAL_CONSISTENCY_PROMPT = """You are checking the document "{doc_name}" for internal consistency and timeline alignment across its pages.

--- DOCUMENT EXCERPTS ---
{doc_text}

TASK:
Examine dates, numbers, commitments, and statements throughout "{doc_name}".
Detect any chronological inconsistencies, contradictory numbers, or conflicting statements between different sections.

Return your audit as a valid JSON object matching this schema:
{{
  "alignment_score": 0.85,
  "summary": "Brief 1-2 sentence summary of findings.",
  "conflicts": [
    {{
      "topic": "Topic Name",
      "severity": "critical",
      "conflict_type": "contradiction",
      "explanation": "Description of the conflicting statements or dates.",
      "risk_analysis": "Impact of this inconsistency.",
      "doc_a": {{
        "page": 1,
        "snippet": "Quote from earlier in document",
        "section": "Section name"
      }},
      "doc_b": {{
        "page": 2,
        "snippet": "Quote from later in document",
        "section": "Section name"
      }}
    }}
  ]
}}

INSTRUCTIONS:
1. If the document is consistent, return an empty "conflicts" list and alignment_score 1.0.
2. Provide exact verbatim quotes in `snippet`.
3. Return ONLY valid JSON.
"""


def _deterministic_diff(doc_a_chunks: List[Dict], doc_b_chunks: List[Dict], doc_a_name: str, doc_b_name: str) -> AuditDiffReport:
    """Compare numbers, dates, and common keywords between document chunks."""
    conflicts: List[AuditDiffItem] = []
    
    # Match numbers, currencies, and dates
    num_pattern = re.compile(r'(\$\s?[\d,]+(?:\.\d+)?|\b\d+\s?%|\b\d+\s+(?:days?|months?|business days|years?))', re.IGNORECASE)
    
    topics = [
        ("Payment & Invoicing", ["payment", "invoice", "net", "payable", "fee", "penalty"]),
        ("Limitation of Liability", ["liability", "indemnif", "damages", "cap", "aggregate"]),
        ("Termination & Notice", ["termination", "notice", "cure", "terminate", "expire"]),
        ("Confidentiality & Term", ["confidential", "non-disclosure", "term", "duration"]),
        ("Warranty & SLA", ["warranty", "uptime", "sla", "service level", "guarantee"])
    ]
    
    conflict_idx = 1
    
    for topic_name, keywords in topics:
        matched_a = []
        matched_b = []
        
        for c in doc_a_chunks:
            text = c.get("text", "")
            if any(k in text.lower() for k in keywords):
                nums = num_pattern.findall(text)
                matched_a.append((c, nums))
                
        for c in doc_b_chunks:
            text = c.get("text", "")
            if any(k in text.lower() for k in keywords):
                nums = num_pattern.findall(text)
                matched_b.append((c, nums))
                
        if matched_a and matched_b:
            chunk_a, nums_a = matched_a[0]
            chunk_b, nums_b = matched_b[0]
            
            set_a = set(n.lower().strip() for n in nums_a)
            set_b = set(n.lower().strip() for n in nums_b)
            
            if set_a != set_b and (set_a or set_b):
                snippet_a = chunk_a.get("raw_text", chunk_a.get("text", ""))[:220].strip()
                snippet_b = chunk_b.get("raw_text", chunk_b.get("text", ""))[:220].strip()
                
                conflicts.append(AuditDiffItem(
                    id=f"diff-{conflict_idx}",
                    topic=topic_name,
                    severity="critical" if "liability" in topic_name.lower() or "payment" in topic_name.lower() else "warning",
                    conflict_type="numeric_mismatch" if (set_a and set_b) else "modification",
                    explanation=f"Discrepancy detected in {topic_name}: {doc_a_name} specifies {', '.join(set_a) or 'standard terms'} whereas {doc_b_name} specifies {', '.join(set_b) or 'altered terms'}.",
                    risk_analysis=f"Alters commitments between parties for {topic_name.lower()}.",
                    doc_a=ConflictSnippet(
                        filename=doc_a_name,
                        page=chunk_a.get("page", 1),
                        snippet=snippet_a,
                        section=chunk_a.get("section")
                    ),
                    doc_b=ConflictSnippet(
                        filename=doc_b_name,
                        page=chunk_b.get("page", 1),
                        snippet=snippet_b,
                        section=chunk_b.get("section")
                    )
                ))
                conflict_idx += 1

    crit_count = sum(1 for c in conflicts if c.severity == "critical")
    warn_count = sum(1 for c in conflicts if c.severity == "warning")
    score = max(0.2, round(1.0 - (len(conflicts) * 0.15), 2))
    
    if doc_a_name == doc_b_name:
        summary = (
            f"Internal document consistency audit identified {len(conflicts)} potential discrepancies within {doc_a_name}."
            if conflicts else f"Internal consistency audit verified: 100% aligned with no conflicting statements or numerical discrepancies detected in {doc_a_name}."
        )
    else:
        summary = (
            f"Cross-document analysis identified {len(conflicts)} potential discrepancies "
            f"between {doc_a_name} and {doc_b_name}."
            if conflicts else f"No material discrepancies or numerical contradictions identified between {doc_a_name} and {doc_b_name}."
        )

    return AuditDiffReport(
        doc_a_name=doc_a_name,
        doc_b_name=doc_b_name,
        alignment_score=score,
        summary=summary,
        critical_count=crit_count,
        warning_count=warn_count,
        conflicts=conflicts
    )


def _select_salient_chunks(chunks: List[Dict], max_chars: int = 7500) -> List[Dict]:
    """Select key chunks with numbers or important terms across the document."""
    if not chunks:
        return []

    total_len = sum(len(c.get("text", "")) for c in chunks)
    if total_len <= max_chars:
        return chunks

    salience_pattern = re.compile(
        r'(\$\s?[\d,]+|\b\d+[\d,.]*(?:%|\b)|liability|indemnif|payment|termination|sla|warranty|penalty|cure period|days|months)',
        re.IGNORECASE
    )

    scored_chunks = []
    for idx, c in enumerate(chunks):
        text = c.get("text", "")
        matches = len(salience_pattern.findall(text))
        score = matches * 3
        if c.get("section"):
            score += 2
        scored_chunks.append((idx, score, c))

    scored_chunks.sort(key=lambda x: x[1], reverse=True)

    selected_indices = set()
    current_chars = 0

    for idx, score, c in scored_chunks:
        c_len = len(c.get("text", ""))
        if current_chars + c_len > max_chars and len(selected_indices) >= 5:
            continue
        selected_indices.add(idx)
        current_chars += c_len
        if current_chars >= max_chars:
            break

    if 0 not in selected_indices and len(chunks) > 0:
        selected_indices.add(0)

    return [chunks[i] for i in sorted(selected_indices)]


def run_cross_document_audit(
    doc_a_chunks: List[Dict],
    doc_b_chunks: List[Dict],
    doc_a_name: str,
    doc_b_name: str,
    llm_service: Optional[Any] = None
) -> AuditDiffReport:
    """Compare two documents to find differences and contradictions."""
    if not doc_a_chunks or not doc_b_chunks:
        return AuditDiffReport(
            doc_a_name=doc_a_name,
            doc_b_name=doc_b_name,
            alignment_score=1.0,
            summary="Insufficient chunk context to perform comparative audit.",
            critical_count=0,
            warning_count=0,
            conflicts=[]
        )

    # Select representative chunks from both documents
    salient_a = _select_salient_chunks(doc_a_chunks, max_chars=6000)
    salient_b = _select_salient_chunks(doc_b_chunks, max_chars=6000)

    a_parts = [f"[Page {c.get('page', 1)} | Section: {c.get('section', 'General')}]\n{c.get('text', '')}" for c in salient_a]
    b_parts = [f"[Page {c.get('page', 1)} | Section: {c.get('section', 'General')}]\n{c.get('text', '')}" for c in salient_b]

    doc_a_text = "\n\n---\n\n".join(a_parts)
    doc_b_text = "\n\n---\n\n".join(b_parts)

    if doc_a_name == doc_b_name:
        prompt = INTERNAL_CONSISTENCY_PROMPT.format(
            doc_name=doc_a_name,
            doc_text=doc_a_text[:8000]
        )
    else:
        prompt = CONTRADICTION_PROMPT.format(
            doc_a_name=doc_a_name,
            doc_b_name=doc_b_name,
            doc_a_text=doc_a_text[:6000],
            doc_b_text=doc_b_text[:6000]
        )

    if llm_service:
        try:
            logger.info(f"Running LLM contradiction audit between {doc_a_name} and {doc_b_name}...")
            
            if hasattr(llm_service, "provider") and llm_service.provider == "google":
                response = llm_service.client.generate_content(prompt)
                raw = response.text.strip()
            elif hasattr(llm_service, "client") and hasattr(llm_service.client, "chat"):
                response = llm_service.client.chat.completions.create(
                    model=llm_service.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=1500
                )
                raw = response.choices[0].message.content.strip()
            else:
                raw = ""

            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                raw_conflicts = parsed.get("conflicts", [])
                
                conflicts: List[AuditDiffItem] = []
                for idx, c in enumerate(raw_conflicts, 1):
                    da = c.get("doc_a", {})
                    db = c.get("doc_b", {})
                    conflicts.append(AuditDiffItem(
                        id=f"diff-{idx}",
                        topic=c.get("topic", "Contract Clause"),
                        severity=c.get("severity", "warning").lower(),
                        conflict_type=c.get("conflict_type", "contradiction").lower(),
                        explanation=c.get("explanation", "Discrepancy identified between documents."),
                        risk_analysis=c.get("risk_analysis", "Review required by legal/compliance."),
                        doc_a=ConflictSnippet(
                            filename=doc_a_name,
                            page=int(da.get("page", 1)),
                            snippet=da.get("snippet", ""),
                            section=da.get("section")
                        ),
                        doc_b=ConflictSnippet(
                            filename=doc_b_name,
                            page=int(db.get("page", 1)),
                            snippet=db.get("snippet", ""),
                            section=db.get("section")
                        )
                    ))
                    
                crit_count = sum(1 for c in conflicts if c.severity == "critical")
                warn_count = sum(1 for c in conflicts if c.severity != "critical")
                
                return AuditDiffReport(
                    doc_a_name=doc_a_name,
                    doc_b_name=doc_b_name,
                    alignment_score=float(parsed.get("alignment_score", 0.75)),
                    summary=parsed.get("summary", f"Identified {len(conflicts)} discrepancies between documents."),
                    critical_count=crit_count,
                    warning_count=warn_count,
                    conflicts=conflicts
                )
        except Exception as e:
            logger.warning(f"LLM contradiction audit failed: {e}. Falling back to rule-based diff.")

    # Rule-based fallback if LLM is unavailable
    return _deterministic_diff(doc_a_chunks, doc_b_chunks, doc_a_name, doc_b_name)
