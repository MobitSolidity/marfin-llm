"""
Phase 3 RAG regression suite.

Every assertion below corresponds to a defect that was FOUND, or to a hazard
verified against live EDGAR data. The exploratory probe scripts
(probe_ingest / probe_retrieval / probe_rerank / probe_citations /
probe_conflicts) found six real defects; these are the permanent tests that
stop them coming back.

VERIFICATION METHODS (same taxonomy as the calc suites):
  (B) HAND ARITHMETIC -- a magnitude computed independently and written literal
  (C) INVARIANT       -- a property that must hold whatever the implementation
  (D) FAILURE         -- bad input must refuse, not return something plausible
"""

import json
import operator
import os
import sys

from _harness import check, check_raises, check_true, section, summary

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rag.answer import answer_gate                                 # noqa: E402
from rag.citations import (_tolerance_for, extract_numbers,         # noqa: E402
                           verify_answer, verify_claim)
from rag.conflicts import (detect_period_mixing, resolve_facts,     # noqa: E402
                           resolve_result, staleness)
from rag.documents import (Fact, Passage, Provenance,               # noqa: E402
                           classify_period, detect_language)
from rag.ingest import (_is_heading, chunk_document, detect_scale,  # noqa: E402
                        detect_currency, facts_from_xbrl_companyconcept,
                        ingest_document, provenance_for, split_blocks,
                        unresolved_scale_passages)
from market import tradingview as tv                                # noqa: E402
from rag.normalize import compound_variants, fold, index_terms, tokenize  # noqa
from rag.rerank import (W_AUTHORITY, W_RECENCY,                     # noqa: E402
                        _normalize_scores, rerank)
from rag.retrieval import (FactStore, HybridRetriever,              # noqa: E402
                           PassageIndex, RetrievalResult)
from rag.sources import (AccessError, SOURCES, Source, _is_contact_ua,  # noqa
                         check_access, descoped_sources, enabled_sources,
                         get_source, manifest, register_source)

# A User-Agent that names a reachable contact, as SEC requires.
# MEASURED 2026-08-10: contact UA -> HTTP 200, absent UA -> HTTP 403.
CONTACT_UA = "marfin-llm/0.1 (contact@example.com)"

PROV = Provenance(source="SEC EDGAR", trust_level="VERIFIED_PRIMARY",
                  filed="2026-07-31", accession="0000320193-26-000020")
BLOG = Provenance(source="Blog", trust_level="PERMITTED_NEWS",
                  published="2026-06-01")
OLD = Provenance(source="SEC EDGAR", trust_level="VERIFIED_PRIMARY",
                 filed="2011-01-01", accession="acc-old")

FA_ZWNJ = "\u0627\u0631\u0632\u0634\u200c\u06af\u0630\u0627\u0631\u06cc"
FA_SPACE = "\u0627\u0631\u0632\u0634 \u06af\u0630\u0627\u0631\u06cc"
FA_SOLID = "\u0627\u0631\u0632\u0634\u06af\u0630\u0627\u0631\u06cc"


def mkp(text, prov=PROV, i=0, units=None, table=False, entity=None):
    return Passage(text=text, provenance=prov, doc_id="d", chunk_index=i,
                   units_note=units, table=table, entity=entity)


def mkf(val, filed, end="2026-06-27", start="2026-03-29", unit="USD",
        trust="VERIFIED_PRIMARY", accn=None, concept="Revenues", scale=1):
    return Fact(concept=concept, value=val, unit=unit, scale=scale,
                provenance=Provenance(source="SEC EDGAR", trust_level=trust,
                                      filed=filed, accession=accn or filed),
                period_start=start, period_end=end, entity="Apple Inc.")


# ---------------------------------------------------------------------------
section("normalization: bilingual, and symmetric on BOTH sides")
# ---------------------------------------------------------------------------

check_true("ZWNJ and spaced spellings fold together",
           fold(FA_ZWNJ) == fold(FA_SPACE), "(C) invariant")
check_true("all three Persian spellings share an index term",
           set(index_terms(FA_ZWNJ)) & set(index_terms(FA_SOLID)) and
           set(index_terms(FA_SPACE)) & set(index_terms(FA_SOLID)),
           "(C) the defect probe R6 found")
check_true("arabic yeh/kaf fold to persian forms",
           fold("\u0643\u064a\u0641\u064a\u062a") == fold("\u06a9\u06cc\u0641\u06cc\u062a"), "(C)")
check_true("persian digits fold to ascii",
           tokenize("\u06f1\u06f2\u06f3") == ["123"], "(B)")
check_true("thousands separators dropped inside numbers",
           tokenize("109,417") == ["109417"], "(B)")
check_true("fold is idempotent", fold(fold(FA_ZWNJ)) == fold(FA_ZWNJ), "(C)")
check_true("compound variants do NOT inflate base token count",
           len(tokenize(FA_SPACE)) == 2 and len(index_terms(FA_SPACE)) == 3,
           "(C) BM25 length normalization would penalise Persian")
check_true("english text gains no compound variants",
           compound_variants(tokenize("net sales revenue")) == [], "(C)")

# ---------------------------------------------------------------------------
section("ingestion: heading detection (silent content loss)")
# ---------------------------------------------------------------------------

# DEFECT FOUND: _HEADING_RE was compiled with re.IGNORECASE, which made the
# ALL-CAPS branch match lowercase prose. Every prose line not ending in a
# period was classified as a heading and CONSUMED -> zero passages, silently.
for prose in ("we expect margins to improve",
              "The Company is exposed to credit risk",
              "Net sales increased primarily due to higher iPhone revenue"):
    check_true("prose is NOT a heading: %r" % prose[:28],
               not _is_heading(prose), "(D) silent content loss")
for head in ("## Risk Factors", "Item 1A. Risk Factors", "PART II",
             "CONSOLIDATED BALANCE SHEETS"):
    check_true("heading IS a heading: %r" % head[:28], _is_heading(head), "(C)")

NO_PERIODS = """\
## Management Discussion

Net sales increased primarily due to higher iPhone revenue
Gross margin was flat year over year
"""
_ps = chunk_document(NO_PERIODS, PROV, doc_id="d")
check_true("prose without terminal periods survives chunking",
           len(_ps) == 1 and "iPhone revenue" in _ps[0].text,
           "(D) the zero-passage defect")
check_true("no document of ordinary sentences chunks to nothing",
           len(chunk_document("## H\n\nplain words here\n", PROV,
                              doc_id="d")) == 1, "(D)")

