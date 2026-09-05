"""
Claim-level citations and verification (SS.5.2, SS.8 `citation_verify`, Phase 3).

WHAT A CITATION HAS TO DO HERE
------------------------------
Phase 3 acceptance says "citations returned" and "provenance traceable". The
weak reading is a source list at the bottom of an answer. That is exactly the
failure mode this project is built to avoid, because it lets a fabricated
number sit next to three real citations and inherit their credibility.

So a citation binds to a CLAIM, and `verify_claim` answers one question: is the
number in this sentence actually present in the evidence it cites?

THE SCALE TRAP IS THE WHOLE PROBLEM
-----------------------------------
"Revenue was $109,417 million" cites a filing row reading `109,417` under a
header reading `(in millions)`. "Revenue was $109,417" cites the same row and
is wrong by 10^6. Both contain the digits 109,417. A substring check passes
both, which means a naive citation checker certifies the wrong one.

Verification therefore compares NORMALIZED MAGNITUDES, not digit strings:
the claim's stated value times its stated scale, against the evidence's value
times the evidence's scale. Digits matching is not evidence.

Stdlib only.
"""

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import re

from rag.documents import Fact, Passage
from rag.ingest import SCALE_WORDS
from rag.normalize import fold, mask_non_quantities, tokenize

# Floor on relative tolerance, to absorb binary floating-point noise only.
# This is NOT the rounding allowance -- see _tolerance_for().
REL_TOL = 1e-9

# U+060C ARABIC COMMA admitted 2026-08-31 (D-0089b), and U+066C is NOT needed
# here because rag.normalize.fold() already deletes it before this regex runs.
#
# MEASURED before the fix, on the reply recorded for RAG-FA-001:
#     extract_numbers('۳۸۳،۲۸۵ میلیون')
#         -> [ClaimNumber('383' -> 383), ClaimNumber('285' -> 2.85e+08)]
# The claim verifier therefore checked a MANUFACTURED 285,000,000 against the
# evidence instead of the 383,285 million the model actually claimed. For a
# module whose whole purpose is refusing unsupported numbers, inventing one is
# the worst available failure.
#
# This character class is INSIDE the number pattern rather than a strip pass,
# so it can only ever match between digits by construction: the leading `\d` is
# required and the class sits in the repeated tail. Persian sentence
# punctuation cannot be consumed.
_NUM_RE = re.compile(r"[-+]?\d[\d,\u060c]*(?:\.\d+)?")

# Scale words that may follow a number inside a CLAIM ("109.4 billion").
_CLAIM_SCALE_RE = re.compile(
    r"\b(thousand|thousands|million|millions|billion|billions|trillion|"
    r"lakh|crore|\u0647\u0632\u0627\u0631|\u0645\u06cc\u0644\u06cc\u0648\u0646|\u0645\u06cc\u0644\u06cc\u0627\u0631\u062f)\b")

_CLAIM_SCALES = dict(SCALE_WORDS)
_CLAIM_SCALES["trillion"] = 1e12


class ClaimNumber(object):
    """A number extracted from a claim, with whatever scale it declared."""

    __slots__ = ("raw", "value", "scale_word", "scale", "magnitude")

    def __init__(self, raw, value, scale_word, scale):
        self.raw = raw
        self.value = value
        self.scale_word = scale_word
        self.scale = scale
        self.magnitude = value * scale

    def __repr__(self):
        return "ClaimNumber(%r -> %g)" % (self.raw, self.magnitude)


def extract_numbers(text: str) -> List[ClaimNumber]:
    """
    Pull numbers out of a claim, attaching any scale word that follows.

    Percentages are skipped: "grew 12%" is a derived statement, not a magnitude
    that can be matched against a filing row, and treating 12 as a magnitude
    would produce noisy false mismatches.
    """
    out: List[ClaimNumber] = []
    folded = fold(text or "")
    for m in _NUM_RE.finditer(folded):
        raw = m.group(0)
        tail = folded[m.end():m.end() + 24]
        if tail.lstrip().startswith("%") or tail.lstrip().startswith(
                "\u066a"):
            continue
        try:
            # U+060C stripped alongside "," (D-0089b): the pattern now admits
            # it, so failing to strip it here would turn every Persian grouped
            # figure into a ValueError and drop the claim SILENTLY -- trading a
            # wrong number for a missing one.
            value = float(raw.replace(",", "").replace("\u060c", ""))
        except ValueError:
            continue
        sm = _CLAIM_SCALE_RE.match(tail.lstrip())
        scale_word, scale = None, 1.0
        if sm:
            scale_word = sm.group(1)
            scale = _CLAIM_SCALES.get(scale_word, 1.0)
        out.append(ClaimNumber(raw, value, scale_word, scale))
    return out


