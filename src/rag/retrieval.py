"""
Hybrid retrieval over financial documents (master prompt SS.5.2, Phase 3).

WHAT "HYBRID" HONESTLY MEANS HERE
---------------------------------
It does NOT mean dense vectors + sparse keywords. There is no embedding model
on this machine (16 GB CPU box, stdlib-only calc engine), so claiming a vector
index would be claiming a capability that does not exist -- SS.0B.

It means two genuinely different retrieval modes over two different stores:

  1. LEXICAL (BM25) over Passages -- narrative text, accounting policy, risk
     factors, MD&A. Answers "what did they SAY".
  2. STRUCTURED over Facts -- exact concept/period/entity lookup with no
     scoring at all. Answers "what was the NUMBER".

They are separated because a number must never be retrieved by text similarity.
"Revenue was strong" scores well against a revenue query and contains no
revenue. Facts are matched on identity, not likeness.

FILTERS ARE HARD, NOT SOFT
--------------------------
Entity, period and period_kind are applied as filters, never as score
contributions. A 12-month figure that ranks highly for a quarterly question is
not a good answer with a small penalty -- it is the WRONG NUMBER. MEASURED:
one Apple revenue tag carries 3/6/9/12-month facts side by side, so soft
ranking would surface a mixed-period set routinely.

ABSTENTION
----------
Phase 3 acceptance requires that retrieval failure causes abstention. Every
entry point returns a result object with `.ok` and `.reason`; empty is a
first-class outcome, not an empty list the caller may quietly ignore.

Stdlib only.
"""

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import datetime
import math

from rag.documents import Fact, Passage, TRUST_LEVELS
from rag.normalize import index_terms, tokenize

# BM25 parameters. Standard defaults; k1 controls term-frequency saturation,
# b controls length normalization.
BM25_K1 = 1.5
BM25_B = 0.75


class RetrievalResult(object):
    """
    Outcome of a retrieval call.

    `ok=False` is a normal, expected outcome. The answer layer MUST treat it as
    a refusal to answer rather than as "no supporting evidence, answer anyway".
    """

    __slots__ = ("hits", "scores", "reason", "query", "filters", "mode")

    def __init__(self, hits, scores=None, reason="", query="", filters=None,
                 mode=""):
        self.hits = list(hits)
        self.scores = list(scores or [])
        self.reason = reason
        self.query = query
        self.filters = dict(filters or {})
        self.mode = mode

    @property
    def ok(self) -> bool:
        return bool(self.hits)

    def __len__(self) -> int:
        return len(self.hits)

    def __iter__(self):
        return iter(self.hits)

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "mode": self.mode, "n": len(self.hits),
                "reason": self.reason, "query": self.query,
                "filters": self.filters, "scores": self.scores}


# ---------------------------------------------------------------------------
# Lexical index over passages.
# ---------------------------------------------------------------------------

