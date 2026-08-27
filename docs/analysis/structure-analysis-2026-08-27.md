# marfin-llm — Structure & Dependency Analysis

**Label: MEASURED_STATIC_AST** · Date: 2026-08-27 · Tool: `tools/graph_project.py`
Reproduce with: `python3 tools/graph_project.py --json /tmp/graph.json`

Every number in this document was produced by running the tool on the tree.
Nothing here is ESTIMATED. Where the tool cannot resolve something, this
document says so instead of filling the gap.

---

## 0. Why this tool and not graphify itself

Request 40 asked that the graphify repository be used to understand and graph
marfin-llm. It was cloned (depth 1, branch `v8`, Apache-2.0, 337 `.py` files)
and read. Then MEASURED:

- `graphify.extract.extract()` raises immediately:
  `ImportError: tree-sitter is not installed. Run: pip install 'tree-sitter>=0.23.0'`
  (raised at `graphify/extract.py:4290`)
- Its dependency set is `networkx>=3.4` (present), `numpy`, `rapidfuzz`, and
  ~27 tree-sitter grammars (absent).
- marfin-llm is **89 `.py` files and nothing else that is source**. Stdlib
  `ast` parses all of `src/` with **zero** failures.

graphify's value is breadth — one tool that reads 27 languages. marfin-llm
needs exactly one of those 27. Installing ~30 packages plus a native
toolchain to gain 26 unused languages is the wrong trade on a machine that
must stay reproducible, so this tool takes graphify's **ideas** and implements
them against `ast`, which is already present.

**Borrowed from graphify, deliberately:**

1. **Pipeline shape** — `detect → extract → build → cluster → analyze → report`.
2. **Confidence labels on every edge** — `EXTRACTED` / `INFERRED` /
   `AMBIGUOUS`, with AMBIGUOUS surfaced for human review. This parallels
   marfin-llm's own VERIFIED/MEASURED/COMPUTED/ESTIMATED/UNKNOWN convention:
   a call graph built from names is full of guesses, and a graph that hides
   which edges are guesses is worse than no graph.
3. **Node schema** — `{id, label, source_file, source_location}`.

---

## 1. Headline measurements

| Quantity | Value |
|---|---|
| modules analysed | 91 |
| nodes (module / function / class) | 728 |
| edges (imports + calls) | 7,724 |
| **parse errors** | **0** |
| import edges | 530 |
| internal import edges (ours → ours) | 164 |
| **import cycles** | **none** |

`parse errors 0` matters twice: it is the evidence that the `ast` route is
sufficient for this tree, and it means no module was silently skipped — a
skipped module would make every figure below an undercount.

### Edge confidence

| Label | Count | Share |
|---|---|---|
| EXTRACTED | 1,902 | 24.6 % |
| INFERRED | 1,958 | 25.3 % |
| AMBIGUOUS | 3,864 | 50.0 % |

**Half of all call edges are AMBIGUOUS, and that is an honest result, not a
tool defect.** An AMBIGUOUS edge means the called name is defined in more than
one module, so a static reader cannot say which definition a call reaches.
The tool records `?:<name>` rather than picking a winner.

The dominant cause is MEASURED and benign: the test tree defines the same
assertion helpers in many suites. `check`, `check_true`, `check_raises`,
`section`, `summary`, `_strip_escapes`, `_utc_now`, `fixture` and similar
names recur across 44 test modules. VERIFIED example: `check` is genuinely
defined twice — `tests/_harness.py:42` and `tests/test_returns_risk.py:32`.

**Do not read the 50 % as "half the codebase is unclear."** Restricted to
imports — where the AST gives a real answer — resolution is complete: 530
import edges, 0 parse failures, 0 unresolved-but-matchable targets remaining.

---

## 2. Most depended-on modules (fan-in)

A defect here reaches furthest, so this is where test effort belongs.

| Module | fan-in | fan-out | LOC |
|---|---|---|---|
| `tests._harness` | **16** | 0 | 115 |
| `rag.documents` | 15 | 0 | 396 |
| `market.quotes` | 11 | 1 | 798 |
| `market` (package init) | 9 | 0 | 1 |
| `rag.ingest` | 8 | 2 | 480 |
| `calc` (package init) | 7 | 0 | 1 |
| `rag.retrieval` | 7 | 2 | 351 |
| `llm.providers` | 6 | 0 | 416 |
| `execution.mode` | 5 | 0 | 484 |
| `llm` (package init) | 5 | 0 | 2 |

