"""
Document Insights Engine for DocuMind AI.
Generates executive summaries, suggested questions, and extracts key entities
immediately after document upload.
"""

import re
import logging
import time
from typing import List, Dict, Optional, Tuple
from collections import Counter

from models import (
    DocumentInsights,
    ExecutiveSummary,
    EntityInfo,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Entity Extraction (regex-based, no spaCy dependency)
# ──────────────────────────────────────────────

# Common patterns for entity extraction
MONEY_PATTERN = re.compile(
    r'[\$€£¥₹]\s*\d[\d,]*(?:\.\d{1,2})?\s*(?:million|billion|trillion|mn|bn|M|B|K)?'
    r'|\d[\d,]*(?:\.\d{1,2})?\s*(?:dollars|euros|pounds|USD|EUR|GBP|INR)',
    re.IGNORECASE
)

DATE_PATTERN = re.compile(
    r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}'
    r'|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}'
    r'|\b(?:Q[1-4])\s+\d{4}'
    r'|\b(?:FY|CY)\s*\d{2,4}'
    r'|\b\d{4}\b(?=\s*(?:annual|fiscal|report|quarter))',
    re.IGNORECASE
)

PERCENTAGE_PATTERN = re.compile(
    r'\d+(?:\.\d+)?\s*%'
    r'|\d+(?:\.\d+)?\s+percent',
    re.IGNORECASE
)

# Capitalized multi-word names that likely are organizations or people
ORG_PATTERN = re.compile(
    r'\b(?:[A-Z][a-z]+(?:\s+(?:Inc|Corp|Ltd|LLC|Co|Group|Holdings|International|Technologies|Solutions|Partners|Association|Foundation|Institute|University|Commission|Committee|Department|Agency|Board))+\.?)\b'
)

PERSON_PATTERN = re.compile(
    r'\b(?:Mr|Mrs|Ms|Dr|Prof|CEO|CFO|CTO|President|Director|Chairman|Secretary)\.\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})'
)

LOCATION_PATTERN = re.compile(
    r'\b(?:New York|San Francisco|London|Tokyo|Beijing|Shanghai|Mumbai|Delhi|Singapore|Hong Kong|Dubai|'
    r'California|Texas|Florida|Illinois|Washington|Virginia|Massachusetts|'
    r'United States|United Kingdom|European Union|China|India|Japan|Germany|France|Canada|Australia)\b'
)


def extract_entities(chunks: List[Dict]) -> List[EntityInfo]:
    """
    Extract named entities from document chunks using regex patterns.
    Groups and deduplicates entities.
    """
    entities: Dict[str, Dict] = {}  # key: (type, normalized_value)

    full_text = "\n".join(c["text"] for c in chunks)

    # Extract monetary values
    for match in MONEY_PATTERN.finditer(full_text):
        value = match.group().strip()
        key = f"MONEY:{value.lower()}"
        if key not in entities:
            entities[key] = {"entity_type": "MONEY", "value": value, "count": 0}
        entities[key]["count"] += 1

    # Extract dates
    for match in DATE_PATTERN.finditer(full_text):
        value = match.group().strip()
        key = f"DATE:{value.lower()}"
        if key not in entities:
            entities[key] = {"entity_type": "DATE", "value": value, "count": 0}
        entities[key]["count"] += 1

    # Extract percentages
    for match in PERCENTAGE_PATTERN.finditer(full_text):
        value = match.group().strip()
        key = f"PERCENTAGE:{value.lower()}"
        if key not in entities:
            entities[key] = {"entity_type": "PERCENTAGE", "value": value, "count": 0}
        entities[key]["count"] += 1

    # Extract organizations
    for match in ORG_PATTERN.finditer(full_text):
        value = match.group().strip()
        if len(value) > 3:
            key = f"ORG:{value.lower()}"
            if key not in entities:
                entities[key] = {"entity_type": "ORGANIZATION", "value": value, "count": 0}
            entities[key]["count"] += 1

    # Extract people
    for match in PERSON_PATTERN.finditer(full_text):
        value = match.group(1).strip() if match.group(1) else match.group().strip()
        key = f"PERSON:{value.lower()}"
        if key not in entities:
            entities[key] = {"entity_type": "PERSON", "value": value, "count": 0}
        entities[key]["count"] += 1

    # Extract locations
    for match in LOCATION_PATTERN.finditer(full_text):
        value = match.group().strip()
        key = f"LOCATION:{value.lower()}"
        if key not in entities:
            entities[key] = {"entity_type": "LOCATION", "value": value, "count": 0}
        entities[key]["count"] += 1

    # Convert to EntityInfo objects, sorted by count
    entity_list = [
        EntityInfo(
            entity_type=e["entity_type"],
            value=e["value"],
            count=e["count"]
        )
        for e in entities.values()
    ]
    entity_list.sort(key=lambda x: x.count, reverse=True)

    # Limit to top 50 entities
    return entity_list[:50]


# ──────────────────────────────────────────────
# Insights Generation
# ──────────────────────────────────────────────

def generate_document_insights(
    session_id: str,
    chunks: List[Dict],
    llm_service=None,
    total_pages: int = 0
) -> DocumentInsights:
    """
    Generate comprehensive document insights including:
    - Executive summary
    - Suggested questions
    - Key entities

    Args:
        session_id: Current session identifier
        chunks: Processed document chunks
        llm_service: Initialized FreeLLMService instance
        total_pages: Total document pages

    Returns:
        DocumentInsights with all generated data
    """
    start_time = time.time()

    # 1. Extract entities (fast, no LLM needed)
    logger.info("Extracting entities...")
    key_entities = extract_entities(chunks)
    logger.info(f"Found {len(key_entities)} entities")

    # 2. Generate summary & suggested questions (single fast call)
    executive_summary = None
    suggested_questions = []

    if llm_service:
        try:
            if hasattr(llm_service, "generate_summary_and_questions"):
                logger.info("Generating unified executive summary & questions in single LLM call...")
                summary_dict, questions = llm_service.generate_summary_and_questions(chunks)
                executive_summary = ExecutiveSummary(
                    purpose=summary_dict.get("purpose", ""),
                    key_findings=summary_dict.get("key_findings", []),
                    risks=summary_dict.get("risks", []),
                    conclusions=summary_dict.get("conclusions", [])
                )
                suggested_questions = questions
            else:
                logger.info("Generating executive summary...")
                summary_dict = llm_service.generate_summary(chunks)
                executive_summary = ExecutiveSummary(
                    purpose=summary_dict.get("purpose", ""),
                    key_findings=summary_dict.get("key_findings", []),
                    risks=summary_dict.get("risks", []),
                    conclusions=summary_dict.get("conclusions", [])
                )
                suggested_questions = llm_service.generate_suggested_questions(chunks)
        except Exception as e:
            logger.error(f"Insights generation failed: {e}")
            suggested_questions = _default_questions()

    elapsed_ms = (time.time() - start_time) * 1000

    return DocumentInsights(
        session_id=session_id,
        executive_summary=executive_summary,
        suggested_questions=suggested_questions or _default_questions(),
        key_entities=key_entities,
        total_pages=total_pages,
        total_chunks=len(chunks),
        processing_time_ms=elapsed_ms
    )


def _default_questions() -> List[str]:
    """Fallback questions when LLM-based generation fails."""
    return [
        "What is the main topic of this document?",
        "What are the key findings or conclusions?",
        "Can you provide a brief summary?",
        "What are the most important data points?",
        "Are there any risks or concerns mentioned?",
    ]
