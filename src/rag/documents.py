"""
Financial document model (master prompt SS.5.2, Phase 3).

WHY THIS IS NOT A PLAIN TEXT CHUNK
----------------------------------
General-purpose RAG stores text and an embedding. That is unsafe for finance,
because the number is meaningless without the things a text chunk throws away:

  - PERIOD. Apple's `RevenueFromContractWithCustomer` tag holds 3-month,
    6-month, 9-month and 12-month facts side by side. MEASURED on live EDGAR
    data: 64 / 16 / 16 / 21 facts respectively in a single tag. Retrieving
    "Apple revenue" without a period filter can return a quarter and an
    annual figure as if they were comparable.
  - SCALE. Filings state "in thousands" or "in millions" in a table header that
    a chunker happily separates from the row. EDGAR's XBRL API returns raw
    units instead (109417000000, not 109417), so the SAME concept arrives at
    different scales depending on the path it took.
  - CURRENCY. A USD figure and an IRR figure are both "revenue".
  - VINTAGE. MEASURED: 46 periods in that one tag are reported by more than one
    filing, because later filings restate earlier ones. Citing the superseded
    number is a correctness failure that looks perfectly plausible.
  - PROVENANCE. SS.5.2 requires claim-level citation. A claim that cannot name
    its accession number, filing date and source URL cannot be checked.

So the unit of storage here is a FACT or a PASSAGE that carries its own
metadata, and the retrieval layer is allowed to refuse rather than guess when
that metadata is missing or contradictory.

Stdlib only, consistent with the calc engine: this must run on a Windows CPU
box with no compiler toolchain.
"""

from typing import Any, Dict, List, Optional, Sequence
import datetime
import hashlib
import re

# ---------------------------------------------------------------------------
# Trust levels (SS.5.2 "source authority").
# Ordered: a conflict between two sources is resolved toward higher authority,
# and the resolution is always reported, never silent.
# ---------------------------------------------------------------------------

TRUST_LEVELS = {
    "VERIFIED_PRIMARY": 100,   # audited filing / regulator / official issuer
    "OFFICIAL_DATA": 90,       # official statistical agency (FRED, central bank)
    "EXCHANGE": 80,            # exchange documentation
    "PERMITTED_RESEARCH": 50,
    "PERMITTED_NEWS": 30,
    "UNVERIFIED": 0,           # never citable as fact
}

# Period kinds. Mixing these is the single most common financial RAG error.
PERIOD_KINDS = ("instant", "quarter", "half", "nine_month", "annual",
                "ytd", "trailing_twelve", "unknown")

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_date(value: Optional[str], field: str) -> Optional[datetime.date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime.date):
        return value
    if not isinstance(value, str) or not _ISO.match(value):
        raise ValueError(
            "%s must be an ISO date (YYYY-MM-DD), got %r. Refusing to guess a "
            "date format: an ambiguous date silently mis-periods every fact "
            "derived from it." % (field, value))
    return datetime.date.fromisoformat(value)


def classify_period(start: Optional[str], end: Optional[str]) -> str:
    """
    Derive the period kind from its span.

    Uses day-count bands rather than exact month arithmetic because fiscal
    quarters are 13-week periods that drift against calendar months (Apple's
    Q3 2026 runs 2026-03-29 to 2026-06-27 = 90 days).
    """
    s = _parse_date(start, "start")
    e = _parse_date(end, "end")
    if e is None:
        return "unknown"
    if s is None or s == e:
        return "instant"
    days = (e - s).days
    if days < 0:
        raise ValueError("period end %s precedes start %s" % (end, start))
    if days <= 100:
        return "quarter"
    if days <= 190:
        return "half"
    if days <= 285:
        return "nine_month"
    if days <= 380:
        return "annual"
    return "unknown"