**Reading of the shape:** the high-fan-in modules almost all have fan-out 0 or
1. They are leaves that everything depends on and that depend on nothing.
That is the healthy direction for a dependency graph — combined with **zero
import cycles**, it means the layering holds in practice and not just on the
architecture diagram.

`market.quotes` at 798 LOC with fan-in 11 is the largest high-traffic module
and the most reasonable future split candidate. Recorded as an observation,
**not** proposed as a change: it is currently covered and not failing, and
refactoring a module 11 others depend on is not free.

---

## 3. The finding that changed the work: the harness was untested

The graph put `tests._harness` at the **top** of the fan-in table — 16 suites
import it. VERIFIED by import statement, not by mention:

- files with a real `from _harness import` / `import _harness` statement: **16**
- files merely *mentioning* `_harness` in comments or docstrings: 21

The 5-file gap is `mutate_phase4.py`, `probe_alpha_vantage.py`,
`probe_csv_import.py`, `probe_quotes.py`, `probe_tradingview.py`. An earlier
`grep -l` count of "21 suites" was wrong for exactly the reason this project
has already recorded once: **a source-text match cannot distinguish "uses it"
from "mentions it."** The graph's 16 is correct; the expectation was not.

Then the important part. MEASURED: `tests/_harness.py` has **no test of its
own and no mutation battery**, while 11 other modules do have batteries
(`alpha_vantage`, `broker_tools`, `csv_import`, `execution`, `llm_providers`,
`market`, `phase4`, `rag`, `screenshot`, `selector`, `webhooks`).

If the harness could pass falsely, all 16 suites — and the 3,006 assertions
they carry — would report green wrongly. So it was probed directly:

| Probe | Result |
|---|---|
| `check(1.0, 1.0)` correct-equal | pass=1 fail=0 ✅ |
| `check(1.0, 2.0)` must fail | pass=0 fail=1 ✅ |
| **`check(nan, nan)`** — the classic false-pass trap | **pass=0 fail=1 ✅** |
| `check(inf, inf)` | pass=0 fail=1 (conservative) |
| `check(True, 1)` | pass=1 fail=0 (type-blind) |
| `check_true("anything")` | pass=1 fail=0 ✅ |
| `check_true(0)` must fail | pass=0 fail=1 ✅ |
| **`check_raises(fn that does not raise)`** | **pass=0 fail=1 ✅** |

**Verdict: no false-pass mode found.** The two traps that would have
invalidated the whole suite base — `nan == nan` silently passing, and
`check_raises` passing when nothing raises — both correctly FAIL. The
assertion base is trustworthy.

Two traits recorded for future readers:

- `check(True, 1)` **passes** — the comparison is numeric and type-blind.
  `True == 1` in Python, so this is consistent, but it means `check` must not
  be used to assert a value's *type*. This is exactly why
  `tests/test_console.py` carries its own `check_is`, which compares
  `type(got) is type(want)`.
- `check(inf, inf)` **fails**. It errs toward reporting a defect rather than
  hiding one, which is the correct direction for this project.

---

## 4. Defect found and fixed in the tool itself, by its own first run

The tool's first run reported `tests._harness` as a module with **no internal
edges** — i.e. as a possible dead file. That is plainly false for a module 16
suites import, so the tool was audited before any of its numbers were
believed.

**Root cause.** `from _harness import check` names the module `_harness`,
while the tool ids that same file as `tests._harness` (only `src/` is stripped
from the path). `build()` keeps an edge only when `target in ours`, so every
such edge was silently DISCARDED.

**Scale, MEASURED before fixing:** 530 import edges, **17 recoverable**,
exactly two distinct targets — `_harness` and `phase4_lib`.

**Why the fix is legitimate rather than convenient.** Those modules are
imported as bare top-level names only because the importing files put their
own directory on `sys.path` first. VERIFIED at `tests/test_console.py:40`:

```python
sys.path.insert(0, os.path.dirname(__file__))
```

So a bare `_harness` inside `tests/` genuinely *is* `tests/_harness.py`.
It remains an assumption about `sys.path` rather than something read off the
AST, so **every edge resolved this way is labelled `INFERRED`, never
`EXTRACTED`.**

Two forms had to be covered, not one. `import phase4_lib as L` (a plain
`ast.Import`, VERIFIED at `scripts/run_phase4.py:67` and
`tests/test_phase4_harness.py:111`) needed the same treatment as
`from ... import ...`. A cross-package fallback handles the case where a file
adds *another* directory to the path — VERIFIED at
`tests/test_phase4_harness.py:104-107`, which adds both `src/` and `scripts/`.
That fallback fires **only when exactly one module in the tree has that
basename**; with two candidates it returns unresolved, because a graph that
guesses which of two modules an edge reaches is worse than one that admits it
does not know.

**Post-fix verification** (all conditions required simultaneously):

| Check | Result |
|---|---|
| import edges total | 530 — **unchanged**, nothing invented |
| `tests._harness` fan-in | 0 → **16** (correct) |
| `scripts.phase4_lib` fan-in | 1 → **2** (correct) |
| self-edges introduced | **0** |
| `llm.providers` fan-in | 6 → **6** (no regression) |
| import cycles | still **none** |
| `tests._harness` in orphan list | **removed** |

Node count moved 727 → 728 and edges 7,722 → 7,724. That delta is accounted
for exactly: the new `_resolve_sibling` function plus its 2 call sites, since
the tool analyses `tools/` including itself. No unexplained drift.

---

## 5. Clusters

| Cluster | Modules |
|---|---|
| `tests` | 44 |
| `rag` | 10 |
| `scripts` | 9 |
| `calc` | 7 |
| `market` | 7 |
| `llm` | 5 |
| `tools` | 5 |
| `execution` | 4 |

44 of 91 modules — **48 %** — are tests. For a project whose governing rule is
that a passing suite proves nothing without mutation testing, a roughly 1:1
test-to-source ratio is the expected shape rather than a surprise.

---

## 6. Modules with no internal edges

The tool lists these without classifying them, because **it cannot tell an
entry point from dead code and must not guess**:

`scripts.estimate_model_footprint`, `scripts.measure_tokenizer_efficiency`,
`scripts.merge_phase4`, `scripts.run_baseline`, `scripts.size_from_config`,
`scripts.throughput_ceiling`, `tests.mutate_*` (11 modules), and 5 more.

Inspected by category:

- The `scripts.*` entries are **command-line entry points**, run by the user
  directly. Zero fan-in is correct for them, not suspicious.
- The `tests.mutate_*` entries are **mutation batteries**. They deliberately
  drive their targets through `subprocess`, not through imports, so an
  import-graph reader cannot see their edges. Also correct.

**No dead code was identified.** Stated plainly because the honest answer to
"is any of this dead?" here is *no evidence of any*, and inventing a cleanup
task would be worse than reporting nothing.

---

## 7. What this analysis does NOT establish

- It is **static**. It says nothing about runtime behaviour, performance, or
  correctness. It cannot be used to argue any Phase 4 threshold.
- The **50 % AMBIGUOUS** call edges are unresolved by design. Any claim that
  depends on a specific call target must be verified against the source.
- It does not change `phase_4/measurements_recorded`, which remains `None`.
- The dynamic-import blind spot is real: `tests.mutate_*` reach their targets
  via `subprocess`, and no import-graph tool will show those edges.

---

## 8. Actions taken from this analysis

1. **Fixed** the sibling-import resolution defect in `tools/graph_project.py`
   (17 lost edges recovered, all labelled `INFERRED`).
2. **Probed the harness** that 16 suites depend on and established it has no
   false-pass mode — the single most load-bearing untested module in the tree.
3. **Recorded** `check`'s type-blindness as the standing reason
   `tests/test_console.py` needs its own `check_is`.
4. **Confirmed** zero import cycles and a leaf-shaped dependency graph.
5. **Declined** to propose a `market.quotes` split or any dead-code cleanup,
   because the evidence supports neither.