# ---------------------------------------------------------------------------
section("ingestion: heading nesting")
# ---------------------------------------------------------------------------

# DEFECT FOUND: section[:level-1] treated depth as a list position, so two
# sibling "##" headings nested one inside the other when no "#" was present.
NEST = """\
## Operations

alpha text

## Employees

beta text
"""
_np = chunk_document(NEST, PROV, doc_id="d")
check_true("sibling headings do not nest",
           _np[1].section_path == ("Employees",),
           "(C) was ('Operations','Employees')")
DEEP = """\
# PART II

## Item 7. MD&A

### Liquidity

cash was tight
"""
check_true("genuine nesting is preserved",
           chunk_document(DEEP, PROV, doc_id="d")[0].section_path
           == ("PART II", "Item 7. MD&A", "Liquidity"), "(C)")

# ---------------------------------------------------------------------------
section("ingestion: the scale hazard (10^6 error)")
# ---------------------------------------------------------------------------

check_true("scale from a table header", detect_scale("Statements (in millions)")
           == ("millions", 1e6), "(B)")
check_true("scale from bare prose",
           detect_scale("amounts in thousands") == ("thousands", 1e3), "(B)")
check_true("persian scale", detect_scale(
    "\u0627\u0631\u0642\u0627\u0645 \u0628\u0647 \u0645\u06cc\u0644\u06cc\u0648\u0646 \u0631\u06cc\u0627\u0644")[1] == 1e6, "(B)")
check_true("no false scale", detect_scale("sales rose this quarter") is None,
           "(D)")
check_true("currency detected", detect_currency("in millions of dollars")
           == "USD", "(B)")

FILING = """\
# Consolidated Statements of Operations (in millions)

| Item | Q3 2026 |
| --- | --- |
| Net sales | 109,417 |
"""
_rows = chunk_document(FILING, PROV, doc_id="d")
_row = [p for p in _rows if "109,417" in p.text]
check_true("the numeric row keeps its units note",
           len(_row) == 1 and _row[0].units_note == "millions",
           "(C) THE hazard this module exists to prevent")
check_true("the row is not split from its header",
           "Item" in _row[0].text, "(C)")

BIG = "# T (in millions)\n\n| a | b |\n| --- | --- |\n" + \
      "".join("| row%d | %d |\n" % (i, i) for i in range(200))
_bp = chunk_document(BIG, PROV, doc_id="d")
check_true("a table is never split, even far past max_chars",
           len(_bp) == 1 and len(_bp[0].text) > 1200, "(C)")

# MUTATION SURVIVOR: replacing the table branch with _split_prose was a no-op
# on the table above, because it has no sentence punctuation to split on. Real
# filings use dot leaders, which _split_prose happily treats as sentence ends.
LEADERS = """\
# Statements (in millions)

| Item | Amount |
| --- | --- |
| Net sales .................... | 109,417 |
| Cost of sales ................ | 60,020 |
| Gross margin ................. | 49,397 |
"""
_lp = chunk_document(LEADERS, PROV, doc_id="d", max_chars=40)
check_true("a table with dot leaders is still never split",
           len(_lp) == 1 and _lp[0].table,
           "(D) dot leaders look like sentence ends")
check_true("every row stays with the header row",
           all(s in _lp[0].text for s in ("Item", "Net sales",
                                          "Gross margin")), "(C)")
check_true("long prose IS split",
           len(chunk_document("# S\n\n" + "A sentence about revenue. " * 120,
                              PROV, doc_id="d", max_chars=400)) > 1, "(C)")

INHERIT = """\
## Operations (in millions)

### Segment A

revenue was 1,234

## Employees

we had 164,000 people
"""
_ip = chunk_document(INHERIT, PROV, doc_id="d")
check_true("scale is inherited by a SUBsection",
           _ip[0].units_note == "millions", "(C)")
check_true("scale does NOT leak to a sibling section",
           _ip[1].units_note is None, "(D) a leak would mis-scale by 10^6")
check_true("numbers with no scale are FLAGGED",
           len(unresolved_scale_passages(_ip)) == 1, "(D)")
check_raises("ingestion refuses a document with no provenance",
             lambda: chunk_document("text", None, doc_id="d"), ValueError)
check_raises("ingestion refuses a non-Provenance object",
             lambda: chunk_document("text", "SEC EDGAR", doc_id="d"),
             ValueError)

# ---------------------------------------------------------------------------
section("documents: period and comparability")
# ---------------------------------------------------------------------------

check_true("90-day fiscal quarter classifies as quarter",
           classify_period("2026-03-29", "2026-06-27") == "quarter", "(B)")
check_true("365-day span classifies as annual",
           classify_period("2025-06-29", "2026-06-27") == "annual", "(B)")
check_true("quarterly is NOT comparable to annual",
           not mkf(1.0, "2026-07-31").is_comparable_to(
               mkf(1.0, "2026-07-31", start="2025-06-29")),
           "(C) the period-mixing hazard")
check_true("scale is applied exactly once",
           mkf(109417.0, "2026-07-31", scale=1e6).normalized_value
           == 109417000000.0, "(B)")
check_true("language detection", detect_language(FA_ZWNJ) == "fa"
           and detect_language("revenue") == "en", "(C)")
check_raises("Fact refuses a missing unit",
             lambda: Fact(concept="x", value=1, unit="", provenance=PROV))
check_raises("Fact refuses NaN",
             lambda: Fact(concept="x", value=float("nan"), unit="USD",
                          provenance=PROV))
check_raises("Provenance refuses an unknown trust level",
             lambda: Provenance(source="s", trust_level="MADE_UP"))

# ---------------------------------------------------------------------------
section("retrieval: abstention is a first-class outcome")
# ---------------------------------------------------------------------------

check_true("empty index abstains with a reason",
           not PassageIndex().search("revenue").ok, "(D)")
_idx = PassageIndex()
_idx.add(mkp("The Company is exposed to credit risk"))
check_true("no match abstains", not _idx.search("hashrate mining").ok, "(D)")
check_true("abstention carries a reason",
           bool(_idx.search("hashrate mining").reason), "(D)")
# MUTATION SURVIVOR: these passed even with the isinstance guards removed,
# because a bare string then raised AttributeError deeper in the call and
# check_raises(Exception) accepted it. Asserting the SPECIFIC type is what
# distinguishes a deliberate refusal from an incidental crash.
check_raises("index refuses a bare string", lambda: PassageIndex().add("text"),
             ValueError)
check_raises("fact store refuses a dict", lambda: FactStore().add({"v": 1}),
             ValueError)

