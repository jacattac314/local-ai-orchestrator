"""Entity resolution package for matching models across sources."""

from orchestrator.resolution.normalizer import NameNormalizer
from orchestrator.resolution.matcher import SimilarityMatcher
from orchestrator.resolution.resolver import EntityResolver
from orchestrator.resolution.repository import AliasRepository

__all__ = [
    "NameNormalizer",
    "SimilarityMatcher",
    "EntityResolver",
    "AliasRepository",
]
