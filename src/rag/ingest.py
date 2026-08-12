"""
Ingestion and chunking (master prompt SS.5.2, Phase 3).

THE CHUNKING HAZARD THIS MODULE EXISTS TO PREVENT
-------------------------------------------------
A filing states its scale ONCE, in a table header:

    Consolidated Statements of Operations (in millions)
    Net sales ......................... 109,417

A fixed-window chunker splits that into "(in millions)" in one chunk and
"Net sales 109,417" in another. Retrieval then returns a row that says 109,417
with no indication whether that is dollars, thousands or millions -- a 10^6
error that looks completely reasonable and cites a real filing.

So chunking here is structure-aware:
  - section headings are tracked and attached to every chunk beneath them
  - a units/scale note ("in millions", "ارقام به میلیون ریال") is captured when
    seen and propagated to every chunk in that section
  - table rows are never split away from their header row
  - a chunk that contains numbers but has no resolvable scale is FLAGGED, not
    silently indexed

Stdlib only.
"""

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import re

from rag.documents import Document, Fact, Passage, Provenance, detect_language
from rag.sources import Source, check_access, get_source

# ---------------------------------------------------------------------------
# Scale and currency detection, bilingual.
# ---------------------------------------------------------------------------

SCALE_WORDS: Dict[str, float] = {
    "thousand": 1e3, "thousands": 1e3,
    "million": 1e6, "millions": 1e6,
    "billion": 1e9, "billions": 1e9,
    "lakh": 1e5, "crore": 1e7,
    "\u0647\u0632\u0627\u0631": 1e3,            # hezar
    "\u0645\u06cc\u0644\u06cc\u0648\u0646": 1e6,      # milyun
    "\u0645\u06cc\u0644\u06cc\u0627\u0631\u062f": 1e9,     # milyard
}

_SCALE_RE = re.compile(
    r"\((?:\s*(?:amounts?|figures?|\u0627\u0631\u0642\u0627\u0645|\u0645\u0628\u0627\u0644\u063a)?\s*"
    r"(?:in|\u0628\u0647)\s+)([a-z\u0600-\u06ff]+)",
    re.IGNORECASE)
_SCALE_BARE_RE = re.compile(
    r"\b(?:in|\u0628\u0647)\s+(thousands?|millions?|billions?|"
    r"\u0647\u0632\u0627\u0631|\u0645\u06cc\u0644\u06cc\u0648\u0646|\u0645\u06cc\u0644\u06cc\u0627\u0631\u062f)\b",
    re.IGNORECASE)

CURRENCY_WORDS: Dict[str, str] = {
    "usd": "USD", "us dollars": "USD", "dollars": "USD", "$": "USD",
    "eur": "EUR", "euros": "EUR", "\u20ac": "EUR",
    "gbp": "GBP", "\u00a3": "GBP",
    "irr": "IRR", "rials": "IRR", "rial": "IRR",
    "\u0631\u06cc\u0627\u0644": "IRR", "\u062a\u0648\u0645\u0627\u0646": "IRT",
}

# Headings: "Item 1A.", "PART II", markdown "## ", or a short ALL-CAPS line.
#
# CASE SENSITIVITY IS LOAD-BEARING HERE. An earlier version compiled the whole
# alternation with re.IGNORECASE, which defeated the ALL-CAPS branch: with that
# flag, `[A-Z][A-Z0-9 ,'&/()-]{6,80}` matches lowercase prose too. Every prose
# line that did not happen to end in a period was then classified as a heading
# and CONSUMED -- a document of ordinary sentences chunked to zero passages,
# silently. So the caps branch is matched case-sensitively and only the
# Item/Part branch is case-insensitive.
_HEADING_ITEM_RE = re.compile(
    r"^\s*(?:item|part)\s+[0-9ivx]{1,4}[a-z]?[.):]?(?:\s+\S.*)?\s*$",
    re.IGNORECASE)
_HEADING_CAPS_RE = re.compile(r"^\s*[A-Z][A-Z0-9 ,'&/()\u2014-]{5,79}\s*$")
_MD_HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.*\S)\s*$")

_NUMBER_RE = re.compile(r"[-+]?[\d\u0660-\u0669\u06f0-\u06f9][\d\u0660-\u0669"
                        r"\u06f0-\u06f9,\u066c\u066b.]*")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def detect_scale(text: str) -> Optional[Tuple[str, float]]:
    """Return (word, multiplier) if the text declares a scale."""
    for rx in (_SCALE_RE, _SCALE_BARE_RE):
        m = rx.search(text or "")
        if m:
            word = m.group(1).lower().strip()
            if word in SCALE_WORDS:
                return word, SCALE_WORDS[word]
    return None


