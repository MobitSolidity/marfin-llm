# Phase 9 Review — Documentation and Model Card

Date: 2026-10-20 · D-0127 (under the D-0126 delegation) · Labels: (V) VERIFIED · (M) MEASURED · (C) COMPUTED · (E) ESTIMATED

## Status: **PASS**: all 9 SS.24 tasks delivered; every documented claim is checked against code or evidence

| SS.24 task | Deliverable |
|---|---|
| Finalize README | `README.md`: contents, phase status, and a licence section that states the truth (no project licence chosen) |
| Architecture docs | `docs/architecture.md` |
| License registry | `LICENSES.md`, **generated** from `rag.sources` and `market.quotes` by `tools/build_licenses.py`; a test fails on drift |
| Deployment docs | `docs/deployment.md` (checksum, venv, recommended run line, alternatives, mode config); `requirements.txt`; `.env.example` |
| TradingView limitations | `docs/tradingview-integration.md` |
| Broker safety documentation | `docs/execution-safety.md` |
| Model Card | `MODEL_CARD.md`: all 31 SS.23 fields |
| Known failures | `docs/known-failures.md` (12 rows, each with evidence) |
| Error reporting | `docs/error-reporting.md` |

## Acceptance (SS.24)
| Criterion | Result |
|---|---|
| New user can install and run | `docs/deployment.md`. Every flag it names is checked to exist in `run_phase4` (V), and the checksum and Modelfile are checked (V). **Not yet executed by a new user**: that needs the target machine. |
| Licences recorded | `LICENSES.md`: model, 6 dependencies, 15 data sources, 4 market-data providers. The project-code licence is recorded as **not chosen**. |
| Measured and estimated separated | Every number in the model card carries a label, and its source file is cited and checked by tests |
| Limitations explicit | `docs/known-failures.md`; model card "Failure cases" |

## How the docs are kept true

`tests/test_phase9.py` (72 checks) and `tests/mutate_phase9.py` (16/16 killed) check:
- the checksum, size, revision, parameter count and chat-template hash, against the GGUF evidence;
- 8 benchmark values and verdicts, against the Phase 7 verdict file;
- counts against the live code: tools (85), SS.6.1 unmet (10 of 12), paper checks (17), webhook validations (16),
  order states (12), preview fields (10);
- every flag named in a document exists in `run_phase4`;
- `.env.example` names every key the code reads and contains no values;
- `src/` is stdlib-only;
- every third-party import is in both `LICENSES.md` and `requirements.txt`.

**Defects found by the battery:** 2 first-pass survivors, both fixed.
1. The SS.23 field check matched words anywhere in the text. It now requires a table-row key or a heading.
2. A commented-out requirement still counted as present. Only active lines count now.