_r = PassageIndex()
_r.add(mkp("Weather was mild", i=0))
_r.add(mkp("Revenue revenue revenue growth", i=1))
_r.add(mkp("Revenue mentioned once", i=2))
_res = _r.search("revenue")
check_true("BM25 ranks by term frequency, not input order",
           _res.scores[0] > _res.scores[1], "(C)")
check_true("non-matching passage is excluded", len(_res) == 2, "(C)")

_f = PassageIndex()
_f.add(mkp("Apple revenue rose", entity="Apple Inc.", i=0))
_f.add(mkp("Microsoft revenue rose", entity="Microsoft Corp", i=1))
_f.add(mkp("Apple revenue will moon", prov=BLOG, entity="Apple Inc.", i=2))
check_true("entity is a HARD filter",
           len(_f.search("revenue", entity="Apple Inc.")) == 2, "(C)")
check_true("min_trust is a HARD filter",
           len(_f.search("revenue", min_trust=90)) == 2, "(C)")
_leak = PassageIndex()
_leak.add(mkp("guidance raised", prov=OLD, i=0))
_leak.add(mkp("guidance raised again", prov=PROV, i=1))
_cut = _leak.search("guidance", as_of="2025-01-01")
check_true("as_of excludes documents filed later (no lookahead leak)",
           len(_cut) == 1 and _cut.hits[0].provenance.accession == "acc-old",
           "(D) backtest integrity")

_fa = PassageIndex()
_fa.add(mkp("\u0631\u0648\u0634 " + FA_ZWNJ + " \u0634\u0631\u06a9\u062a"))
for _q, _name in ((FA_ZWNJ, "zwnj"), (FA_SPACE, "spaced"),
                  (FA_SOLID, "solid")):
    check_true("Persian query (%s spelling) retrieves" % _name,
               _fa.search(_q).ok, "(C) one-sided normalization bug")

# ---------------------------------------------------------------------------
section("retrieval: structured facts, real EDGAR payload")
# ---------------------------------------------------------------------------

_XBRL = "/tmp/xbrl.json"
if os.path.exists(_XBRL):
    with open(_XBRL) as fh:
        _payload = json.load(fh)
    _facts = facts_from_xbrl_companyconcept(_payload,
                                            retrieved_at="2026-08-10",
                                            user_agent=CONTACT_UA)
    check("live payload yields 117 facts", len(_facts), 117, 0,
          "(B) MEASURED from data.sec.gov")
    _kinds = {}
    for _x in _facts:
        _kinds[_x.period_kind] = _kinds.get(_x.period_kind, 0) + 1
    check("64 quarterly facts", _kinds.get("quarter"), 64, 0, "(B) MEASURED")
    check("21 annual facts", _kinds.get("annual"), 21, 0, "(B) MEASURED")
    check_true("one tag really does mix 4 period lengths",
               len(_kinds) == 4, "(B) MEASURED")
    _periods = {}
    for _x in _facts:
        _periods.setdefault((_x.period_start, _x.period_end), set()).add(
            _x.provenance.accession)
    check("46 periods reported by more than one filing",
          len([k for k, v in _periods.items() if len(v) > 1]), 46, 0,
          "(B) MEASURED restatement hazard")
    check_true("EDGAR facts are raw units (scale 1)",
               all(_x.scale == 1.0 for _x in _facts), "(C)")

    _fs = FactStore()
    _fs.add_all(_facts)
    _c = _fs.concepts()[0]
    check_true("period_kind is a HARD filter on facts",
               {x.period_kind for x in _fs.query(_c, period_kind="quarter")}
               == {"quarter"}, "(C)")
    _dates = [x.provenance.effective_date for x in _fs.query(_c)]
    check_true("facts are returned newest filing first",
               all(_dates[i] >= _dates[i + 1]
                   for i in range(len(_dates) - 1)), "(C)")
    check_true("unknown concept abstains",
               not _fs.query("NotARealTag").ok, "(D)")
    check_true("impossible filter abstains",
               not _fs.query(_c, fiscal_year=1999).ok, "(D)")
else:
    print("  SKIP  live XBRL payload absent (/tmp/xbrl.json)")

check_true("hybrid reports the two modes separately",
           set(HybridRetriever().retrieve("revenue")) == {"lexical",
                                                          "structured"}, "(C)")
check_true("structured is skipped, not faked, without a concept",
           not HybridRetriever().retrieve("revenue")["structured"].ok, "(D)")

# ---------------------------------------------------------------------------
section("reranking: score normalization and feature weights")
# ---------------------------------------------------------------------------

# DEFECT FOUND: min-max normalization mapped [40.0, 39.9] to [1.0, 0.0],
# inflating a 0.25% difference into the maximum gap so no feature could ever
# break a near-tie.
_n = _normalize_scores([40.0, 39.9])
check_true("near-tie stays a near-tie after normalization",
           _n[1] > 0.99, "(C) min-max gave 0.0")
check_true("a real gap stays a gap",
           _normalize_scores([9.0, 0.4])[1] < 0.1, "(C)")
check_true("all-equal scores normalize to 1.0",
           _normalize_scores([5.0, 5.0, 5.0]) == [1.0, 1.0, 1.0], "(C)")
check_true("abstention reranks to nothing",
           rerank(RetrievalResult([], reason="empty")) == [], "(D)")
# MUTATION SURVIVOR: this defaulted to exc=Exception, so removing the guard
# still "passed" -- a bare list then raises AttributeError from deeper in the
# call, and a crash is not a refusal. The specific type is the assertion.
check_raises("rerank refuses a bare list", lambda: rerank([mkp("x")]),
             ValueError)
check_raises("rerank refuses None", lambda: rerank(None), ValueError)

_tie = RetrievalResult([mkp("revenue grew", BLOG, 0),
                        mkp("revenue grew", PROV, 1)], scores=[1.0, 1.0])
check_true("authority breaks a lexical tie",
           rerank(_tie)[0].passage.provenance.trust_level
           == "VERIFIED_PRIMARY", "(C)")

# MUTATION SURVIVOR: the tie test above ALSO differed in date (blog published
# 2026-06-01 vs filing filed 2026-07-31), so the filing won on recency even
# with W_AUTHORITY zeroed. Two features co-varied and neither was isolated --
# the same "factor equals 1" blind spot as the Greeks. Same date isolates it.
_SAMEDAY_BLOG = Provenance(source="Blog", trust_level="PERMITTED_NEWS",
                           published="2026-07-31")