def _evidence_magnitudes(evidence: Any) -> List[Tuple[float, str]]:
    """
    Every magnitude the evidence can support, with how it was derived.

    A Fact contributes exactly one: value * scale. A Passage contributes each
    number it contains, scaled by its units_note if it has one -- and if it has
    NO units_note, its numbers are returned as UNSCALED with that recorded, so
    the verifier can refuse instead of assuming base units.
    """
    if isinstance(evidence, Fact):
        return [(evidence.normalized_value, "fact")]
    if isinstance(evidence, Passage):
        scale = 1.0
        how = "passage:unscaled"
        if evidence.units_note:
            scale = SCALE_WORDS.get(evidence.units_note, 1.0)
            how = "passage:%s" % evidence.units_note
        mags = []
        for cn in extract_numbers(evidence.text):
            # A number inside the passage may carry its own scale word, which
            # wins over the section note.
            eff = cn.scale if cn.scale_word else scale
            mags.append((cn.value * eff, how))
        return mags
    raise ValueError("evidence must be a Fact or Passage, got %r"
                     % type(evidence).__name__)


def _tolerance_for(cn: "ClaimNumber", rel_floor: float = REL_TOL) -> float:
    """
    Absolute tolerance implied by the claim's OWN stated precision.

    A fixed percentage was wrong in both directions. At 0.5%, a claim of
    "109.5 billion" was accepted as support for 109.417 billion -- a figure the
    filing does not contain and that no rounding of it produces. Tighten the
    percentage and correctly-rounded claims start failing instead.

    The precision is stated by the claim itself. "109.4 billion" is written to
    one decimal of a billion, so it stands for the half-open interval
    [109.35, 109.45) billion: the tolerance is half a unit in its last decimal
    place, scaled. "109,417 million" is written to whole millions, so it admits
    half a million. This accepts every correctly-rounded restatement of the
    evidence and rejects everything else, with no tuned constant.
    """
    digits = cn.raw.split(".")
    decimals = len(digits[1]) if len(digits) > 1 else 0
    half_ulp = 0.5 * (10.0 ** -decimals) * cn.scale
    return max(half_ulp, abs(cn.magnitude) * rel_floor)


class Citation(object):
    """A claim bound to the evidence that supports it."""

    __slots__ = ("claim", "evidence", "status", "detail", "matched")

    def __init__(self, claim, evidence, status, detail, matched=None):
        self.claim = claim
        self.evidence = evidence
        self.status = status          # SUPPORTED / CONTRADICTED / UNSUPPORTED
        self.detail = detail
        self.matched = matched

    @property
    def ok(self) -> bool:
        return self.status == "SUPPORTED"

    def render(self) -> str:
        prov = getattr(self.evidence, "provenance", None)
        return "%s [%s] %s" % (self.claim, self.status,
                               prov.citation() if prov else "no provenance")

    def to_dict(self) -> Dict[str, Any]:
        prov = getattr(self.evidence, "provenance", None)
        return {"claim": self.claim, "status": self.status,
                "detail": self.detail, "matched": self.matched,
                "citation": prov.citation() if prov else None,
                "provenance": prov.to_dict() if prov else None}


