# Maintenance (Phase 10, D-0128)

The maintenance routine is one command:

```
python3 tools/maintain.py                 # every check; prints a report
python3 tools/maintain.py --json out.json # also writes the report as JSON
```

Exit status: **0 OK**, **1 DUE** (warnings), **2 FAIL** (a CRITICAL finding). It never reaches the network. A check that
needs the network (re-probing a source, re-reading a terms page) reports **DUE, NOT probed**; it never reports OK.
Response to each status: `docs/incident-response.md`.

## Policy (`configs/maintenance-policy.json`)

| Key | Value | Meaning |
|---|---|---|
| `source_reverify_days` | 90 | an enabled source must be re-verified at least this often |
| `legal_review_days` | 120 | each `docs/legal/*` review must be redone at least this often |
| `corpus_filing_max_age_days` | 550 | the newest filing in the corpus older than this is a warning |
| `dependency_review_days` | 90 | each entry in `releases/dependencies.lock.json` must be reviewed at least this often |
| `risk_policy_review_days` | 90 | `configs/risk-policy.json` must be reviewed at least this often |
| `benchmark_max_age_days` | 60 | the release benchmark must be re-measured on the target at least this often |
| `reconciliation_interval_minutes` | 15 | paper engine: reconcile every 15 minutes while orders exist |
| `reconciliation_overdue_factor` | 2.0 | over 15 × 2 = 30 minutes since the last reconcile is a warning |

Each limit is inclusive: exactly 90 days is still OK.

## Schedule (SS.24 Phase 10 tasks)

| Task | When | How |
|---|---|---|
| Regression tests | before every release; after any dependency change; after any edit to a pinned file | `bash tests/run_all.sh --mutate` (must be ALL GREEN with 0 skipped, 0 survivors; run it from a committed tree) |
| Source refresh | every 90 days per source | re-run the probe recorded in each source's `verified_status` (TradingView: `tools/verify_tradingview_terms.py`); then update `verified_on` in `src/rag/sources.py` |
| Index update | whenever the corpus changes | RAG suite and battery green, then `--record-index` |
| Benchmark refresh | every 60 days; after a model, prompt or runtime change | on the i5-12400: `PHASE8_CONFIRM_RUN_FA.md`, then `--record-baseline` from the new verdict |
| Stale-data alerts | on every quote used | `monitor.check_quotes` (limit `max_quote_age_s` = 5 s; END_OF_DAY/DELAYED always flagged) |
| Dependency monitoring | every 90 days | `pip show` on the target; update `releases/dependencies.lock.json` (llama-cpp-python's version is recorded only there) |
| Licence monitoring | every 120 days; on any registry change | `python3 tools/build_licenses.py > LICENSES.md`; re-review `docs/legal/*` |
| Versioning | every behaviour change | bump `VERSION`, then `--release` (see below) |
| Rollback | on a SEV-1/SEV-2 caused by the build | `--rollback <version>` |
| Incident response | on any exit 2 | `docs/incident-response.md` |
| Broker reconciliation | every 15 min while paper orders exist | `eng.reconcile()`; check it with `--audit <state_dir>` |
| Risk-policy review | every 90 days | edit `configs/risk-policy.json`; only a human may set `human_approved: true` |

## Versioning and rollback

- `VERSION` is MAJOR.MINOR.PATCH. A change to the model sha, the prompt options or the inference settings needs at
  least a **minor** bump, because results are not comparable across it. A change only to pinned files needs a
  **patch** bump.
- `--release` writes `releases/<VERSION>.json`. It pins the sha256 of every file in `release.PINNED_FILES`, along with
  the model sha, the prompt options, the inference settings and the benchmark baseline. Manifests are **immutable**.
  `--release` refuses an existing version, a version lower than the newest release, a bump that is too small, and a
  release when nothing has changed. Commit the manifest **in the same commit** as the files it pins. The manifest
  holds no commit hash, because squashes rewrite hashes; rollback finds the commit that added the manifest from git
  history.
- `--verify <version>` compares the working tree with a release. `--model <gguf>` checks the model file as well.
- `--rollback <version>` prints `git checkout <commit> -- <files>` for exactly the files that differ. It refuses an
  unknown release, a release whose commit cannot be found, and a model on disk that is not that release's model.
- The routine report also says whether the tree still matches the newest release. A pinned file edited without a new
  release is a warning.

## Recorded state (`releases/`)

- `--record-index` writes `index-manifest.json`: the corpus sha256, the passage count and the document ids.
- `--record-baseline` writes `benchmark-baseline.json` from the current Phase 7 verdict.
- `dependencies.lock.json` holds the reviewed versions.
- `0.10.0.json` is the first release.
