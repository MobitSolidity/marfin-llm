# Phase 3 Review — Data Pipeline and Financial RAG

Project: marfin-llm
Date: 2026-08-12
Prompt version governing this phase: SYSTEM_PROMPT.md v2.0
Active mode: `ANALYSIS_ONLY` · Live trading: `DISABLED` · TV connector level: 0

---

## Status

**PASS** — all five §24 Phase 3 acceptance criteria met, each demonstrated by a
test that fails when the behaviour is removed.

One thing to be clear about before anything else: the headline number below is
not "739 tests pass." A passing suite proves nothing on its own. The number that
carries the claim is **151 seeded defects, 0 survivors** — every guard described
in this report was deliberately broken, and the suite caught it.

---

## 1. Acceptance criteria, and what demonstrates each

| Criterion (§24) | Demonstrated by | Result |
|---|---|---|
| Provenance traceable | `Passage`/`Fact` refuse construction without `Provenance`; every fact keeps its own accession + filing date | PASS |
| Restricted data handled correctly | `check_access()` gates every ingestion entry point; Codal/TSETMC refused; contact-UA and API-key terms enforced | PASS |
| Dates, currency, scale preserved | Structure-aware chunking propagates the scale note; tables are never split; unresolved scale is flagged | PASS |
| Citations returned | `verify_claim` matches claim magnitudes against evidence at the claim's own stated precision | PASS |
| Retrieval failure causes abstention | `answer_gate` — no path returns `may_answer=True` without evidence that survived resolution, trust floor, staleness and verification | PASS |

---

## 2. What was built

Nine modules, stdlib only, under `src/rag/`:

| Module | Responsibility |
|---|---|
| `documents.py` | `Provenance` / `Fact` / `Passage` / `Document`; trust levels; period classification |
| `sources.py` | Source registry; access terms as enforceable data; `check_access()` |
| `normalize.py` | Bilingual fold/tokenize; Persian compound variants; `index_terms()` |
| `ingest.py` | Structure-aware chunking; scale/currency capture; gated entry points |
| `retrieval.py` | BM25 lexical index + structured fact store + hybrid façade |
| `rerank.py` | Feature-based reranking (lexical, authority, recency, units, table) |
| `citations.py` | Claim-level numeric verification at the claim's own precision |
| `conflicts.py` | Period mixing, restatement supersession, staleness |
| `answer.py` | The abstention gate |

### Capability labelling (§0B — honest naming)

- **"Hybrid retrieval" here means lexical BM25 + structured identity lookup.**
  It is **not** dense vector search. No embedding model exists on this machine,
  and `rag_vector_search` is listed as unavailable in the capability manifest.
- **"Reranking" is feature-based, not a cross-encoder.** It combines normalized
  lexical score with source authority, recency, units presence and table-ness.

Calling either of these by their more impressive names would misrepresent what
the system can do.

---

## 3. Hazards verified against live data (not assumed)

MEASURED on `data.sec.gov`, Apple `RevenueFromContractWithCustomerExcludingAssessedTax`:

| Hazard | Live finding |
|---|---|
| Period mixing | **One tag returns 117 facts**: 64 quarterly, 16 six-month, 16 nine-month, 21 annual. Averaging them silently is trivially easy. |
| Restatement | **46 periods reported by more than one filing.** Picking arbitrarily gives a superseded number that still cites a real filing. |
| Scale separation | EDGAR XBRL returns **raw units** (`109417000000`) where the filing text says "in millions" (`109417`). A 10⁶ discrepancy between two views of the same fact. |

Access terms, MEASURED 2026-08-10 and re-probed 2026-08-12:

| Source | Probe result |
|---|---|
| `data.sec.gov/submissions` | **200** with contact UA · **403** without |
| `data.sec.gov/api/xbrl` | **200** with contact UA |
| `api.stlouisfed.org/fred` | **400** "Variable api_key is not set" |
| `codal.ir`, `tsetmc.com` | Not probed — descoped (Phase 0 Q3) |

---

## 4. Defects found, and how

Nine real defects. None was found by writing a test I expected to pass; every
one came from attacking the module and seeing what it did.

**Ingestion**

1. **Silent total content loss.** `re.IGNORECASE` on the ALL-CAPS heading branch
   made lowercase prose match as a heading, so it was *consumed*: `passages: 0`,
   no error anywhere. The worst possible failure mode — a pipeline that
   confidently indexes nothing.