_auth_only = RetrievalResult([mkp("revenue grew", _SAMEDAY_BLOG, 0),
                              mkp("revenue grew", PROV, 1)],
                             scores=[1.0, 1.0])
check_true("authority alone decides when dates are IDENTICAL",
           rerank(_auth_only, as_of="2026-08-10")[0].passage.provenance
           .trust_level == "VERIFIED_PRIMARY",
           "(C) isolates authority from recency")
# ...and even that could not detect W_AUTHORITY=0, because the sort's SECONDARY
# key is also authority, so the filing still won on the tie-break. Ranking
# order cannot distinguish a weight from a tie-break; the SCORE can.
_ao = rerank(_auth_only, as_of="2026-08-10")
check_true("authority contributes a nonzero score component",
           _ao[0].components["authority"] > 0.0, "(D) weight, not tie-break")
check_true("a higher-trust source scores strictly above a lower-trust one",
           _ao[0].components["authority"] > _ao[1].components["authority"],
           "(D)")
check("authority component equals weight times normalized authority",
      _ao[0].components["authority"], W_AUTHORITY * 1.0, 1e-12,
      "(B) 100/100 authority")
_near = RetrievalResult([mkp("revenue", BLOG, 0), mkp("revenue", PROV, 1)],
                        scores=[40.0, 39.9])
check_true("authority decides a NEAR-tie too",
           rerank(_near)[0].passage.provenance.trust_level
           == "VERIFIED_PRIMARY", "(C) the min-max defect")
_gap = RetrievalResult([mkp("revenue revenue revenue", BLOG, 0),
                        mkp("weather was mild", PROV, 1)], scores=[9.0, 0.4])
check_true("authority does NOT overrule a large lexical gap",
           rerank(_gap)[0].passage.provenance.trust_level
           == "PERMITTED_NEWS", "(C) reranker must not become a trust sort")
_rec = RetrievalResult([mkp("revenue grew", OLD, 0),
                        mkp("revenue grew", PROV, 1)], scores=[1.0, 1.0])
check_true("recency breaks a tie between equal-authority sources",
           rerank(_rec, as_of="2026-08-10")[0].passage.provenance.filed
           .isoformat() == "2026-07-31", "(C)")
# MUTATION SURVIVOR: asserting only >= 0.0 could not detect the guard being
# removed, because a negative age produces a bonus ABOVE the maximum, not
# below zero. The bound has to be checked at BOTH ends.
_future = rerank(RetrievalResult([mkp("revenue", PROV, 0)], scores=[1.0]),
                 as_of="2020-01-01")[0].components["recency"]
check_true("future-dated document gets no recency bonus at all",
           _future == 0.0, "(D) was 'is it >= 0', which a 1.4 bonus passes")
check_true("recency bonus never exceeds its weight",
           _future <= W_RECENCY, "(D) upper bound")
_un = RetrievalResult([mkp("net sales 109,417", PROV, 0),
                       mkp("net sales 109,417", PROV, 1, units="millions")],
                      scores=[1.0, 1.0])
check_true("a passage with resolvable units outranks one without",
           rerank(_un)[0].passage.units_note == "millions", "(C)")
check_true("reranking is deterministic across runs",
           len({tuple(h.passage.passage_id for h in rerank(_tie))
                for _ in range(5)}) == 1, "(C)")

# MUTATION SURVIVOR: repeating the SAME input proves nothing, because Python's
# sort is stable -- identical input gives identical output even with a
# non-total key. A total order must survive PERMUTING the input.
_a = mkp("revenue grew", PROV, 0)
_b = mkp("revenue grew", PROV, 1)
_fwd = rerank(RetrievalResult([_a, _b], scores=[1.0, 1.0]))
_rev = rerank(RetrievalResult([_b, _a], scores=[1.0, 1.0]))
check_true("tie order is total: input permutation cannot change it",
           [h.passage.passage_id for h in _fwd]
           == [h.passage.passage_id for h in _rev],
           "(C) stability is not determinism")
_c = mkp("revenue grew", PROV, 2)
_p1 = rerank(RetrievalResult([_a, _b, _c], scores=[1.0, 1.0, 1.0]))
_p2 = rerank(RetrievalResult([_c, _a, _b], scores=[1.0, 1.0, 1.0]))
check_true("three-way tie is also order-independent",
           [h.passage.passage_id for h in _p1]
           == [h.passage.passage_id for h in _p2], "(C)")

# ---------------------------------------------------------------------------
section("citations: the scale trap")
# ---------------------------------------------------------------------------

_row2 = [p for p in chunk_document(FILING, PROV, doc_id="d")
         if "109,417" in p.text][0]
check_true("scaled claim is SUPPORTED",
           verify_claim("Revenue was $109,417 million", _row2).ok, "(C)")
check_true("SAME DIGITS without the scale word is CONTRADICTED",
           verify_claim("Revenue was $109,417", _row2).status
           == "CONTRADICTED", "(D) the 10^6 error")
check_true("percentages are not treated as magnitudes",
           extract_numbers("grew 12%") == [], "(C)")
check_true("scale word attaches to the number",
           extract_numbers("109.4 billion")[0].magnitude == 1.094e11, "(B)")

# DEFECT FOUND: a fixed 0.5% tolerance accepted "109.5 billion" as support for
# 109.417 billion. Tolerance now follows the claim's own stated precision.
for _claim, _want in (("Revenue was 109.4 billion", "SUPPORTED"),
                      ("Revenue was 109.5 billion", "CONTRADICTED"),
                      ("Revenue was 109.42 billion", "SUPPORTED"),
                      ("Revenue was 109.41 billion", "CONTRADICTED"),
                      ("Revenue was 109 billion", "SUPPORTED"),
                      ("Revenue was 110 billion", "CONTRADICTED"),
                      ("Revenue was 109,417 million", "SUPPORTED"),
                      ("Revenue was 109,418 million", "CONTRADICTED")):
    check_true("precision-scoped tolerance: %r -> %s"
               % (_claim[12:], _want),
               verify_claim(_claim, _row2).status == _want,
               "(B) half-ulp of the claim's last digit")
check_true("tolerance shrinks as the claim states more digits",
           _tolerance_for(extract_numbers("109.4 billion")[0])
           > _tolerance_for(extract_numbers("109.42 billion")[0]), "(C)")

# DEFECT FOUND: unscaled evidence REJECTED the scaled reading but ACCEPTED the
# bare one, silently assuming base units.
_naked = mkp("Net sales were 109,417 for the quarter", i=9)
check_true("unscaled evidence cannot support a scaled claim",
           not verify_claim("Revenue was $109,417 million", _naked).ok, "(D)")
