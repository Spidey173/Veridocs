"""
Entity Resolution and Canonicalization for Knowledge Graph.
Performs:
1. Legal corporate suffix normalization (Corp, Inc, LLC, Ltd, Group, etc.)
2. Fuzzy string matching via rapidfuzz (token_set_ratio / token_sort_ratio)
3. Alias tracking across varying document naming formats
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from rapidfuzz import fuzz

from config import get_settings

logger = logging.getLogger(__name__)

LEGAL_SUFFIXES = [
    r"\b(?:corp(?:oration)?|inc(?:orporated)?|llc|l\.l\.c\.|ltd|limited|holdings|group|partners|co|company|services|technologies|solutions)\b",
    r"\b(?:gmbh|s\.a\.|plc|bv|nv)\b",
]


def strip_legal_suffixes(name: str) -> str:
    """Strips corporate legal suffixes and trims extraneous punctuation."""
    clean = re.sub(r"[\'\".,;]+", " ", name)
    for pat in LEGAL_SUFFIXES:
        clean = re.sub(pat, " ", clean, flags=re.IGNORECASE)
    # Collapse whitespace
    clean = " ".join(clean.split()).strip()
    return clean if clean else name.strip()


def normalize_canonical_key(name: str, label: str) -> str:
    """Generates standard slug identifier for graph nodes."""
    stripped = strip_legal_suffixes(name).lower()
    slug = re.sub(r"[^a-z0-9]+", "_", stripped).strip("_")
    prefix = label.lower()[:4]
    return f"{prefix}:{slug}" if slug else f"{prefix}:{name.lower()}"


class EntityResolver:
    """Resolves raw entity names to existing canonical graph nodes or creates new ones."""

    def __init__(self, similarity_threshold: Optional[float] = None):
        settings = get_settings()
        self.threshold = similarity_threshold or settings.GRAPH_RESOLUTION_SIMILARITY_THRESHOLD

    def resolve_entity(self, raw_name: str, label: str, existing_nodes: List[Dict[str, Any]]) -> Tuple[str, str, bool]:
        """
        Resolves an entity to an existing canonical node or returns new canonical parameters.
        Returns: (node_id, canonical_name, is_existing_match)
        """
        clean_raw = raw_name.strip()
        stripped_candidate = strip_legal_suffixes(clean_raw).lower()

        best_score = 0.0
        best_node_id = None
        best_canonical = None

        for node in existing_nodes:
            if node.get("label") != label:
                continue

            node_canonical = node.get("canonical_name", "")
            stripped_existing = strip_legal_suffixes(node_canonical).lower()

            # Exact stripped match
            if stripped_candidate and stripped_candidate == stripped_existing:
                return node["id"], node_canonical, True

            # Fuzzy comparison between stripped names
            score1 = fuzz.token_sort_ratio(stripped_candidate, stripped_existing)
            score2 = fuzz.token_set_ratio(stripped_candidate, stripped_existing)
            score = max(score1, score2)

            # Also check existing aliases
            for alias in node.get("aliases", []):
                s_alias = strip_legal_suffixes(alias).lower()
                a_score = fuzz.token_sort_ratio(stripped_candidate, s_alias)
                if a_score > score:
                    score = a_score

            if score > best_score:
                best_score = score
                best_node_id = node["id"]
                best_canonical = node_canonical

        if best_score >= self.threshold and best_node_id:
            logger.debug(f"Entity '{clean_raw}' resolved to existing node '{best_canonical}' (score: {best_score:.1f})")
            return str(best_node_id), str(best_canonical or clean_raw), True

        # Generate new canonical node
        canonical_name = strip_legal_suffixes(clean_raw)
        node_id = normalize_canonical_key(clean_raw, label)
        return node_id, canonical_name, False