def detect_currency(text: str) -> Optional[str]:
    low = (text or "").lower()
    # Longest keys first so "us dollars" wins over "dollars".
    for key in sorted(CURRENCY_WORDS, key=len, reverse=True):
        if key in low:
            return CURRENCY_WORDS[key]
    return None


def contains_number(text: str) -> bool:
    return bool(_NUMBER_RE.search(text or ""))


def _is_heading(line: str) -> bool:
    """
    Conservative heading test.

    Biased deliberately toward FALSE. A missed heading costs a section label;
    a false heading DELETES the line, because headings are consumed rather than
    emitted as content. Persian has no letter case, so an unmarked Persian
    heading is simply read as prose -- preserved but unlabelled, which is the
    safe direction to be wrong in.
    """
    if _MD_HEADING_RE.match(line):
        return True
    stripped = line.strip()
    if not stripped or len(stripped) > 90:
        return False
    if _TABLE_ROW_RE.match(line):
        return False
    # A heading rarely ends in sentence punctuation.
    if stripped[-1] in ".!?\u061f\u06d4:;,":
        # "Item 1A." is the documented exception: a bare item label.
        if not _HEADING_ITEM_RE.match(line):
            return False
    if _HEADING_ITEM_RE.match(line):
        return True
    return bool(_HEADING_CAPS_RE.match(line))


def _heading_level(line: str) -> int:
    m = _MD_HEADING_RE.match(line)
    if m:
        return len(m.group(1))
    if re.match(r"^\s*part\s", line, re.IGNORECASE):
        return 1
    if re.match(r"^\s*item\s", line, re.IGNORECASE):
        return 2
    return 3


def _heading_text(line: str) -> str:
    m = _MD_HEADING_RE.match(line)
    return (m.group(2) if m else line).strip()


class Block(object):
    """An intermediate structural unit: prose paragraph or whole table."""

    __slots__ = ("lines", "kind", "section_path", "units_note", "scale")

    def __init__(self, kind, section_path, units_note=None, scale=None):
        self.lines: List[str] = []
        self.kind = kind
        self.section_path = tuple(section_path)
        self.units_note = units_note
        self.scale = scale

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()


def split_blocks(text: str) -> List[Block]:
    """
    Split raw text into structural blocks, tracking headings and scale notes.

    Tables are kept whole. A scale note seen anywhere in a section applies to
    every block in that section until a new section or a new note replaces it.
    """
    blocks: List[Block] = []
    # Stack of (level, text). Keyed by LEVEL, not by list position: an earlier
    # version truncated with section[:level-1], so two sibling "##" headings in
    # a document with no "#" heading nested one inside the other and citations
    # reported "Operations / Employees" for a top-level Employees section.
    stack: List[Tuple[int, str]] = []
    section: List[str] = []
    # Scales are scoped the same way. A scale on a PARENT heading genuinely
    # governs its subsections, so it is inherited downward; a sibling or
    # shallower heading clears it. Clearing is the safe direction: the block is
    # then FLAGGED by unresolved_scale_passages rather than mis-scaled.
    scale_stack: List[Tuple[int, Tuple[str, float]]] = []
    current_scale: Optional[Tuple[str, float]] = None
    cur: Optional[Block] = None

    def flush():
        nonlocal cur
        if cur is not None and cur.text:
            blocks.append(cur)
        cur = None

    for raw in (text or "").splitlines():
        line = raw.rstrip()

        if _is_heading(line):
            flush()
            lvl = _heading_level(line)
            head = _heading_text(line)
            # Pop every heading at the same or deeper level: a sibling replaces
            # its sibling, it does not nest beneath it.
            while stack and stack[-1][0] >= lvl:
                stack.pop()
            stack.append((lvl, head))
            section = [h for _, h in stack]
            # A scale declared in a heading governs the section beneath it,
            # including its subsections.
            while scale_stack and scale_stack[-1][0] >= lvl:
                scale_stack.pop()
            found = detect_scale(head)
            if found:
                scale_stack.append((lvl, found))
            current_scale = scale_stack[-1][1] if scale_stack else None
            continue

        if not line.strip():
            flush()
            continue

        found = detect_scale(line)
        if found and not _TABLE_ROW_RE.match(line):
            current_scale = found

        is_table = bool(_TABLE_ROW_RE.match(line))
        want = "table" if is_table else "prose"
        if cur is None or cur.kind != want:
            flush()
            cur = Block(want, section,
                        units_note=current_scale[0] if current_scale else None,
                        scale=current_scale[1] if current_scale else None)
        # Keep the block's scale current if the note appeared mid-block.
        if current_scale and cur.scale is None:
            cur.units_note, cur.scale = current_scale[0], current_scale[1]
        cur.lines.append(line)

    flush()
    return blocks