check_true("unscaled evidence cannot support a BARE claim either",
           not verify_claim("Revenue was $109,417", _naked).ok,
           "(D) the asymmetry defect")
check_true("a claim with no number is not silently passed",
           verify_claim("Revenue increased", _row2).status == "UNSUPPORTED",
           "(D)")
check_true("no evidence is UNSUPPORTED, not SUPPORTED",
           verify_claim("Revenue was 5 million", None).status
           == "UNSUPPORTED", "(D)")

# MUTATION SURVIVOR: the None case above is caught by a DIFFERENT guard, so
# removing the provenance check went undetected. Evidence that exists but
# carries no provenance is the case that matters -- it is what an untrusted
# scraped snippet looks like.
check_true("evidence object with no provenance cannot be cited",
           verify_claim("Revenue was 5 million", "a scraped snippet").status
           == "UNSUPPORTED", "(D) refuses rather than crashing")
check_true("the refusal names the missing provenance",
           "provenance" in verify_claim("Revenue was 5 million",
                                        "a scraped snippet").detail, "(D)")
check_true("citation string names its source and accession",
           "0000320193-26-000020" in
           verify_claim("Revenue was $109,417 million", _row2).render(), "(C)")
_ans = verify_answer([("Revenue was $109,417 million", _row2),
                      ("Revenue was $109,417", _row2)])
check_true("one bad claim invalidates the whole answer",
           not _ans["ok"] and _ans["must_abstain"], "(D) no dilution")
check_true("an all-good answer passes",
           verify_answer([("Revenue was $109,417 million", _row2)])["ok"],
           "(C)")

# ---------------------------------------------------------------------------
section("conflicts: restatement, period mixing, staleness")
# ---------------------------------------------------------------------------

_rest = resolve_facts([mkf(109000000000.0, "2026-05-01", accn="old"),
                       mkf(109417000000.0, "2026-07-31", accn="new")],
                      as_of="2026-08-10")
check_true("newest filing is chosen",
           _rest.chosen.provenance.accession == "new", "(C)")
check_true("superseded figure is REPORTED, not dropped",
           len(_rest.superseded) == 1 and any("restated" in w
                                              for w in _rest.warnings),
           "(D) resolution is never silent")
check_true("agreeing filings are not flagged as a restatement",
           not resolve_facts([mkf(1e11, "2026-05-01"), mkf(1e11, "2026-07-31")],
                             as_of="2026-08-10").superseded, "(C)")
_mixed = [mkf(1e11, "2026-07-31"),
          mkf(3.6e11, "2026-07-31", start="2025-06-29")]
check_true("period kinds are detected",
           detect_period_mixing(_mixed) == ["annual", "quarter"], "(C)")
check_true("period mixing is REFUSED, not resolved",
           resolve_facts(_mixed).status == "REFUSED", "(D)")
# MUTATION SURVIVOR: the comparable-key guard also refuses this set, so status
# alone could not tell whether the PERIOD check ran. The reason has to name it,
# or a user gets a misleading explanation for a correct refusal.
check_true("the refusal explains that periods were mixed",
           "period kinds" in resolve_facts(_mixed).reason,
           "(D) two guards, distinguishable only by reason")
check_true("equal authority + equal date + different value = CONFLICT",
           resolve_facts([mkf(1e11, "2026-07-31", accn="a"),
                          mkf(9e11, "2026-07-31", accn="b")]).status
           == "CONFLICT", "(D) no invented tie-break")
check_true("higher authority beats a newer low-trust source",
           resolve_facts([mkf(1e11, "2026-07-31", accn="filing"),
                          mkf(5e11, "2026-08-09", trust="PERMITTED_NEWS",
                              accn="blog")], as_of="2026-08-10")
           .chosen.provenance.accession == "filing", "(C)")
check_true("different concepts are never collapsed",
           resolve_facts([mkf(1.0, "2026-07-31", concept="Revenues"),
                          mkf(2.0, "2026-07-31", concept="NetIncomeLoss")])
           .status == "REFUSED", "(D)")
check_true("empty set abstains", resolve_facts([]).status == "EMPTY", "(D)")

_st = staleness(mkf(1.0, "2026-08-09", start="2023-01-01", end="2023-03-31"),
                as_of="2026-08-10")
check_true("staleness is measured from PERIOD END, not filing date",
           _st["stale"] and _st["age_days"] > 1000,
           "(C) a fresh filing about an old period is stale data")
check_true("a current quarter is not stale",
           not staleness(mkf(1.0, "2026-07-31"), as_of="2026-08-10")["stale"],
           "(C)")
check_true("a fact with no period end is treated as stale",
           staleness(Fact(concept="X", value=1.0, unit="USD",
                          provenance=PROV), as_of="2026-08-10")["stale"],
           "(D) never assumed fresh")
check_raises("resolve_result refuses a bare list",
             lambda: resolve_result(["x"]))

# ---------------------------------------------------------------------------
section("the abstention gate (Phase 3 acceptance)")
# ---------------------------------------------------------------------------

_good = mkf(109417000000.0, "2026-07-31", accn="acc-new")
check_true("no evidence -> may_answer is False",
           not answer_gate(RetrievalResult([], reason="none")).may_answer,
           "(D) THE acceptance criterion")
check_true("no evidence names the reason",
           answer_gate([]).code == "NO_EVIDENCE", "(D)")

# MUTATION SURVIVORS: the gate's early guards are redundant with resolution,
# which also abstains on an empty set -- so removing them left may_answer
# False and the test green. The guards earn their place by producing a message
# a user can act on, naming what the retriever actually said. That is the
# behaviour worth pinning.
_nofound = answer_gate(RetrievalResult(
    [], reason="concept 'Revenues' is not in the fact store"))
check_true("the abstention repeats the retriever's own reason",
           "not in the fact store" in _nofound.message, "(D)")
check_true("the abstention states that memory is not a fallback",
           "memory" in _nofound.message, "(D) SS.0B")
check_true("an empty fact list says the same",
           "memory" in answer_gate([]).message, "(D)")
check_true("good evidence + true claim -> permitted",
           answer_gate([_good], claim="Revenue was $109,417 million",
                       as_of="2026-08-10").may_answer, "(C)")
check_true("permission always carries the citation",
           answer_gate([_good], claim="Revenue was $109,417 million",
                       as_of="2026-08-10").citations[0].ok, "(C)")