2. **Sibling headings nested.** List-slicing the section stack made peer
   headings parents of each other, corrupting the section paths that citations
   report.

**Normalization**

3. **Persian concatenated spelling never matched.** `ارزش‌گذاری` / `ارزش گذاری` /
   `ارزشگذاری` are all real. Folding ZWNJ→space reconciles only two of three;
   the third needs symmetric compound joining — kept out of `tokenize()` so BM25
   length normalization does not penalise Persian roughly 2×.

**Reranking**

4. **Min-max normalization made the reranker a no-op.** It maps the lowest score
   to 0 and the highest to 1 regardless of how close they were, amplifying a
   0.25% BM25 difference into the maximum possible gap. My own docstring had
   argued for the wrong choice. Now divide-by-max.

**Citations**

5. **Fixed 0.5% tolerance accepted a wrong number.** It admitted "109.5 billion"
   as support for 109.417. Replaced with half-ULP of the claim's *own* last
   stated digit: "109.4 billion" ⇒ ±0.05 B, "109,417 million" ⇒ ±0.5 M. No
   tuned constant.
6. **Unscaled-evidence asymmetry.** A bare table number rejected the *scaled*
   reading of a claim but **accepted** the unscaled one — silently assuming base
   units, which is precisely the 10⁶ error the module exists to prevent.