def chunk_document(text: str, provenance: Provenance, doc_id: str,
                   entity: Optional[str] = None,
                   entity_id: Optional[str] = None,
                   period_start: Optional[str] = None,
                   period_end: Optional[str] = None,
                   max_chars: int = 1200) -> List[Passage]:
    """
    Chunk a document into Passages that each carry their own context.

    `max_chars` is a soft limit: a table is never split, because a row without
    its header is worse than a long chunk. Prose is split on paragraph and
    sentence boundaries, and every chunk inherits its section path and the
    scale note governing it.
    """
    # Redundant with Passage.__init__, which raises the same ValueError. Kept
    # deliberately: it fails on the WHOLE document before any chunking work,
    # and states the SS.5.2 rule at the entry point rather than leaving a
    # reader to infer it from a constructor three modules away. A mutation
    # battery correctly reports this as an equivalent mutant.
    if not isinstance(provenance, Provenance):
        raise ValueError("ingestion requires a Provenance object; an uncited "
                         "document may not enter the index (SS.5.2)")

    passages: List[Passage] = []
    idx = 0
    for block in split_blocks(text):
        body = block.text
        if not body:
            continue

        if block.kind == "table":
            pieces = [body]          # never split a table
        else:
            pieces = _split_prose(body, max_chars)

        for piece in pieces:
            passages.append(Passage(
                text=piece,
                provenance=provenance,
                section_path=block.section_path,
                entity=entity,
                entity_id=entity_id,
                period_start=period_start,
                period_end=period_end,
                table=(block.kind == "table"),
                doc_id=doc_id,
                chunk_index=idx,
                units_note=block.units_note,
            ))
            idx += 1
    return passages


def _split_prose(body: str, max_chars: int) -> List[str]:
    if len(body) <= max_chars:
        return [body]
    out: List[str] = []
    buf = ""
    # Split on sentence ends, including the Persian full stop and Arabic
    # question mark, so Persian text is not treated as one giant sentence.
    for sentence in re.split(r"(?<=[.!?\u061f\u06d4])\s+", body):
        if buf and len(buf) + len(sentence) + 1 > max_chars:
            out.append(buf.strip())
            buf = sentence
        else:
            buf = (buf + " " + sentence).strip() if buf else sentence
    if buf.strip():
        out.append(buf.strip())
    return out or [body]


def unresolved_scale_passages(passages: Iterable[Passage]) -> List[Passage]:
    """
    Passages that contain numbers but declare no scale.

    Not an error by itself -- plenty of prose contains a percentage or a year.
    It is a FLAG: the retrieval layer downgrades these and the answer layer
    must not quote a magnitude from them without a corroborating Fact.
    """
    return [p for p in passages
            if contains_number(p.text) and not p.units_note]


# ---------------------------------------------------------------------------
# EDGAR XBRL ingestion -> Facts (the "separate documents from time series" half)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Source-gated entry points.
#
# WHY INGESTION GOES THROUGH THE REGISTRY
# ---------------------------------------
# `sources.py` declared the access terms, but declaring them changes nothing on
# its own -- the acceptance criterion is "restricted data handled correctly",
# and until this point NOTHING called check_access(). A descoped source was
# refused only if a caller remembered to ask.
#
# It was also possible to ingest AS a source while contradicting its registered
# terms: the XBRL path below hardcoded trust_level="VERIFIED_PRIMARY" and its
# own licence string, so the registry and the ingested provenance were two
# copies of the same fact, free to drift. Worse, any caller could hand a
# Provenance claiming VERIFIED_PRIMARY for a source registered as UNVERIFIED,
# and nothing would notice.
#
# So: trust level and licence are READ FROM the registry, never passed in, and
# every gated entry point calls check_access() first.
# ---------------------------------------------------------------------------


