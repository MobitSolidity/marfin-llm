"""
Reranking retrieved passages (master prompt SS.5.2 / SS.8 `rerank`, Phase 3).

WHY NOT A CROSS-ENCODER
-----------------------
The usual answer is a cross-encoder reranker. There isn't one here, and there
cannot be: the budget is a 16 GB CPU box already spending 8.9K tokens on tool
schemas. Claiming a neural reranker would be claiming a capability that does
not exist (SS.0B). This is a FEATURE-BASED reranker and is labelled as such.

WHAT IT ACTUALLY REWARDS
------------------------
BM25 ranks by term statistics alone, which in finance is the wrong objective in
three specific, recurring ways:

  1. AUTHORITY. A blog post and a 10-Q can use identical words. The filing is
     the better evidence even when the blog matches the query better.
  2. RECENCY. Financial facts expire. An eight-year-old filing that matches
     perfectly is usually the wrong document, but NOT always -- so recency is a
     bounded bonus, never a hard cut. That decision belongs to `as_of`.
  3. RESOLVABILITY. A passage whose numbers have a known scale is quotable; one
     whose numbers float free of any units note is a landmine (see ingest.py).

The score is a transparent weighted sum, printed in the trace, because an
opaque reranker in a system that must justify every number is unauditable.

Stdlib only.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple
import datetime

from rag.documents import Passage
from rag.retrieval import RetrievalResult

# Weights. Lexical relevance stays dominant: reranking corrects the ordering,
# it does not overrule the retriever and promote an irrelevant filing just for
# being authoritative.
W_LEXICAL = 1.00
W_AUTHORITY = 0.30
W_RECENCY = 0.20
W_UNITS = 0.10
W_TABLE = 0.05

# A passage older than this contributes no recency bonus (it is not penalised
# below zero -- old filings remain retrievable, they just stop being boosted).
RECENCY_HORIZON_DAYS = 365 * 5


class RerankedHit(object):
    """A passage plus the full breakdown of why it ranks where it does."""

    __slots__ = ("passage", "score", "components", "rank", "prior_rank")

    def __init__(self, passage, score, components, rank, prior_rank):
        self.passage = passage
        self.score = score
        self.components = dict(components)
        self.rank = rank
        self.prior_rank = prior_rank

    def explain(self) -> str:
        parts = ", ".join("%s=%.3f" % (k, v)
                          for k, v in sorted(self.components.items()))
        return "rank %d (was %d) score %.4f [%s]" % (
            self.rank, self.prior_rank, self.score, parts)

    def to_dict(self) -> Dict[str, Any]:
        return {"rank": self.rank, "prior_rank": self.prior_rank,
                "score": self.score, "components": dict(self.components),
                "passage_id": self.passage.passage_id}


def _normalize_scores(scores: Sequence[float]) -> List[float]:
    """
    Scale BM25 scores into [0, 1] by dividing by the maximum.

    NOT min-max. This was min-max first and it was wrong: min-max maps
    [40.0, 39.9] to [1.0, 0.0], turning a 0.25% difference into the largest
    gap the scale can express, and it forces the weakest hit to exactly 0
    whether it was nearly as good or worthless. Under those inflated gaps no
    feature weight can ever break a near-tie, which defeats the entire point
    of reranking.

    Divide-by-max preserves relative magnitude: 40.0 and 39.9 become 1.0 and
    0.9975, so a 0.30 authority weight correctly decides a near-tie, while a
    real gap (9.0 vs 0.4 -> 1.0 vs 0.044) still dominates every other feature.

    BM25 scores are non-negative, so no hit can be pushed below zero.
    """
    if not scores:
        return []
    hi = max(scores)
    if hi <= 1e-12:
        return [1.0] * len(scores)
    return [s / hi for s in scores]


def _recency_bonus(passage: Passage,
                   as_of: Optional[datetime.date]) -> float:
    eff = passage.provenance.effective_date
    if eff is None:
        return 0.0
    ref = as_of or datetime.date.today()
    age = (ref - eff).days
    if age < 0:
        # Filed after the reference date. Retrieval's as_of filter should have
        # excluded it; if it is still here, give it NO bonus rather than a
        # negative age bonus that would rank the future first.
        return 0.0
    if age >= RECENCY_HORIZON_DAYS:
        return 0.0
    return 1.0 - (age / float(RECENCY_HORIZON_DAYS))


def rerank(result: RetrievalResult, top_k: Optional[int] = None,
           as_of: Optional[str] = None) -> List[RerankedHit]:
    """
    Rerank a lexical RetrievalResult.

    An abstention passes straight through as an empty list: reranking nothing
    must never manufacture something.
    """
    # Duck-typing here would be a trap: a bare list has no `.ok`, so removing
    # this check does not make rerank permissive -- it makes it raise
    # AttributeError from somewhere deeper, turning a clear refusal into an
    # incidental crash. Check explicitly and say why.
    if not isinstance(result, RetrievalResult) or not hasattr(result, "ok"):
        raise ValueError(
            "rerank expects a RetrievalResult, got %s. A bare list cannot "
            "express abstention, so an empty retrieval would be "
            "indistinguishable from 'no results worth ranking'."
            % type(result).__name__)
    # Redundant with the loop below (iterating no hits yields no rows), and
    # kept deliberately: it states the abstention contract at the top of the
    # function where a reader looks for it.
    if not result.ok:
        return []

    ref = datetime.date.fromisoformat(as_of) if as_of else None
    lex = _normalize_scores(result.scores) if result.scores else \
        [1.0] * len(result.hits)

    rows: List[Tuple[float, Dict[str, float], Passage, int]] = []
    for i, p in enumerate(result.hits):
        comp = {
            "lexical": W_LEXICAL * lex[i],
            "authority": W_AUTHORITY * (p.provenance.authority / 100.0),
            "recency": W_RECENCY * _recency_bonus(p, ref),
            "units": W_UNITS * (1.0 if p.units_note else 0.0),
            "table": W_TABLE * (1.0 if p.table else 0.0),
        }
        rows.append((sum(comp.values()), comp, p, i))

    # Total order: score, then authority, then passage_id. Never rely on sort
    # stability alone -- a reproducible trace is part of the audit story.
    rows.sort(key=lambda r: (-r[0], -r[2].provenance.authority,
                             r[2].passage_id))
    out = [RerankedHit(p, s, c, rank + 1, prior + 1)
           for rank, (s, c, p, prior) in enumerate(rows)]
    return out[:top_k] if top_k else out
