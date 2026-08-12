"""
Staleness and conflict detection (SS.5.2, Phase 3).

THE HAZARD, MEASURED
--------------------
In ONE Apple revenue tag pulled live from EDGAR: 117 facts, and 46 distinct
periods reported by more than one filing. Later filings restate earlier ones.
So "Apple's Q3 revenue" has several answers on record, all from primary
sources, all citable, and the superseded one looks exactly as credible as the
current one.

A retriever that returns the first match, or the highest-scoring match, will
sometimes cite a number the company itself no longer stands behind -- with a
real accession number attached.

THREE DISTINCT FAILURE MODES, KEPT DISTINCT
-------------------------------------------
  1. RESTATEMENT: same concept, same entity, same period, DIFFERENT value from
     different filings. Resolve toward the newest filing and SAY that earlier
     figures were superseded.
  2. PERIOD MIXING: same concept and entity, DIFFERENT period lengths. This is
     not a conflict to resolve -- it is a malformed question. Refuse.
  3. STALENESS: the newest available figure is old. Not an error; a disclosure.
     Whether 400 days is too old depends on the question, so this module
     reports the age and the caller decides.

Resolution is never silent. Every output carries what was chosen, what was
rejected, and why.

Stdlib only.
"""

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import datetime

from rag.documents import Fact

# Default staleness thresholds by period kind, in days past period end.
# A quarterly figure more than ~135 days old means a newer quarter has almost
# certainly been filed; an annual figure has a longer natural shelf life.
STALENESS_DAYS = {
    "quarter": 135,
    "half": 225,
    "nine_month": 315,
    "annual": 400,
    "instant": 135,
    "ytd": 225,
    "trailing_twelve": 400,
    "unknown": 135,
}


class Resolution(object):
    """The outcome of reconciling a set of facts."""

    __slots__ = ("status", "chosen", "superseded", "rejected", "reason",
                 "warnings")

    def __init__(self, status, chosen=None, superseded=None, rejected=None,
                 reason="", warnings=None):
        self.status = status          # RESOLVED / CONFLICT / REFUSED / EMPTY
        self.chosen = chosen
        self.superseded = list(superseded or [])
        self.rejected = list(rejected or [])
        self.reason = reason
        self.warnings = list(warnings or [])

    @property
    def ok(self) -> bool:
        return self.status == "RESOLVED"

    @property
    def must_abstain(self) -> bool:
        return self.status in ("REFUSED", "EMPTY", "CONFLICT")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "ok": self.ok,
            "must_abstain": self.must_abstain,
            "reason": self.reason,
            "warnings": list(self.warnings),
            "chosen": self.chosen.to_dict() if self.chosen else None,
            "n_superseded": len(self.superseded),
            "superseded": [{"value": f.normalized_value,
                            "filed": f.provenance.filed.isoformat()
                            if f.provenance.filed else None,
                            "accession": f.provenance.accession}
                           for f in self.superseded],
        }

    def explain(self) -> str:
        if not self.chosen:
            return "%s: %s" % (self.status, self.reason)
        bits = ["%s: %g (%s)" % (self.status, self.chosen.normalized_value,
                                 self.chosen.provenance.citation())]
        if self.superseded:
            bits.append("supersedes %d earlier figure(s): %s"
                        % (len(self.superseded),
                           ", ".join("%g from %s" % (
                               f.normalized_value,
                               f.provenance.accession or "unknown")
                               for f in self.superseded)))
        for w in self.warnings:
            bits.append("WARNING: %s" % w)
        return " | ".join(bits)


def _values_differ(a: Fact, b: Fact, rel_tol: float = 1e-9) -> bool:
    x, y = a.normalized_value, b.normalized_value
    denom = max(abs(x), abs(y), 1e-12)
    return abs(x - y) / denom > rel_tol


def detect_period_mixing(facts: Sequence[Fact]) -> List[str]:
    """Period kinds present in a fact set, sorted. More than one is a problem."""
    return sorted({f.period_kind for f in facts})


