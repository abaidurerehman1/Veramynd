"""In-memory BM25 over normalized standard ``embed_text`` (no external deps)."""

from __future__ import annotations

import math
import re
from collections import Counter

from .models import StandardDoc

# Keep dotted codes (1.f.pa.4) and words as tokens.
_TOKEN = re.compile(r"[a-z0-9]+(?:\.[a-z0-9]+)*", re.I)


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


class StandardsBm25Index:
    """Okapi BM25 over a fixed standards corpus."""

    def __init__(
        self,
        docs: list[StandardDoc],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if k1 < 0 or b < 0 or b > 1:
            raise ValueError(f"invalid BM25 params k1={k1} b={b}")
        self.k1 = k1
        self.b = b
        self.docs = list(docs)
        self._tokens: list[list[str]] = [tokenize(d.text) for d in self.docs]
        self._doc_len = [len(toks) or 1 for toks in self._tokens]
        self._avgdl = (
            sum(self._doc_len) / len(self._doc_len) if self._doc_len else 1.0
        )
        df: Counter[str] = Counter()
        for toks in self._tokens:
            df.update(set(toks))
        n = max(len(self.docs), 1)
        self._idf = {
            term: math.log(1.0 + (n - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def search(self, query: str, *, limit: int = 30) -> list[tuple[str, float]]:
        """Return ``(standard_code, score)`` ranked by BM25 descending."""
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")
        q_terms = tokenize(query)
        if not q_terms or not self.docs:
            return []
        scores: list[tuple[str, float]] = []
        for i, doc in enumerate(self.docs):
            toks = self._tokens[i]
            if not toks:
                continue
            tf = Counter(toks)
            dl = self._doc_len[i]
            score = 0.0
            for term in q_terms:
                if term not in tf:
                    continue
                idf = self._idf.get(term, 0.0)
                freq = tf[term]
                denom = freq + self.k1 * (1.0 - self.b + self.b * dl / self._avgdl)
                score += idf * (freq * (self.k1 + 1.0)) / denom
            if score > 0.0:
                scores.append((doc.standard_code, float(score)))
        scores.sort(key=lambda kv: (-kv[1], kv[0]))
        return scores[:limit]


__all__ = ["StandardsBm25Index", "tokenize"]