check_true("wrong-scale claim is refused even with perfect evidence",
           answer_gate([_good], claim="Revenue was $109,417",
                       as_of="2026-08-10").code == "UNVERIFIED_CLAIM", "(D)")
check_true("low-trust evidence cannot be quoted",
           answer_gate([mkf(1.0, "2026-07-31", trust="PERMITTED_NEWS")],
                       claim="It was 1 dollar", as_of="2026-08-10").code
           == "LOW_TRUST", "(D)")
_stale = mkf(5.0, "2024-01-31", start="2023-09-30", end="2023-12-31")
check_true("stale evidence is refused by default",
           answer_gate([_stale], claim="It was 5 dollars",
                       as_of="2026-08-10").code == "STALE", "(D)")
check_true("stale evidence is quotable only on explicit request",
           answer_gate([_stale], claim="It was 5 dollars", as_of="2026-08-10",
                       allow_stale=True).may_answer, "(C)")
check_true("period mixing surfaces as a malformed question",
           answer_gate(_mixed, claim="Revenue was $109,417 million").code
           == "MALFORMED_QUESTION", "(D)")
check_true("an unbreakable conflict is reported, not resolved",
           answer_gate([mkf(1e11, "2026-07-31", accn="a"),
                        mkf(9e11, "2026-07-31", accn="b")]).code
           == "CONFLICT", "(D)")
check_true("a restatement answers but discloses supersession",
           answer_gate([mkf(109000000000.0, "2026-05-01", accn="old"),
                        mkf(109417000000.0, "2026-07-31", accn="new")],
                       claim="Revenue was $109,417 million",
                       as_of="2026-08-10").warnings, "(D)")

if os.path.exists(_XBRL):
    _fs2 = FactStore()
    _fs2.add_all(facts_from_xbrl_companyconcept(_payload,
                                                retrieved_at="2026-08-10",
                                                user_agent=CONTACT_UA))
    _c2 = _fs2.concepts()[0]
    _one = _fs2.query(_c2, period_kind="quarter", period_end="2026-06-27")
    check_true("REAL DATA: narrowed query permits a cited answer",
               answer_gate(_one, claim="Revenue was $109,417 million",
                           as_of="2026-08-10").may_answer, "(C) end to end")
    check_true("REAL DATA: the unnarrowed 64-fact set is refused",
               answer_gate(_fs2.query(_c2, period_kind="quarter"),
                           claim="Revenue was $109,417 million",
                           as_of="2026-08-10").code == "MALFORMED_QUESTION",
               "(D) period mixing on live data")


# ---------------------------------------------------------------------------
section("source registry: terms are enforced, not merely declared")
# ---------------------------------------------------------------------------
# Every assertion here is a defect found on the FIRST execution of sources.py.
# The module had been written and committed to disk without ever being run;
# three of the four findings below were live exploits.

check("6 sources registered", len(SOURCES), 6, 0, "(C)")
check("3 enabled", len(enabled_sources()), 3, 0, "(C)")
check("3 descoped (2x Q3 scope, 1x TradingView licence)",
      len(descoped_sources()), 3, 0, "(C)")
check_true("registry key always matches source.key",
           all(k == v.key for k, v in SOURCES.items()), "(C)")
check_true("every source records a doc_url or a descope_reason",
           all(s.doc_url or s.descope_reason for s in SOURCES.values()),
           "(C) no source is unexplained")

# --- the MEASURED HTTP behaviours, encoded as refusals -----------------------
check_raises("EDGAR xbrl without contact UA is refused (MEASURED 403)",
             lambda: check_access("sec_edgar_xbrl"), AccessError)
check_raises("EDGAR submissions with empty UA is refused",
             lambda: check_access("sec_edgar_submissions", user_agent=""),
             AccessError)
check_true("EDGAR xbrl with contact UA is permitted (MEASURED 200)",
           check_access("sec_edgar_xbrl",
                        user_agent=CONTACT_UA).key == "sec_edgar_xbrl",
           "(C)")
check_raises("FRED without an API key is refused (MEASURED 400)",
             lambda: check_access("fred"), AccessError)
check_raises("FRED with a whitespace-only key is refused",
             lambda: check_access("fred", api_key="   "), AccessError)
check_true("FRED with a key is permitted",
           check_access("fred", api_key="k").key == "fred", "(C)")

# DEFECT: the first UA check was `"@" in user_agent`, which accepted "@",
# "me@" and "@example.com". A placeholder that passes the guard but reaches
# SEC as an unusable contact is worse than no guard: it converts a readable
# refusal into a 403 to diagnose.
for _bad_ua in ("@", "me@", "@example.com", " @ ", "a@b", "no-at-sign"):
    check_true("degenerate UA %r rejected" % _bad_ua,
               not _is_contact_ua(_bad_ua), "(D) placeholder contact")
for _good_ua in ("a@b.c", CONTACT_UA, "me@example.com trailing"):
    check_true("real contact UA %r accepted" % _good_ua,
               _is_contact_ua(_good_ua), "(C) boundary, other side")

# --- descoped sources must not leak through any door ------------------------
check_raises("codal is refused (Phase 0 Q3 descope)",
             lambda: check_access("codal", user_agent=CONTACT_UA), AccessError)
check_raises("tsetmc is refused (Phase 0 Q3 descope)",
             lambda: check_access("tsetmc", user_agent=CONTACT_UA), AccessError)
check_true("codal absent from enabled_sources",
           not any(s.key == "codal" for s in enabled_sources()), "(C)")
check_true("codal STILL listed in the manifest (decision stays visible)",
           any(d["key"] == "codal" for d in manifest()["sources"]),
           "(C) descoped is not the same as forgotten")
check("manifest counts account for every source",
      manifest()["n_enabled"] + manifest()["n_descoped"], len(SOURCES), 0,
      "(C) no source falls between the two lists")
check_raises("an unregistered source is refused",
             lambda: get_source("bloomberg"))

# --- DEFECT: source terms were mutable at runtime ---------------------------
# One line re-enabled a source the user descoped:
#     SOURCES["codal"].enabled = True   -> check_access("codal") passed.
# The same line could drop requires_contact_ua, or set trust_level to a string
# that is not a trust level, at which point .authority raised KeyError -- a
# crash, not a refusal.
check_raises("cannot re-enable a descoped source",
             lambda: setattr(SOURCES["codal"], "enabled", True))
check_raises("cannot drop the contact-UA requirement",
             lambda: setattr(SOURCES["sec_edgar_xbrl"],
                             "requires_contact_ua", False))