def staleness(fact: Fact, as_of: Optional[str] = None,
              thresholds: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """
    Age of a fact relative to `as_of`, and whether that exceeds the threshold.

    Measured from PERIOD END, not filing date: a filing published yesterday
    about a period that ended two years ago is stale data, however fresh the
    document is.
    """
    limits = thresholds or STALENESS_DAYS
    ref = (datetime.date.fromisoformat(as_of) if as_of
           else datetime.date.today())
    end = fact.period_end
    if end is None:
        return {"age_days": None, "stale": True, "as_of": ref.isoformat(),
                "reason": "fact has no period end; age cannot be established, "
                          "so it is treated as stale rather than assumed fresh"}
    age = (ref - end).days
    limit = limits.get(fact.period_kind, limits.get("unknown", 135))
    return {"age_days": age, "stale": age > limit, "limit_days": limit,
            "as_of": ref.isoformat(), "period_end": end.isoformat(),
            "reason": ("%d days past period end exceeds the %d-day limit for a "
                       "%s figure" % (age, limit, fact.period_kind))
                      if age > limit else ""}


def resolve_facts(facts: Sequence[Fact], as_of: Optional[str] = None,
                  require_single_period: bool = True,
                  thresholds: Optional[Dict[str, int]] = None) -> Resolution:
    """
    Reconcile a set of facts into ONE citable figure, or refuse.

    Refuses rather than guesses when:
      - the set is empty
      - it mixes period kinds (a malformed question, not a conflict)
      - two filings of equal authority and equal date disagree on the value
        (nothing in the data can break that tie, so the caller must)
    """
    if not facts:
        return Resolution("EMPTY", reason="no facts to resolve; retrieval "
                                          "returned nothing to cite")

    kinds = detect_period_mixing(facts)
    if require_single_period and len(kinds) > 1:
        return Resolution(
            "REFUSED", rejected=list(facts),
            reason="fact set mixes %d period kinds (%s). MEASURED: a single "
                   "EDGAR revenue tag carries 3/6/9/12-month facts side by "
                   "side, so these are not alternative answers to one "
                   "question -- they answer different questions. Narrow the "
                   "period before asking." % (len(kinds), ", ".join(kinds)))

    # Group by what actually has to agree: concept, entity, period, unit.
    groups: Dict[tuple, List[Fact]] = {}
    for f in facts:
        groups.setdefault(f.comparable_key(), []).append(f)
    if len(groups) > 1:
        return Resolution(
            "REFUSED", rejected=list(facts),
            reason="fact set spans %d distinct (concept, entity, period, unit) "
                   "groups; refusing to collapse different quantities into one "
                   "answer" % len(groups))

    group = list(facts)
    # Highest authority first, then newest filing.
    group.sort(key=lambda f: (
        -f.provenance.authority,
        -(f.provenance.effective_date or datetime.date.min).toordinal(),
    ))
    chosen = group[0]

    # Anything that disagrees with the chosen value.
    disagreeing = [f for f in group[1:] if _values_differ(chosen, f)]

    # An unbreakable tie: same authority, same date, different value.
    for f in disagreeing:
        same_auth = f.provenance.authority == chosen.provenance.authority
        same_date = (f.provenance.effective_date
                     == chosen.provenance.effective_date)
        if same_auth and same_date:
            return Resolution(
                "CONFLICT", rejected=list(group),
                reason="two sources of equal authority (%s) and equal date "
                       "report different values (%g vs %g). Nothing in the "
                       "data breaks this tie, so it is reported rather than "
                       "resolved."
                       % (chosen.provenance.trust_level,
                          chosen.normalized_value, f.normalized_value))

    warnings: List[str] = []
    st = staleness(chosen, as_of=as_of, thresholds=thresholds)
    if st["stale"]:
        warnings.append("stale: %s" % st["reason"])
    if disagreeing:
        warnings.append(
            "restated: %d earlier filing(s) reported a different value; the "
            "newest filing is cited and the earlier ones are listed"
            % len(disagreeing))

    return Resolution("RESOLVED", chosen=chosen, superseded=disagreeing,
                      reason="chose the highest-authority, newest filing",
                      warnings=warnings)


def resolve_result(result: Any, **kwargs) -> Resolution:
    """Resolve a structured RetrievalResult, preserving its abstention."""
    hits = getattr(result, "hits", None)
    if hits is None:
        raise ValueError("resolve_result expects a RetrievalResult")
    if not getattr(result, "ok", False):
        return Resolution("EMPTY",
                          reason=getattr(result, "reason", "") or
                          "retrieval returned nothing")
    return resolve_facts(hits, **kwargs)
