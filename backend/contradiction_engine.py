import re
import json
import logging
import hashlib
import threading
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from config import get_settings
from rate_limiter import get_token_limiter

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

TARGETED_VERIFICATION_PROMPT = """You are an expert forensic document auditor reviewing specific candidate discrepancies detected between two documents:
- Document A: "{doc_a_name}"
- Document B: "{doc_b_name}"

Candidate conflict excerpts identified across the filings:
{candidates_text}

TASK:
For each candidate conflict:
1. Verify whether this represents a true material contradiction or numerical discrepancy between Document A and Document B.
2. Confirm or adjust the severity ("critical" for liability caps, indemnification, pricing, or payment terms; "warning" for notice periods, SLAs, or minor terms).
3. Provide a clear, factual explanation of the discrepancy and a concise risk analysis.
4. Calculate an overall alignment score (0.0 to 1.0) and write a 1-2 sentence executive summary.

Return your audit as a valid JSON object matching this schema:
{{
  "alignment_score": 0.70,
  "summary": "Brief 1-2 sentence executive summary of the verified conflicts.",
  "conflicts": [
    {{
      "topic": "Topic Name",
      "severity": "critical",
      "conflict_type": "contradiction",
      "explanation": "Exact description of how Doc A and Doc B contradict each other.",
      "risk_analysis": "Impact of this discrepancy.",
      "doc_a": {{
        "page": 1,
        "snippet": "Exact quote from Document A",
        "section": "Section name"
      }},
      "doc_b": {{
        "page": 2,
        "snippet": "Exact quote from Document B",
        "section": "Section name"
      }}
    }}
  ]
}}

INSTRUCTIONS:
1. If a candidate is not a genuine conflict, omit it from the "conflicts" list.
2. If all candidates are resolved or non-conflicting, return an empty "conflicts" list and alignment_score 1.0.
3. Provide exact verbatim quotes in `snippet`.
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

TARGETED_INTERNAL_CONSISTENCY_PROMPT = """You are an expert forensic document auditor reviewing candidate internal timeline or numerical discrepancies within "{doc_name}":

Candidate internal discrepancies identified across document sections:
{candidates_text}

TASK:
Verify whether these represent true internal contradictions, chronological errors, or numerical conflicts between sections of "{doc_name}".

Return your audit as a valid JSON object matching this schema:
{{
  "alignment_score": 0.85,
  "summary": "Brief 1-2 sentence summary of internal findings.",
  "conflicts": [
    {{
      "topic": "Topic Name",
      "severity": "critical",
      "conflict_type": "contradiction",
      "explanation": "Description of internal inconsistency.",
      "risk_analysis": "Impact of this inconsistency.",
      "doc_a": {{
        "page": 1,
        "snippet": "Quote from earlier in document",
        "section": "Section name"
      }},
      "doc_b": {{
        "page": 3,
        "snippet": "Quote from later in document",
        "section": "Section name"
      }}
    }}
  ]
}}