check_raises("cannot inflate a source's trust level",
             lambda: setattr(SOURCES["fred"], "trust_level",
                             "VERIFIED_PRIMARY"))
check_raises("cannot delete a term",
             lambda: delattr(SOURCES["fred"], "requires_api_key"))
# operator.setitem, not SOURCES.__setitem__: a mappingproxy has no
# __setitem__ attribute at all, so calling it directly raises AttributeError
# -- a crash, which the harness correctly refused to accept as a refusal. Real
# subscript assignment is what a caller would write, and it raises TypeError.
check_raises("cannot inject a source through SOURCES[...] = ...",
             lambda: operator.setitem(
                 SOURCES, "blog",
                 Source("blog", "B", "u", "VERIFIED_PRIMARY")),
             TypeError)
check_raises("cannot silently replace a registered source's terms",
             lambda: register_source(Source("fred", "F", "u", "UNVERIFIED")))
check_raises("register_source refuses a non-Source",
             lambda: register_source({"key": "x"}), TypeError)
check_raises("a bad trust level is refused at construction",
             lambda: Source("x", "X", "u", "NOT_A_LEVEL"))
check_raises("a disabled source with no recorded reason is refused",
             lambda: Source("z", "Z", "u", "EXCHANGE", enabled=False))
check_true("authority is read from the trust table",
           SOURCES["sec_edgar_xbrl"].authority == 100
           and SOURCES["fred"].authority == 90, "(B)")


# ---------------------------------------------------------------------------
section("ingestion is gated by the registry, not by the caller's goodwill")
# ---------------------------------------------------------------------------
# Before this wiring, sources.py DECLARED the terms and nothing called it.
# The acceptance criterion is "restricted data handled correctly", which a
# declaration alone cannot satisfy.

_GATED = ("CONSOLIDATED STATEMENTS OF OPERATIONS\n(in millions)\n\n"
          "Net sales ......................... 109,417\n")

check_raises("ingestion without a contact UA is refused",
             lambda: ingest_document(_GATED, "sec_edgar_submissions", "d"),
             AccessError)
check("ingestion with a contact UA proceeds",
      len(ingest_document(_GATED, "sec_edgar_submissions", "d",
                         user_agent=CONTACT_UA)), 2, 0, "(C)")
check_raises("ingestion from a descoped source is refused",
             lambda: ingest_document(_GATED, "codal", "d",
                                     user_agent=CONTACT_UA), AccessError)
check_raises("ingestion from an unregistered source is refused",
             lambda: ingest_document(_GATED, "bloomberg", "d",
                                     user_agent=CONTACT_UA))

# Trust level is a property of the SOURCE, never an argument. Otherwise a
# caller could claim VERIFIED_PRIMARY for a blog and outrank a real filing.
check_raises("provenance_for refuses a caller-supplied trust_level",
             lambda: provenance_for("fred", api_key="k",
                                    trust_level="VERIFIED_PRIMARY"))
check_raises("provenance_for refuses a caller-supplied licence",
             lambda: provenance_for("fred", api_key="k", licence="mine"))
check_true("provenance_for reads trust level from the registry",
           provenance_for("fred", api_key="k").trust_level == "OFFICIAL_DATA",
           "(C) single source of truth")
check_raises("a passage may not claim authority its source lacks",
             lambda: ingest_document(
                 _GATED, "sec_edgar_submissions", "d", user_agent=CONTACT_UA,
                 provenance=Provenance(source="x",
                                       trust_level="PERMITTED_NEWS")))
check_true("a matching provenance is accepted",
           len(ingest_document(_GATED, "sec_edgar_submissions", "d",
                               user_agent=CONTACT_UA, provenance=PROV)) == 2,
           "(C) the guard checks the level, not identity")

# MUTATION SURVIVOR: replacing check_access() with get_source() inside
# ingest_document left the suite green, because every gating assertion above
# happens to pass provenance=None -- and the None branch calls provenance_for,
# which checks access again downstream. So the gate was only ever tested on the
# path that re-checks it, never on the path a real caller uses. A filing always
# arrives WITH provenance (it has an accession and a filing date), so the
# untested path was the normal one. These assert the gate on that path.
check_raises("access is checked even when provenance is supplied",
             lambda: ingest_document(_GATED, "sec_edgar_submissions", "d",
                                     provenance=PROV), AccessError)
check_raises("a descoped source is refused even with valid provenance",
             lambda: ingest_document(
                 _GATED, "codal", "d", user_agent=CONTACT_UA,
                 provenance=Provenance(source="Codal",
                                       trust_level="VERIFIED_PRIMARY")),
             AccessError)
check_true("gated ingestion still preserves the scale note",
           all(p.units_note == "millions" for p in
               ingest_document(_GATED, "sec_edgar_submissions", "d",
                               user_agent=CONTACT_UA)),
           "(C) the gate did not break the scale chain")

if os.path.exists(_XBRL):
    check_raises("XBRL facts are refused without a contact UA",
                 lambda: facts_from_xbrl_companyconcept(_payload),
                 AccessError)
    check_raises("XBRL facts are refused for a descoped source",
                 lambda: facts_from_xbrl_companyconcept(
                     _payload, source_key="codal", user_agent=CONTACT_UA),
                 AccessError)
    _gf = facts_from_xbrl_companyconcept(_payload, user_agent=CONTACT_UA)
    check_true("XBRL provenance names the registered source",
               _gf[0].provenance.source == SOURCES["sec_edgar_xbrl"].name,
               "(C) licence text no longer duplicated in ingest.py")
    check_true("XBRL licence comes from the registry",
               _gf[0].provenance.licence == SOURCES["sec_edgar_xbrl"].licence,
               "(C) cannot drift from the declared terms")

    # MUTATION SURVIVOR -- the "factor equals 1" blind spot, a fourth time.
    # Re-hardcoding trust_level="VERIFIED_PRIMARY" in the XBRL path survived,
    # because sec_edgar_xbrl IS VERIFIED_PRIMARY: the mutation was a no-op
    # under the only source these tests exercised. Asserting the value against
    # the registry cannot distinguish "read from the registry" from "happens to
    # match". So ingest the same payload under a source whose registered level
    # DIFFERS, where the two answers diverge.
    _lf = facts_from_xbrl_companyconcept(_payload, source_key="fred",
                                         api_key="k")
    check_true("trust level follows the SOURCE, not a hardcoded constant",
               _lf[0].provenance.trust_level == "OFFICIAL_DATA",
               "(C) differs from VERIFIED_PRIMARY, so a constant cannot pass")
    check_true("licence follows the SOURCE, not a hardcoded string",
               _lf[0].provenance.licence == SOURCES["fred"].licence
               != SOURCES["sec_edgar_xbrl"].licence,
               "(C) the two registered licences differ")