class PassageIndex(object):
    """
    BM25 over Passage text, with hard metadata filters.

    The index stores `index_terms()` output -- the SAME function the query path
    calls. That symmetry is deliberate: the Q9 selector shipped a bug where one
    side normalized and the other did not, and the failure was a silent miss.
    """

    def __init__(self):
        self.passages: List[Passage] = []
        self._terms: List[List[str]] = []
        self._tf: List[Dict[str, int]] = []
        self._df: Dict[str, int] = {}
        self._len: List[int] = []
        self._avglen: float = 0.0

    def add(self, passage: Passage) -> None:
        if not isinstance(passage, Passage):
            raise ValueError("PassageIndex holds Passage objects; a bare "
                             "string has no provenance and may not be indexed")
        terms = index_terms(passage.text)
        tf: Dict[str, int] = {}
        for t in terms:
            tf[t] = tf.get(t, 0) + 1
        self.passages.append(passage)
        self._terms.append(terms)
        self._tf.append(tf)
        # Length uses BASE tokens, not compound variants: see normalize.py.
        self._len.append(max(1, len(tokenize(passage.text))))
        for t in set(terms):
            self._df[t] = self._df.get(t, 0) + 1
        self._avglen = sum(self._len) / float(len(self._len))

    def add_all(self, passages: Iterable[Passage]) -> None:
        for p in passages:
            self.add(p)

    def __len__(self) -> int:
        return len(self.passages)

    def _idf(self, term: str) -> float:
        n = len(self.passages)
        df = self._df.get(term, 0)
        if df == 0:
            return 0.0
        # Robertson/Sparck-Jones idf, floored at 0 so a term appearing in every
        # document contributes nothing rather than a negative score.
        return max(0.0, math.log(1.0 + (n - df + 0.5) / (df + 0.5)))

    def search(self, query: str, top_k: int = 10,
               entity: Optional[str] = None,
               lang: Optional[str] = None,
               as_of: Optional[str] = None,
               require_units: bool = False,
               min_trust: int = 0) -> RetrievalResult:
        """
        Rank passages for a query.

        Filters are hard. `as_of` excludes documents filed AFTER that date,
        which is what makes backtesting honest: a model must not read a filing
        that did not exist yet.
        """
        filters = {"entity": entity, "lang": lang, "as_of": as_of,
                   "require_units": require_units, "min_trust": min_trust}

        if not self.passages:
            return RetrievalResult([], reason="index is empty", query=query,
                                   filters=filters, mode="lexical")

        q_terms = index_terms(query)
        if not q_terms:
            return RetrievalResult([], reason="query has no searchable terms",
                                   query=query, filters=filters,
                                   mode="lexical")

        cutoff = None
        if as_of:
            cutoff = datetime.date.fromisoformat(as_of)

        scored: List[Tuple[float, int]] = []
        n_filtered = 0
        for i, p in enumerate(self.passages):
            if entity and (p.entity or "").lower() != entity.lower():
                n_filtered += 1
                continue
            if lang and p.lang != lang:
                n_filtered += 1
                continue
            if min_trust and p.provenance.authority < min_trust:
                n_filtered += 1
                continue
            if require_units and not p.units_note:
                n_filtered += 1
                continue
            if cutoff is not None:
                eff = p.provenance.effective_date
                if eff is None or eff > cutoff:
                    n_filtered += 1
                    continue

            tf = self._tf[i]
            dl = self._len[i]
            score = 0.0
            for t in q_terms:
                f = tf.get(t, 0)
                if not f:
                    continue
                denom = f + BM25_K1 * (1 - BM25_B + BM25_B * dl / self._avglen)
                score += self._idf(t) * (f * (BM25_K1 + 1)) / denom
            if score > 0:
                scored.append((score, i))

        if not scored:
            reason = ("no passage matched the query terms"
                      if n_filtered < len(self.passages)
                      else "every passage was excluded by filters")
            return RetrievalResult([], reason=reason, query=query,
                                   filters=filters, mode="lexical")

        # Sort by score, then by authority, then by recency, then by id so the
        # order is total and reproducible run to run.
        scored.sort(key=lambda s: (
            -s[0],
            -self.passages[s[1]].provenance.authority,
            -(self.passages[s[1]].provenance.effective_date
              or datetime.date.min).toordinal(),
            self.passages[s[1]].passage_id,
        ))
        top = scored[:top_k]
        return RetrievalResult([self.passages[i] for _, i in top],
                               scores=[s for s, _ in top],
                               query=query, filters=filters, mode="lexical")


# ---------------------------------------------------------------------------
# Structured index over facts.
# ---------------------------------------------------------------------------