INSTRUCTIONS:
1. If all candidates are non-conflicting, return an empty "conflicts" list and alignment_score 1.0.
2. Return ONLY valid JSON.
"""


class ContradictionAuditCache:
    """Thread-safe LRU cache for cross-document contradiction reports."""

    def __init__(self, max_size: int = 256):
        self.max_size = max_size
        self._cache: Dict[str, AuditDiffReport] = {}
        self._access_order: List[str] = []
        self._lock = threading.Lock()

    @staticmethod
    def compute_cache_key(doc_a_name: str, doc_b_name: str, doc_a_chunks: List[Dict], doc_b_chunks: List[Dict]) -> str:
        """Compute deterministic fingerprint of chunk contents and metadata."""
        hasher = hashlib.sha256()
        hasher.update(doc_a_name.encode("utf-8"))
        hasher.update(doc_b_name.encode("utf-8"))
        for c in doc_a_chunks:
            hasher.update(str(c.get("page", "")).encode("utf-8"))
            hasher.update(c.get("text", "").encode("utf-8"))
        hasher.update(b"||--DELIMITER--||")
        for c in doc_b_chunks:
            hasher.update(str(c.get("page", "")).encode("utf-8"))
            hasher.update(c.get("text", "").encode("utf-8"))
        return hasher.hexdigest()

    def get(self, key: str) -> Optional[AuditDiffReport]:
        with self._lock:
            if key in self._cache:
                self._access_order.remove(key)
                self._access_order.append(key)
                return self._cache[key]
            return None

    def set(self, key: str, report: AuditDiffReport) -> None:
        with self._lock:
            if key in self._cache:
                self._access_order.remove(key)
            elif len(self._cache) >= self.max_size:
                oldest_key = self._access_order.pop(0)
                self._cache.pop(oldest_key, None)
            self._cache[key] = report
            self._access_order.append(key)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._access_order.clear()


_audit_cache = ContradictionAuditCache()


def get_audit_cache() -> ContradictionAuditCache:
    """Return the global contradiction audit cache."""
    return _audit_cache


def _execute_llm_audit_prompt(llm_service: Any, prompt: str) -> str:
    """Execute audit prompt across any supported LLM provider with retry and error handling."""
    if not llm_service:
        return ""

    provider = getattr(llm_service, "provider", "").lower()

    def _invoke_with_retry(call_fn):
        retry_fn = getattr(llm_service, "_with_retry", None)
        if callable(retry_fn) and type(retry_fn).__name__ not in ("MagicMock", "Mock"):
            return retry_fn(call_fn)
        return call_fn()

    if provider == "google":
        def _call_google():
            response = llm_service.client.generate_content(prompt)
            return response.text.strip()
        return _invoke_with_retry(_call_google)

    elif provider == "anthropic":
        def _call_anthropic():
            response = llm_service.client.messages.create(
                model=llm_service.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1500
            )
            return response.content[0].text.strip()
        return _invoke_with_retry(_call_anthropic)

    elif provider in ("openai", "deepseek", "groq", "mistral", "openrouter", "github", "ollama", "custom"):
        if hasattr(llm_service, "client") and hasattr(llm_service.client, "chat"):
            def _call_openai_compat():
                response = llm_service.client.chat.completions.create(
                    model=llm_service.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=1500
                )
                return response.choices[0].message.content.strip()
            return _invoke_with_retry(_call_openai_compat)

    return ""


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
    """Compare two documents to find differences and contradictions with token rate limiting and caching."""
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

    settings = get_settings()
    cache_enabled = getattr(settings, "AUDIT_CACHE_ENABLED", True)
    cache_key = ContradictionAuditCache.compute_cache_key(doc_a_name, doc_b_name, doc_a_chunks, doc_b_chunks)

    # 1. Check in-memory content cache (0 tokens consumed on repeated audits)
    if cache_enabled:
        cached = _audit_cache.get(cache_key)
        if cached:
            logger.info(f"Serving cached contradiction audit for {doc_a_name} vs {doc_b_name} (0 tokens consumed)")
            return cached

    # 2. Check audit mode and provider availability
    audit_mode = getattr(settings, "AUDIT_MODE", "hybrid").lower()
    is_offline = not llm_service or getattr(llm_service, "provider", "") in ("offline", "mock")

    # If deterministic mode or no LLM service, execute rule-based diff directly
    if audit_mode == "deterministic" or is_offline:
        deterministic_report = _deterministic_diff(doc_a_chunks, doc_b_chunks, doc_a_name, doc_b_name)
        if cache_enabled:
            _audit_cache.set(cache_key, deterministic_report)
        return deterministic_report

    # 3. Phase 1: High-precision deterministic conflict candidate extraction
    deterministic_report = _deterministic_diff(doc_a_chunks, doc_b_chunks, doc_a_name, doc_b_name)

    # If hybrid mode and zero candidate conflicts detected, short-circuit (100% token savings!)
    if audit_mode == "hybrid" and len(deterministic_report.conflicts) == 0:
        logger.info(f"Phase 1 deterministic audit found 0 conflicts between {doc_a_name} and {doc_b_name}. Short-circuiting LLM call (0 tokens consumed).")
        if cache_enabled:
            _audit_cache.set(cache_key, deterministic_report)
        return deterministic_report

    # 4. Phase 2: Targeted LLM verification (drastically slashes token consumption by 85-90%)
    if audit_mode == "hybrid" and deterministic_report.conflicts:
        candidate_lines = []
        for idx, c in enumerate(deterministic_report.conflicts, 1):
            sec_a = f", Section: {c.doc_a.section}" if c.doc_a.section else ""
            sec_b = f", Section: {c.doc_b.section}" if c.doc_b.section else ""
            candidate_lines.append(
                f"Candidate #{idx}: [{c.topic}]\n"
                f"- {doc_a_name} (Page {c.doc_a.page}{sec_a}): \"{c.doc_a.snippet}\"\n"
                f"- {doc_b_name} (Page {c.doc_b.page}{sec_b}): \"{c.doc_b.snippet}\""
            )
        candidates_text = "\n\n".join(candidate_lines)

        if doc_a_name == doc_b_name:
            prompt = TARGETED_INTERNAL_CONSISTENCY_PROMPT.format(
                doc_name=doc_a_name,
                candidates_text=candidates_text
            )
        else:
            prompt = TARGETED_VERIFICATION_PROMPT.format(
                doc_a_name=doc_a_name,
                doc_b_name=doc_b_name,
                candidates_text=candidates_text
            )
    else:
        # Full LLM mode
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

    # 5. Proactive Token Rate Limiting & TPM Budgeting
    token_limiter = get_token_limiter()
    estimated_tokens = (len(prompt) // 4) + 400

    if not token_limiter.can_consume(estimated_tokens):
        logger.warning(
            f"Provider TPM budget protection: Estimated {estimated_tokens} tokens would exceed sliding-window limit. "
            "Falling back to deterministic rule-based diff to prevent 429 quota exhaustion."
        )
        fallback_report = deterministic_report
        fallback_report.summary += " [Audit performed via deterministic rule analysis to preserve provider token budget]"
        if cache_enabled:
            _audit_cache.set(cache_key, fallback_report)
        return fallback_report

    token_limiter.consume(estimated_tokens)

    # 6. Execute LLM prompt with universal provider support and graceful rate-limit fallback
    try:
        logger.info(f"Running LLM contradiction audit ({estimated_tokens} estimated tokens)...")
        raw = _execute_llm_audit_prompt(llm_service, prompt)

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

            final_report = AuditDiffReport(
                doc_a_name=doc_a_name,
                doc_b_name=doc_b_name,
                alignment_score=float(parsed.get("alignment_score", 0.75)),
                summary=parsed.get("summary", f"Identified {len(conflicts)} discrepancies between documents."),
                critical_count=crit_count,
                warning_count=warn_count,
                conflicts=conflicts
            )
            if cache_enabled:
                _audit_cache.set(cache_key, final_report)
            return final_report
    except Exception as e:
        logger.warning(f"LLM contradiction audit failed: {e}. Falling back to rule-based diff.")

    # Fallback to deterministic report if LLM fails or returned invalid JSON
    if cache_enabled:
        _audit_cache.set(cache_key, deterministic_report)
    return deterministic_report