class Provenance(object):
    """
    Where a fact came from and whether it is still current.

    `retrieved_at` is separate from `filed` and `published`: staleness is
    measured against the real world, not against when we happened to fetch.
    """

    __slots__ = ("source", "source_id", "url", "trust_level", "filed",
                 "published", "retrieved_at", "accession", "licence", "note")

    def __init__(self, source, url=None, trust_level="UNVERIFIED",
                 filed=None, published=None, retrieved_at=None,
                 accession=None, licence=None, source_id=None, note=""):
        if not source:
            raise ValueError("provenance requires a source; an uncited fact "
                             "may not enter the index (SS.5.2)")
        if trust_level not in TRUST_LEVELS:
            raise ValueError("unknown trust_level %r; allowed: %s"
                             % (trust_level, sorted(TRUST_LEVELS)))
        self.source = source
        self.source_id = source_id
        self.url = url
        self.trust_level = trust_level
        self.filed = _parse_date(filed, "filed")
        self.published = _parse_date(published, "published")
        self.retrieved_at = _parse_date(retrieved_at, "retrieved_at")
        self.accession = accession
        self.licence = licence
        self.note = note

    @property
    def authority(self) -> int:
        return TRUST_LEVELS[self.trust_level]

    @property
    def effective_date(self) -> Optional[datetime.date]:
        """The date that matters for staleness: when the world learned this."""
        return self.filed or self.published

    def citation(self) -> str:
        """A human-checkable citation string."""
        bits = [self.source]
        if self.accession:
            bits.append(self.accession)
        d = self.effective_date
        if d:
            bits.append(d.isoformat())
        if self.url:
            bits.append(self.url)
        return " | ".join(bits)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "source_id": self.source_id,
            "url": self.url,
            "trust_level": self.trust_level,
            "authority": self.authority,
            "filed": self.filed.isoformat() if self.filed else None,
            "published": self.published.isoformat() if self.published else None,
            "retrieved_at": (self.retrieved_at.isoformat()
                             if self.retrieved_at else None),
            "accession": self.accession,
            "licence": self.licence,
            "citation": self.citation(),
            "note": self.note,
        }


class Fact(object):
    """
    One numeric observation, with everything needed to use it safely.

    A Fact is deliberately NOT free text. It is the structured half of the
    "separate documents from time series" requirement: numbers live here where
    units, scale and period are enforced, and prose lives in Passage.
    """

    __slots__ = ("concept", "value", "unit", "scale", "currency", "period_kind",
                 "period_start", "period_end", "entity", "entity_id",
                 "fiscal_year", "fiscal_period", "form", "provenance",
                 "dimensions", "label")

    def __init__(self, concept, value, unit, provenance,
                 period_start=None, period_end=None, entity=None,
                 entity_id=None, scale=1, currency=None, fiscal_year=None,
                 fiscal_period=None, form=None, dimensions=None,
                 period_kind=None, label="VERIFIED"):
        if not concept:
            raise ValueError("fact requires a concept name")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("fact value must be numeric, got %r" % (value,))
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("fact value must be finite, got %r" % (value,))
        if not unit:
            raise ValueError(
                "fact requires a unit. A bare number is exactly the failure "
                "mode this model exists to prevent (SS.5.2).")
        if not isinstance(provenance, Provenance):
            raise ValueError("fact requires a Provenance object")
        if scale in (0, None):
            raise ValueError("scale must be a non-zero multiplier")

        self.concept = concept
        self.value = float(value)
        self.unit = unit
        self.scale = float(scale)
        self.currency = currency
        self.period_start = _parse_date(period_start, "period_start")
        self.period_end = _parse_date(period_end, "period_end")
        self.period_kind = period_kind or classify_period(period_start,
                                                          period_end)
        if self.period_kind not in PERIOD_KINDS:
            raise ValueError("unknown period_kind %r" % (self.period_kind,))
        self.entity = entity
        self.entity_id = entity_id
        self.fiscal_year = fiscal_year
        self.fiscal_period = fiscal_period
        self.form = form
        self.provenance = provenance
        self.dimensions = dict(dimensions or {})
        self.label = label

    @property
    def normalized_value(self) -> float:
        """
        Value in base units.

        Scale is applied HERE and nowhere else. EDGAR's XBRL API reports raw
        units (109417000000) while a filing table may report the same concept
        "in millions" (109417). Storing scale and normalising in one place is
        what stops those two ever being compared directly.
        """
        return self.value * self.scale

    def comparable_key(self) -> tuple:
        """
        Two facts may only be compared if this key matches.

        Period kind is part of the key: a 3-month and a 12-month revenue are
        different quantities, not different values of one quantity.
        """
        return (self.concept, self.entity_id or self.entity, self.unit,
                self.currency, self.period_kind, self.period_start,
                self.period_end, tuple(sorted(self.dimensions.items())))

    def is_comparable_to(self, other: "Fact") -> bool:
        return self.comparable_key() == other.comparable_key()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "concept": self.concept,
            "label_text": self.label,
            "value": self.value,
            "normalized_value": self.normalized_value,
            "unit": self.unit,
            "scale": self.scale,
            "currency": self.currency,
            "period_kind": self.period_kind,
            "period_start": (self.period_start.isoformat()
                             if self.period_start else None),
            "period_end": (self.period_end.isoformat()
                           if self.period_end else None),
            "entity": self.entity,
            "entity_id": self.entity_id,
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "form": self.form,
            "dimensions": dict(self.dimensions),
            "provenance": self.provenance.to_dict(),
        }