**Source terms** (all three found on the module's *first ever execution*)

7. **Terms were mutable at runtime.** One line re-enabled a source the user
   descoped: `SOURCES["codal"].enabled = True` → `check_access("codal")` passed.
   The same line could drop `requires_contact_ua`, or set `trust_level` to a
   string that is not a trust level, at which point `.authority` raised
   `KeyError` — a crash, not a refusal. Sources are now frozen after
   construction and the registry is handed out as a read-only mapping.
8. **The contact-UA check was a bare `"@"` substring test**, so `"@"`, `"me@"`
   and `"@example.com"` all passed. A placeholder that satisfies the guard and
   then earns a 403 anyway is worse than no guard: it converts a readable
   refusal into a network error to diagnose.
9. **The terms were declared but never enforced.** `sources.py` existed,
   `check_access()` existed, and **nothing called it**. Trust level and licence
   were *hardcoded* in `ingest.py`, free to drift from the registry, and any
   caller could hand in a `Provenance` claiming `VERIFIED_PRIMARY` for a blog.
   Trust level and licence are now read *from* the registry and may not be
   passed in at all.

Defect 9 is the one worth dwelling on: the acceptance criterion is "restricted
data handled correctly," and a module that documents the rules while nothing
calls it satisfies the wording and none of the intent.

---

## 5. Mutation testing — the part that carries the claim

151 defects seeded across three batteries; **0 survivors, 0 skips**.

| Battery | Seeded | Killed | Equivalent | Survived |
|---|---|---|---|---|
| calculation | 56 | 56 | 0 | 0 |
| selector | 15 | 15 | 0 | 0 |
| RAG | 80 | 77 | 3 | 0 |

The RAG battery surfaced **14 survivors across its runs** — every one a finding
about the *tests*, not the code. The instructive ones:

- **Ranking order cannot distinguish a weight from a tie-break.** With
  `W_AUTHORITY = 0` the filing still ranked first, because the sort's *secondary*
  key is also authority. Only asserting `components["authority"] > 0` kills it.
- **A crash is not a refusal.** `check_raises(..., exc=Exception)` accepted an
  incidental `AttributeError` thrown three frames deeper after a guard was
  deleted. This was **systemic: 106 of 113 assertions** across all eight suites
  relied on that default. Fixed at the harness, so every suite tightened at once.
- **A SKIP is not a PASS.** An ambiguous mutation pattern silently skipped and
  hid a real survivor. The battery now fails on any skip.
- **Sort stability is not determinism.** Repeating identical input proves
  nothing; a total order must survive *permuting* the input.
- **The "factor equals 1" blind spot, a fourth time.** Re-hardcoding
  `trust_level="VERIFIED_PRIMARY"` in the XBRL path survived — because
  `sec_edgar_xbrl` *is* `VERIFIED_PRIMARY`, so the mutation was a no-op under the
  only source the tests used. Killed by ingesting the same payload under a source
  whose registered level *differs*.
- **A gate tested only on the path that re-checks it downstream.** Replacing
  `check_access()` with `get_source()` in `ingest_document` survived, because
  every assertion happened to pass `provenance=None` — and that branch checks
  access again. Real filings always arrive *with* provenance, so the untested
  path was the normal one.

Three mutants are documented as **equivalent** in an explicit `EQUIVALENT` dict,
each naming the layer that already catches it, plus a `RECHECK` path that fires
if one ever starts dying — so "survived: 0" never becomes a number people learn
to ignore.

---

## 6. Separation of documents from time series

Structural, not cosmetic:

- `PassageIndex` holds text and is searched **lexically**; it has no
  period-identity query method.
- `FactStore` holds numeric observations and is queried by **identity only**
  (concept, entity, period kind, period end, currency); it has **no text search
  method at all**, verified by inspection.
- `HybridRetriever` returns the two channels under separate keys (`lexical`,
  `structured`), each tagged with its own `mode`, so a caller cannot silently
  treat a text match as a numeric fact.

This matters because scoring a numeric fact by text similarity is how a
retrieval system ends up "confident" about the wrong period.

---

## 7. Honest gaps

Stated plainly rather than left for a reader to notice:

1. **No dense vector retrieval.** Lexical + structured only (see §2).
2. **Two §5.2 source categories have no registered source**: *permitted
   research* and *permitted financial news*. `PERMITTED_RESEARCH` and
   `PERMITTED_NEWS` trust levels exist and are honoured by the trust floor, but
   nothing is registered under them, because no such source has had its terms
   verified. Registering one on the strength of a guess would defeat the purpose
   of the registry.
3. **FRED is UNVERIFIED end to end.** Reachability is MEASURED (400 without a
   key); no key has been supplied, so no successful fetch has been observed.
   Blocked on D-0007 (no credentials before a secret vault exists).
4. **Codal / TSETMC descoped, not evaluated.** Registered `enabled=False` with
   the Phase 0 Q3 reason recorded. Terms and sanctions status never verified.
5. **No live network fetching is implemented.** This phase ingests payloads and
   documents already in hand and gates them; an HTTP client with rate limiting
   belongs in Phase 3A alongside market data.
6. **Persian tested with constructed text, not real Iranian filings** — a
   consequence of (4). The bilingual normalization is verified against all three
   real ZWNJ spellings, but not against a genuine Codal document.
7. **No end-to-end run with a live model.** The RAG layer is deterministic and
   independently testable; whether the *model* respects the abstention gate is a
   Phase 2 carry-forward that needs the user's i5-12400 (R10).

---

## 8. Test state

```
test_returns_risk  57 | test_valuation 78 | test_technicals    81
test_fixed_income  69 | test_derivatives 92 | test_tools        99
test_selector      69 | test_rag       194
TOTAL: 739 assertions passed across 8 suites

mutation battery:          seeded 56, killed 56, survived 0, skipped 0
selector mutation battery: seeded 15, killed 15, survived 0, skipped 0
RAG mutation battery:      seeded 80, killed 77, equivalent 3, survived 0, skipped 0
ALL GREEN   EXIT=0
```

Reproduce: `./tests/run_all.sh --mutate`

---

## 9. Risks

**Closed**

- **R19 — source terms declared but unenforced.** Closed: `check_access()` gates
  every ingestion entry point; trust level and licence come from the registry.

**Open / carried forward**

- **R10** — Persian generation quality unmeasured (needs the i5-12400).
- **R17** — model-side tool selection accuracy (unmeasurable in this sandbox).
- **R18** — router keyword lists need maintenance as tools are added.
- **R20 (new, Medium)** — no source registered for *permitted research* /
  *permitted news*; those §5.2 categories are unserved until terms are verified.
- **R21 (new, Medium)** — the RAG layer has never run against a live model, so
  the abstention gate's *effect on generation* is untested.

**Q8** remains deferred until decode speed is measured on the target machine.

---

## 10. Phase 3A gate

Per §24, Phase 3 stops here for explicit approval. Phase 3A is **Market Data,
TradingView, and Broker Design**.

Nothing in Phase 3A has been started, and per §0/§1 nothing will be until
approval is given. Live trading remains `DISABLED` and is not self-enabling.