def verify_claim(claim: str, evidence: Any,
                 rel_tol: float = REL_TOL) -> Citation:
    """
    Check that every magnitude asserted in `claim` appears in `evidence`.

    Statuses:
      SUPPORTED     - every claimed magnitude matches within tolerance
      CONTRADICTED  - a claimed magnitude is absent, or present at a different
                      scale (the 10^6 error)
      UNSUPPORTED   - the claim asserts no checkable magnitude, or the evidence
                      cannot be scaled, so nothing was actually verified

    UNSUPPORTED is deliberately NOT a pass. A claim that cannot be checked must
    not be reported as checked.
    """
    if evidence is None:
        return Citation(claim, None, "UNSUPPORTED",
                        "no evidence supplied; a claim with no evidence is "
                        "not a citation")

    prov = getattr(evidence, "provenance", None)
    if prov is None:
        return Citation(claim, evidence, "UNSUPPORTED",
                        "evidence carries no provenance and cannot be cited")

    # MASK THE NON-QUANTITIES IN THE CLAIM BEFORE EXTRACTING ANY NUMBER.
    #
    # DEFECT MEASURED 2026-09-05 on the user's real 52-case run (D-0092). This
    # module did no masking at all -- `grep mask_years src/rag/citations.py`
    # returned nothing -- so 8 of 12 graded claims were checked against a
    # citation marker or a year:
    #
    #   RAG-EN-001 claimed "2"    -- the marker [2]
    #   RAG-FA-001 claimed "2023" -- the year ۲۰۲۳
    #   RAG-ABST-003 claimed "1402" -- the year ۱۴۰۲
    #
    # and because verify_claim RETURNS ON THE FIRST unlocatable number, and a
    # marker or a year is almost always the first number in a cited sentence,
    # one artefact decided the whole case. The reported detail was
    # "claimed 2 does not appear in the evidence; nearest is 1.69148e+11
    # (ratio 1.1824e-11 -- a power-of-ten ratio means a scale error)", against
    # answers that were CORRECT.
    #
    # WHY HERE AND NOT INSIDE extract_numbers: extract_numbers also serves the
    # EVIDENCE side, via _evidence_magnitudes. Evidence legitimately contains
    # figures that look like years -- a CPI index, a share count, a rial price
    # -- and masking those would delete a magnitude the model is entitled to
    # cite, turning a SUPPORTED claim into a CONTRADICTED one. The claim side
    # is the only side where a year is certainly not an amount being asserted.
    #
    # scripts/phase4_lib.split_claims already masks before it splits, so for
    # the Phase-4 RAG arm this is a second, idempotent application. It is kept
    # because src/rag/answer.py calls verify_claim DIRECTLY, with no splitter
    # in front of it, and that path had no masking whatsoever.
    claimed = extract_numbers(mask_non_quantities(claim))
    if not claimed:
        return Citation(claim, evidence, "UNSUPPORTED",
                        "claim asserts no numeric magnitude to verify")

    available = _evidence_magnitudes(evidence)
    if not available:
        return Citation(claim, evidence, "UNSUPPORTED",
                        "evidence contains no numeric magnitude")

    unscaled = any(how == "passage:unscaled" for _, how in available)
    matched: List[Dict[str, Any]] = []
    for cn in claimed:
        tol = _tolerance_for(cn, rel_tol)

        # UNSCALED EVIDENCE CANNOT SUPPORT A MAGNITUDE AT ALL.
        # This branch used to run after the match loop, so a bare "109,417"
        # claim MATCHED an unscaled passage containing "109,417" and was
        # returned SUPPORTED -- silently assuming the filing meant base units,
        # the exact 10^6 error this module exists to catch. The asymmetry was
        # the tell: the scaled reading was refused while the bare one passed.
        # Neither reading is verifiable without a declared scale, so refuse
        # before comparing.
        if unscaled and not cn.scale_word:
            near = min(available, key=lambda p: abs(p[0] - cn.magnitude))[0]
            return Citation(
                claim, evidence, "UNSUPPORTED",
                "the evidence declares no scale, so a bare magnitude cannot "
                "be confirmed: %g may be units, thousands or millions "
                "(nearest value in evidence %g)" % (cn.magnitude, near))

        hit = None
        for mag, how in available:
            if abs(mag - cn.magnitude) <= tol:
                hit = (mag, how)
                break
        if hit is None:
            near = min(available,
                       key=lambda p: abs(p[0] - cn.magnitude))[0]
            if unscaled:
                return Citation(
                    claim, evidence, "UNSUPPORTED",
                    "claimed %g is not in the evidence, and the evidence "
                    "declares no scale, so it cannot be confirmed or ruled "
                    "out (nearest value %g)" % (cn.magnitude, near))
            ratio = (cn.magnitude / near) if near else float("inf")
            return Citation(
                claim, evidence, "CONTRADICTED",
                "claimed %g does not appear in the evidence; nearest is %g "
                "(ratio %.6g -- a power-of-ten ratio means a scale error)"
                % (cn.magnitude, near, ratio))
        matched.append({"claim_value": cn.raw, "scale_word": cn.scale_word,
                        "magnitude": cn.magnitude, "evidence": hit[0],
                        "derived_from": hit[1], "tolerance": tol})

    return Citation(claim, evidence, "SUPPORTED",
                    "all %d claimed magnitude(s) matched within the precision "
                    "the claim itself states" % len(matched), matched=matched)


def verify_answer(claims: Sequence[Tuple[str, Any]],
                  rel_tol: float = REL_TOL) -> Dict[str, Any]:
    """
    Verify a whole answer, claim by claim.

    `ok` is true only if EVERY claim is SUPPORTED. One unverifiable sentence
    invalidates the answer rather than being diluted by the ones that passed --
    that dilution is precisely how a fabricated figure gets shipped.
    """
    results = [verify_claim(c, e, rel_tol) for c, e in claims]
    bad = [r for r in results if not r.ok]
    return {"ok": not bad, "n_claims": len(results),
            "n_failed": len(bad),
            "citations": [r.to_dict() for r in results],
            "must_abstain": bool(bad),
            "reason": "" if not bad else
                      "%d of %d claims could not be verified: %s"
                      % (len(bad), len(results),
                         "; ".join(r.detail[:60] for r in bad[:3]))}