class Passage(object):
    """
    A chunk of prose that keeps its position in the document hierarchy.

    Hierarchy is retained (SS.5.2 "document hierarchy") because "Item 1A. Risk
    Factors" and "Item 7. MD&A" carry very different weight, and because a
    citation that cannot name its section is not checkable.
    """

    __slots__ = ("text", "provenance", "section_path", "entity", "entity_id",
                 "period_start", "period_end", "lang", "table", "doc_id",
                 "chunk_index", "units_note")

    def __init__(self, text, provenance, section_path=(), entity=None,
                 entity_id=None, period_start=None, period_end=None,
                 lang=None, table=None, doc_id=None, chunk_index=0,
                 units_note=None):
        if not text or not text.strip():
            raise ValueError("passage text may not be empty")
        if not isinstance(provenance, Provenance):
            raise ValueError("passage requires a Provenance object")
        self.text = text
        self.provenance = provenance
        self.section_path = tuple(section_path)
        self.entity = entity
        self.entity_id = entity_id
        self.period_start = _parse_date(period_start, "period_start")
        self.period_end = _parse_date(period_end, "period_end")
        self.lang = lang or detect_language(text)
        self.table = table
        self.doc_id = doc_id
        self.chunk_index = chunk_index
        # Carried explicitly so a table row is never separated from the header
        # that gave it scale ("in millions"). See ingest.chunk_document.
        self.units_note = units_note

    @property
    def passage_id(self) -> str:
        h = hashlib.sha256()
        h.update((self.doc_id or "").encode("utf-8"))
        h.update(str(self.chunk_index).encode("utf-8"))
        h.update(self.text.encode("utf-8"))
        return h.hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passage_id": self.passage_id,
            "text": self.text,
            "section_path": list(self.section_path),
            "entity": self.entity,
            "entity_id": self.entity_id,
            "period_start": (self.period_start.isoformat()
                             if self.period_start else None),
            "period_end": (self.period_end.isoformat()
                           if self.period_end else None),
            "lang": self.lang,
            "is_table": bool(self.table),
            "units_note": self.units_note,
            "doc_id": self.doc_id,
            "chunk_index": self.chunk_index,
            "provenance": self.provenance.to_dict(),
        }


_ARABIC_RANGE = re.compile(r"[\u0600-\u06FF]")


def detect_language(text: str) -> str:
    """
    'fa' if the text contains Arabic-script characters, else 'en'.

    Deliberately crude and deterministic. A statistical detector would be a
    dependency and a nondeterminism for no benefit: the only distinction this
    system needs is Persian vs English.
    """
    if not text:
        return "en"
    return "fa" if _ARABIC_RANGE.search(text) else "en"


class Document(object):
    """A source document: metadata plus its passages and extracted facts."""

    __slots__ = ("doc_id", "title", "provenance", "entity", "entity_id",
                 "doc_type", "period_start", "period_end", "passages", "facts",
                 "lang")

    def __init__(self, doc_id, title, provenance, entity=None, entity_id=None,
                 doc_type=None, period_start=None, period_end=None,
                 passages=None, facts=None, lang=None):
        if not doc_id:
            raise ValueError("document requires a doc_id")
        if not isinstance(provenance, Provenance):
            raise ValueError("document requires a Provenance object")
        self.doc_id = doc_id
        self.title = title
        self.provenance = provenance
        self.entity = entity
        self.entity_id = entity_id
        self.doc_type = doc_type
        self.period_start = _parse_date(period_start, "period_start")
        self.period_end = _parse_date(period_end, "period_end")
        self.passages: List[Passage] = list(passages or [])
        self.facts: List[Fact] = list(facts or [])
        self.lang = lang

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "entity": self.entity,
            "entity_id": self.entity_id,
            "doc_type": self.doc_type,
            "period_start": (self.period_start.isoformat()
                             if self.period_start else None),
            "period_end": (self.period_end.isoformat()
                           if self.period_end else None),
            "n_passages": len(self.passages),
            "n_facts": len(self.facts),
            "provenance": self.provenance.to_dict(),
        }