def provenance_for(source_key: str, user_agent: Optional[str] = None,
                   api_key: Optional[str] = None, **fields) -> Provenance:
    """
    Build a Provenance whose trust level and licence come from the registry.

    Refuses if the source is unregistered, descoped, or its access terms are
    unmet -- so a Provenance object cannot exist for data we were not permitted
    to fetch.

    `trust_level` and `licence` may NOT be supplied by the caller. That is the
    point: the authority a passage carries into ranking is a property of the
    source, not an argument.
    """
    for reserved in ("trust_level", "licence"):
        if reserved in fields:
            raise ValueError(
                "%r is read from the source registry and may not be passed in; "
                "otherwise a caller could claim any authority for any source"
                % reserved)
    src = check_access(source_key, user_agent=user_agent, api_key=api_key)
    return Provenance(source=src.name,
                      trust_level=src.trust_level,
                      licence=src.licence,
                      **fields)


def ingest_document(text: str, source_key: str, doc_id: str,
                    user_agent: Optional[str] = None,
                    api_key: Optional[str] = None,
                    provenance: Optional[Provenance] = None,
                    **kwargs) -> List[Passage]:
    """
    Chunk a document only if its source permits ingestion.

    A caller may pass a pre-built `provenance` (the usual case, since filings
    carry accession numbers and filing dates), but its trust level must MATCH
    the registry. A passage claiming more authority than its source has would
    outrank correct evidence in reranking.
    """
    src = check_access(source_key, user_agent=user_agent, api_key=api_key)
    if provenance is None:
        provenance = provenance_for(source_key, user_agent=user_agent,
                                    api_key=api_key)
    elif not isinstance(provenance, Provenance):
        raise ValueError("provenance must be a Provenance object; an uncited "
                         "document may not enter the index (SS.5.2)")
    elif provenance.trust_level != src.trust_level:
        raise ValueError(
            "provenance claims trust_level %r but source %r is registered as "
            "%r; refusing to index evidence that overstates its own authority"
            % (provenance.trust_level, source_key, src.trust_level))
    return chunk_document(text, provenance, doc_id, **kwargs)


def facts_from_xbrl_companyconcept(payload: Dict[str, Any],
                                   retrieved_at: Optional[str] = None,
                                   base_url: Optional[str] = None,
                                   source_key: str = "sec_edgar_xbrl",
                                   user_agent: Optional[str] = None,
                                   api_key: Optional[str] = None
                                   ) -> List[Fact]:
    """
    Convert an EDGAR `companyconcept` payload into Facts.

    MEASURED on live data (Apple, RevenueFromContractWithCustomer...): one tag
    returned 117 facts spanning 3/6/9/12-month periods, and 46 periods were
    reported by more than one filing. Both are preserved rather than collapsed:
    period_kind keeps the durations apart, and every fact keeps its own
    accession and filing date so the conflict layer can pick the current one
    and SAY that it did.

    EDGAR reports raw units, so scale is 1. That is recorded explicitly rather
    than left implicit.
    """
    if not isinstance(payload, dict) or "units" not in payload:
        raise ValueError("not an EDGAR companyconcept payload: missing 'units'")

    # Gated even though the payload is already in hand: this is where the data
    # enters the index, and a payload fetched under terms we cannot satisfy
    # must not become citable evidence just because the fetch already happened.
    # Trust level and licence now come from the registry instead of being
    # hardcoded here, where they could drift from it silently.
    src = check_access(source_key, user_agent=user_agent, api_key=api_key)

    concept = payload.get("tag") or "unknown"
    entity = payload.get("entityName")
    cik = payload.get("cik")
    entity_id = ("%010d" % cik) if isinstance(cik, int) else (
        str(cik) if cik else None)
    label = payload.get("label") or concept

    out: List[Fact] = []
    for unit, rows in payload["units"].items():
        currency = unit if unit.isupper() and len(unit) == 3 else None
        for row in rows:
            accn = row.get("accn")
            url = None
            if base_url and entity_id and accn:
                url = "%s/%s/%s" % (base_url.rstrip("/"), entity_id,
                                    accn.replace("-", ""))
            prov = Provenance(
                source=src.name,
                source_id="xbrl/companyconcept",
                url=url,
                trust_level=src.trust_level,
                filed=row.get("filed"),
                retrieved_at=retrieved_at,
                accession=accn,
                licence=src.licence,
            )
            out.append(Fact(
                concept=concept,
                value=row["val"],
                unit=unit,
                provenance=prov,
                period_start=row.get("start"),
                period_end=row.get("end"),
                entity=entity,
                entity_id=entity_id,
                scale=1,                 # EDGAR XBRL is already in base units
                currency=currency,
                fiscal_year=row.get("fy"),
                fiscal_period=row.get("fp"),
                form=row.get("form"),
                label=label,
            ))
    return out