class FactStore(object):
    """
    Exact lookup over Facts. No text scoring, ever.

    A number is retrieved by matching concept + entity + period, or it is not
    retrieved. There is no "close enough" for a figure that will be quoted.
    """

    def __init__(self):
        self.facts: List[Fact] = []
        self._by_concept: Dict[str, List[int]] = {}

    def add(self, fact: Fact) -> None:
        if not isinstance(fact, Fact):
            raise ValueError("FactStore holds Fact objects")
        self._by_concept.setdefault(fact.concept.lower(), []).append(
            len(self.facts))
        self.facts.append(fact)

    def add_all(self, facts: Iterable[Fact]) -> None:
        for f in facts:
            self.add(f)

    def __len__(self) -> int:
        return len(self.facts)

    def concepts(self) -> List[str]:
        return sorted(self._by_concept)

    def query(self, concept: str,
              entity: Optional[str] = None,
              period_kind: Optional[str] = None,
              period_end: Optional[str] = None,
              fiscal_year: Optional[int] = None,
              as_of: Optional[str] = None,
              currency: Optional[str] = None) -> RetrievalResult:
        """
        Retrieve facts by identity.

        `period_kind` is the guard that keeps a 3-month figure out of an annual
        answer. It is NOT defaulted: omitting it returns every duration, which
        the conflict layer will then report as a mixed-period set rather than
        silently picking one.
        """
        filters = {"concept": concept, "entity": entity,
                   "period_kind": period_kind, "period_end": period_end,
                   "fiscal_year": fiscal_year, "as_of": as_of,
                   "currency": currency}
        idxs = self._by_concept.get((concept or "").lower())
        if not idxs:
            return RetrievalResult(
                [], reason="concept %r is not in the fact store" % concept,
                query=concept, filters=filters, mode="structured")

        cutoff = datetime.date.fromisoformat(as_of) if as_of else None
        want_end = (datetime.date.fromisoformat(period_end)
                    if period_end else None)

        hits: List[Fact] = []
        for i in idxs:
            f = self.facts[i]
            if entity and (f.entity or "").lower() != entity.lower() and \
                    (f.entity_id or "") != entity:
                continue
            if period_kind and f.period_kind != period_kind:
                continue
            if want_end and f.period_end != want_end:
                continue
            if fiscal_year and f.fiscal_year != fiscal_year:
                continue
            if currency and f.currency != currency:
                continue
            if cutoff is not None:
                eff = f.provenance.effective_date
                if eff is None or eff > cutoff:
                    continue
            hits.append(f)

        if not hits:
            return RetrievalResult(
                [], reason="no fact matched concept %r under the given "
                           "filters" % concept,
                query=concept, filters=filters, mode="structured")

        # Newest filing first: the conflict layer relies on this ordering to
        # identify the current figure and the ones it supersedes.
        hits.sort(key=lambda f: (
            -( f.provenance.effective_date or datetime.date.min).toordinal(),
            -(f.period_end or datetime.date.min).toordinal(),
        ))
        return RetrievalResult(hits, query=concept, filters=filters,
                               mode="structured")


# ---------------------------------------------------------------------------
# Hybrid entry point.
# ---------------------------------------------------------------------------

class HybridRetriever(object):
    """Runs both modes and reports which one produced what."""

    def __init__(self, passage_index=None, fact_store=None):
        self.passages = passage_index or PassageIndex()
        self.facts = fact_store or FactStore()

    def retrieve(self, query: str, concept: Optional[str] = None,
                 top_k: int = 5, **filters) -> Dict[str, RetrievalResult]:
        lex_kwargs = {k: v for k, v in filters.items()
                      if k in ("entity", "lang", "as_of", "require_units",
                               "min_trust")}
        fact_kwargs = {k: v for k, v in filters.items()
                       if k in ("entity", "period_kind", "period_end",
                                "fiscal_year", "as_of", "currency")}
        out = {"lexical": self.passages.search(query, top_k=top_k,
                                               **lex_kwargs)}
        if concept:
            out["structured"] = self.facts.query(concept, **fact_kwargs)
        else:
            out["structured"] = RetrievalResult(
                [], reason="no concept supplied; structured lookup skipped",
                query=query, mode="structured")
        return out