# ---------------------------------------------------------------------------
section("TradingView: display-only, enforced rather than documented")
# ---------------------------------------------------------------------------
# SS.7 requires the terms to be verified at execution time. They were, by live
# probe on 2026-08-12, and the finding was not ambiguity: TradingView licenses
# its content for "exclusive display-only use" and "explicitly prohibits any
# form of non-display usage", naming automated trading, price referencing, order
# verification, algorithmic decision-making, smart order routing and "risk
# management programs" -- and naming charts, alerts and webhooks specifically.
#
# So these assertions test a WALL, not a feature. Each one is a route by which a
# TradingView number could reach a calculation.

check_true("machine use is not permitted", tv.MACHINE_USE_PERMITTED is False,
           "(V) Terms of Use s3, probed 2026-08-12")
check("no mechanism is machine-usable", len(tv.machine_usable_mechanisms()), 0, 0,
      "(C) 7 mechanisms verified to exist; none usable for data")
check("7 mechanisms inventoried", len(tv.MECHANISMS), 7, 0, "(V) all HTTP 200")

# The acceptance criterion "no unsupported Desktop API claimed" -- as an assertion,
# because a criterion nothing tests is a hope.
check_true("desktop app is recorded as existing but with no local API",
           tv.get_mechanism("desktop_app").exists is True
           and "NO LOCAL API IS DOCUMENTED" in tv.get_mechanism("desktop_app").note,
           "(V) probed: localhost x0, 'local API' x0, plugin x0, automation x0")
check_true("broker REST API is recorded as INBOUND to the broker",
           "INBOUND" in tv.get_mechanism("broker_rest_api").direction,
           "(V) 'lets brokers connect their backend systems to the TradingView "
           "interface' -- we are not a broker")

# Every machine purpose must be refused. Not warned about -- refused.
for _purpose in ("automated trading", "price referencing", "order verification",
                 "algorithmic decision-making", "smart order routing",
                 "risk management", "persisting a quote as a fact"):
    check_raises("refused for %r" % _purpose,
                 lambda p=_purpose: tv.assert_display_only_use(p),
                 tv.TradingViewLicenceError)

# There must be no override. An override is the first thing reached for under
# deadline, and the terms admit no exception this project can satisfy.
check_raises("no permit= escape hatch",
             lambda: tv.assert_display_only_use("automated trading", permit=True),
             TypeError)
check_raises("an unlabelled refusal is itself refused",
             lambda: tv.assert_display_only_use(""))

# The wall must not consult mutable state. PROBED: rebinding the module globals
# does not open it, because assert_display_only_use always raises rather than
# looking anything up. Asserted here so a future "optimisation" that adds a
# lookup gets caught.
def _flip_and_retry():
    _saved_flag, _saved_list = tv.MACHINE_USE_PERMITTED, tv.PROHIBITED_USES
    tv.MACHINE_USE_PERMITTED, tv.PROHIBITED_USES = True, ()
    try:
        tv.assert_display_only_use("automated trading")
    finally:
        tv.MACHINE_USE_PERMITTED, tv.PROHIBITED_USES = _saved_flag, _saved_list


check_raises("flipping MACHINE_USE_PERMITTED and emptying PROHIBITED_USES "
             "does not open the wall", _flip_and_retry,
             tv.TradingViewLicenceError)

# Capability records must be immutable, for the reason Phase 3 established: one
# line would otherwise undo the module.
check_raises("cannot mark a mechanism machine-usable at runtime",
             lambda: setattr(tv.MECHANISMS["webhooks"],
                             "usable_for_machine_data", True))
check_raises("cannot delete a mechanism's verdict",
             lambda: delattr(tv.MECHANISMS["webhooks"],
                             "usable_for_machine_data"))
check_raises("cannot inject a mechanism through MECHANISMS[...]",
             lambda: operator.setitem(tv.MECHANISMS, "x", None))
check_raises("cannot CONSTRUCT a mechanism claiming machine usability",
             lambda: tv.Mechanism("x", "X", True, "outbound",
                                  usable_for_machine_data=True, note="fine"))
check_raises("cannot register a mechanism with no stated reason",
             lambda: tv.Mechanism("x", "X", True, "outbound", False, note=""))
check_raises("cannot overwrite a verified mechanism record",
             lambda: tv._add(tv.Mechanism("webhooks", "v2", True, "out", False,
                                          "replaced")))
# MUTATION SURVIVOR: removing _add's isinstance guard survived, because this
# assertion existed only in probe_tradingview.py and the battery runs the SUITE.
# A probe I ran by hand once is not a regression test. Without the guard a dict
# reaches `mech.key` and raises AttributeError -- a CRASH, which the strengthened
# harness correctly reports as a failure rather than accepting as a refusal.
check_raises("_add refuses an object that is not a Mechanism",
             lambda: tv._add({"key": "fake", "usable_for_machine_data": True}))
check_raises("an unknown mechanism is not assumed permitted",
             lambda: tv.get_mechanism("desktop_local_api"))

# Tuples, not lists: the prohibited-use list must not be editable in place.
check_raises("PROHIBITED_USES is not editable in place",
             lambda: operator.setitem(tv.PROHIBITED_USES, 0, "fine"), TypeError)
check_raises("PERMITTED_USES is not editable in place",
             lambda: operator.setitem(tv.PERMITTED_USES, 0,
                                      "automated trading"), TypeError)

# --- and the registry-level block, which is what actually stops ingestion -----
check_raises("check_access('tradingview') is refused",
             lambda: check_access("tradingview", user_agent=CONTACT_UA),
             AccessError)
check_raises("ingesting a TradingView document is refused",
             lambda: ingest_document("AAPL 250.10", "tradingview", "tv1",
                                     user_agent=CONTACT_UA), AccessError)
check_raises("building TradingView provenance is refused",
             lambda: provenance_for("tradingview", user_agent=CONTACT_UA),
             AccessError)
check_true("the refusal names the licence, not a scope decision",
           "PROHIBITED BY LICENCE" in SOURCES["tradingview"].descope_reason,
           "(C) distinguishes it from the Q3 scope descope of Codal/TSETMC")
check_true("TradingView carries no borrowed authority",
           SOURCES["tradingview"].authority == 0,
           "(C) UNVERIFIED -- a licence refusal, not a quality judgement")

sys.exit(summary())
