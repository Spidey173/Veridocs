import re
import logging
import time
from typing import List, Dict

from models import (
    DocumentInsights,
    ExecutiveSummary,
    EntityInfo,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Regular expressions for entity extraction
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
    """Extract money, dates, percentages, organizations, people, and locations."""
    entities: Dict[str, Dict] = {}

    full_text = "\n".join(c["text"] for c in chunks)

    # Monetary values
    for match in MONEY_PATTERN.finditer(full_text):
        value = match.group().strip()
        key = f"MONEY:{value.lower()}"
        if key not in entities:
            entities[key] = {"entity_type": "MONEY", "value": value, "count": 0}
        entities[key]["count"] += 1

    # Dates
    for match in DATE_PATTERN.finditer(full_text):
        value = match.group().strip()
        key = f"DATE:{value.lower()}"
        if key not in entities:
            entities[key] = {"entity_type": "DATE", "value": value, "count": 0}
        entities[key]["count"] += 1

    # Percentages
    for match in PERCENTAGE_PATTERN.finditer(full_text):
        value = match.group().strip()
        key = f"PERCENTAGE:{value.lower()}"
        if key not in entities:
            entities[key] = {"entity_type": "PERCENTAGE", "value": value, "count": 0}
        entities[key]["count"] += 1

    # Organizations
    for match in ORG_PATTERN.finditer(full_text):
        value = match.group().strip()
        if len(value) > 3:
            key = f"ORG:{value.lower()}"
            if key not in entities:
                entities[key] = {"entity_type": "ORGANIZATION", "value": value, "count": 0}
            entities[key]["count"] += 1

    # People
    for match in PERSON_PATTERN.finditer(full_text):
        value = match.group(1).strip() if match.group(1) else match.group().strip()
        key = f"PERSON:{value.lower()}"
        if key not in entities:
            entities[key] = {"entity_type": "PERSON", "value": value, "count": 0}
        entities[key]["count"] += 1

    # Locations
    for match in LOCATION_PATTERN.finditer(full_text):
        value = match.group().strip()
        key = f"LOCATION:{value.lower()}"
        if key not in entities:
            entities[key] = {"entity_type": "LOCATION", "value": value, "count": 0}
        entities[key]["count"] += 1

    entity_list = [
        EntityInfo(
            entity_type=e["entity_type"],
            value=e["value"],
            count=e["count"]
        )
        for e in entities.values()
    ]
    entity_list.sort(key=lambda x: x.count, reverse=True)

    return entity_list[:50]


def generate_document_insights(
    session_id: str,
    chunks: List[Dict],
    llm_service=None,
    total_pages: int = 0
) -> DocumentInsights:
    """Generate executive summary, questions, and extracted entities."""
    start_time = time.time()

    # Extract entities
    key_entities = extract_entities(chunks)

    # Generate summary and suggested questions
    executive_summary = None
    suggested_questions = []

    if llm_service:
        try:
            if hasattr(llm_service, "generate_summary_and_questions"):
                summary_dict, questions = llm_service.generate_summary_and_questions(chunks)
                executive_summary = ExecutiveSummary(
                    purpose=summary_dict.get("purpose", ""),
                    key_findings=summary_dict.get("key_findings", []),
                    risks=summary_dict.get("risks", []),
                    conclusions=summary_dict.get("conclusions", [])
                )
                suggested_questions = questions
            else:
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
    """Default questions if LLM is unavailable."""
    return [
        "What is the main topic of this document?",
        "What are the key findings or conclusions?",
        "Can you provide a brief summary?",
        "What are the most important data points?",
        "Are there any risks or concerns mentioned?",
    ]
