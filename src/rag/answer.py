"""
The abstention gate (SS.5.2 acceptance: "retrieval failure causes abstention").

WHY A GATE AND NOT A CONVENTION
-------------------------------
Every module below this one can already refuse: retrieval returns `ok=False`,
resolution returns `must_abstain`, verification returns `CONTRADICTED`. None of
that helps if the answer path is free to ignore them. "The retriever returned
nothing, so answer from parametric memory" is one `if` statement away at all
times, and it is invisible when it happens.

So the gate inverts the default. `answer_gate()` returns permission to answer,
and permission has to be earned by evidence that survived retrieval,
resolution AND verification. There is no code path that produces
`may_answer=True` without a citation attached.

WHAT THIS MODULE DOES NOT DO
----------------------------
It does not generate text. No model runs here. It decides whether generation is
permitted and what it is permitted to assert -- so the refusal is auditable
independently of any model's behaviour.

Stdlib only.
"""

from typing import Any, Dict, List, Optional, Sequence, Tuple

from rag.citations import verify_claim
from rag.conflicts import Resolution, resolve_facts, resolve_result
from rag.retrieval import RetrievalResult

# Reasons an answer is withheld. Distinct codes, because "I don't know" and
# "the sources disagree" are different statements to a user.
ABSTAIN_NO_EVIDENCE = "NO_EVIDENCE"
ABSTAIN_LOW_TRUST = "LOW_TRUST"
ABSTAIN_CONFLICT = "CONFLICT"
ABSTAIN_MALFORMED = "MALFORMED_QUESTION"
ABSTAIN_UNVERIFIED = "UNVERIFIED_CLAIM"
ABSTAIN_STALE = "STALE"


class AnswerDecision(object):
    """Permission to answer, or a refusal with a reason a user can act on."""

    __slots__ = ("may_answer", "code", "message", "resolution", "citations",
                 "evidence", "warnings")

    def __init__(self, may_answer, code="", message="", resolution=None,
                 citations=None, evidence=None, warnings=None):
        self.may_answer = may_answer
        self.code = code
        self.message = message
        self.resolution = resolution
        self.citations = list(citations or [])
        self.evidence = list(evidence or [])
        self.warnings = list(warnings or [])

    def to_dict(self) -> Dict[str, Any]:
        return {"may_answer": self.may_answer, "code": self.code,
                "message": self.message, "warnings": list(self.warnings),
                "citations": [c.to_dict() for c in self.citations],
                "resolution": (self.resolution.to_dict()
                               if self.resolution else None)}

    def render(self) -> str:
        if not self.may_answer:
            return "ABSTAIN [%s] %s" % (self.code, self.message)
        lines = ["ANSWER PERMITTED"]
        for c in self.citations:
            lines.append("  " + c.render())
        for w in self.warnings:
            lines.append("  WARNING: " + w)
        return "\n".join(lines)


def answer_gate(retrieval: Any,
                claim: Optional[str] = None,
                min_trust: int = 80,
                as_of: Optional[str] = None,
                allow_stale: bool = False,
                require_single_period: bool = True) -> AnswerDecision:
    """
    Decide whether a numeric claim may be asserted.

    `min_trust` defaults to 80 (EXCHANGE and above). A number quoted from
    permitted news is not a fact about a company's accounts, and defaulting to
    "anything retrievable" would make the trust ladder decorative.

    Order matters: evidence, then resolution, then verification. Verifying a
    claim against a set that mixes periods would "confirm" whichever member
    happens to match.
    """
    # 1. Was there any evidence at all?
    if isinstance(retrieval, RetrievalResult):
        if not retrieval.ok:
            return AnswerDecision(
                False, ABSTAIN_NO_EVIDENCE,
                "retrieval returned no evidence (%s); answering from memory is "
                "not permitted" % (retrieval.reason or "no reason given"))
        res = resolve_result(retrieval, as_of=as_of,
                            require_single_period=require_single_period)
    elif isinstance(retrieval, Resolution):
        res = retrieval
    else:
        facts = list(retrieval or [])
        if not facts:
            return AnswerDecision(
                False, ABSTAIN_NO_EVIDENCE,
                "no evidence supplied; answering from memory is not permitted")
        res = resolve_facts(facts, as_of=as_of,
                            require_single_period=require_single_period)

    # 2. Did resolution succeed?
    if res.status == "EMPTY":
        return AnswerDecision(False, ABSTAIN_NO_EVIDENCE, res.reason,
                              resolution=res)
    if res.status == "REFUSED":
        return AnswerDecision(False, ABSTAIN_MALFORMED, res.reason,
                              resolution=res)
    if res.status == "CONFLICT":
        return AnswerDecision(False, ABSTAIN_CONFLICT, res.reason,
                              resolution=res)

    chosen = res.chosen

    # 3. Is the source authoritative enough to quote?
    if chosen.provenance.authority < min_trust:
        return AnswerDecision(
            False, ABSTAIN_LOW_TRUST,
            "best available source is %s (authority %d), below the required "
            "%d for a quoted figure"
            % (chosen.provenance.trust_level, chosen.provenance.authority,
               min_trust), resolution=res)

    # 4. Stale evidence: refuse unless explicitly allowed.
    stale_warn = [w for w in res.warnings if w.startswith("stale:")]
    if stale_warn and not allow_stale:
        return AnswerDecision(
            False, ABSTAIN_STALE,
            "the newest available figure is stale (%s); pass allow_stale=True "
            "to quote it with the age disclosed" % stale_warn[0][7:],
            resolution=res)

    # 5. If a claim was drafted, it must verify against the chosen evidence.
    citations = []
    if claim is not None:
        cit = verify_claim(claim, chosen)
        citations.append(cit)
        if not cit.ok:
            return AnswerDecision(
                False, ABSTAIN_UNVERIFIED,
                "the drafted claim did not verify against its own evidence "
                "(%s: %s)" % (cit.status, cit.detail),
                resolution=res, citations=citations)

    return AnswerDecision(True, "", "", resolution=res, citations=citations,
                          evidence=[chosen], warnings=list(res.warnings))
