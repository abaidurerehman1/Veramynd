"""Hybrid retrieval: dense + BM25 → RRF → cross-encoder rerank."""

from .leaves import filter_alignable_leaves
from .models import Candidate, StandardDoc
from .pipeline import (
    DEFAULT_HYBRID_TOP_K,
    RetrieveError,
    hybrid_retrieve_standards,
    retrieve_and_rerank,
)
from .rerank import DEFAULT_RERANK_MODEL, DEFAULT_RERANK_TOP_N, RerankError
from .rrf import reciprocal_rank_fusion

__all__ = [
    "Candidate",
    "DEFAULT_HYBRID_TOP_K",
    "DEFAULT_RERANK_MODEL",
    "DEFAULT_RERANK_TOP_N",
    "RerankError",
    "RetrieveError",
    "StandardDoc",
    "filter_alignable_leaves",
    "hybrid_retrieve_standards",
    "reciprocal_rank_fusion",
    "retrieve_and_rerank",
]
