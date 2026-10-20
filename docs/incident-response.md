# Incident response (Phase 10, D-0128)

Scope: the paper engine (`src/execution/paper.py`), the analysis assistant (model + RAG + tools), and the data/licence
surface. **There is no live trading.** Every `LIVE_PREREQUISITES` entry in `src/execution/mode.py` is False, so a live-money
incident cannot happen in this build. If something looks like one, treat it as SEV-1 and stop.

## Severities

| Severity | Meaning | Examples | Response |
|---|---|---|---|
| **SEV-1** | Wrong order, wrong ledger, or a licence breach, **now** | reconciliation mismatch; audit chain broken; `maintain.py` exit 2 on `reconciliation`, `licenses` or `risk_policy`; a PROHIBITED source enabled; anything that resembles a live order | Act immediately. Follow steps 1–6 in order. |
| **SEV-2** | Answers may be wrong | benchmark regression (a threshold went PASS → FAIL); corpus changed without re-recording; a source failed its re-probe | Same day. Stop relying on the affected output, roll back or re-record, then re-run the suite. |
| **SEV-3** | Due or drifting | `maintain.py` exit 1: a review overdue, a dependency version differs, a stale quote | Within the policy window (`docs/maintenance.md`). |

`python3 tools/maintain.py` maps onto these: exit 2 (FAIL, any CRITICAL) is SEV-1 or SEV-2 depending on which check
fired; exit 1 (DUE) is SEV-3; exit 0 is OK.

## SEV-1 runbook (paper engine)

1. **Engage the kill switch.** Any principal may do this. It is written to disk first (fail-closed: an unreadable
   kill-switch file counts as engaged) and is audited:
   ```python
   eng.kill.engage("HUMAN", "incident: <one line>")
   ```
   A failed reconciliation already does this automatically (principal `AUTOMATION`).
2. **Verify the audit log.** It is hash-chained; an edited, deleted or reordered line breaks the chain.
   ```
   python3 tools/maintain.py --audit <state_dir>      # CRITICAL "audit chain broken" if tampered
   ```
   If it is broken, **do not append to it**: `AuditLog` refuses to open a broken chain. Copy the state directory
   aside as evidence and start a new one.
3. **Reconcile.** `eng.reconcile()` resolves UNKNOWN orders from the venue, then compares positions, filled
   quantities and cash. Its `problems` list is the incident record. An order is never assumed to be filled or failed:
   only the venue decides its terminal state.
4. **Find the cause.** Look at the audit records around the first problem (`AuditLog(path).records()`) and the
   release in force (`python3 tools/maintain.py --verify <version>`). If pinned files differ from the release, the
   build is not the one that was tested.
5. **Roll back if the build is at fault.**
   ```
   python3 tools/maintain.py --rollback <version> [--model <path to gguf>]
   ```
   This prints the exact `git checkout <commit> -- <files>` and refuses when the model on disk is not that release's
   model. Then run `bash tests/run_all.sh` and `--verify <version>` again.
6. **Disengage: HUMAN only.** `disengage` refuses every principal except `HUMAN`, and the refusal is itself audited.
   It also needs the exact phrase `I CONFIRM DISENGAGING THE PAPER KILL SWITCH` and a written reason:
   ```python
   eng.kill.disengage("HUMAN", KillSwitch.PHRASE, "reconciled clean after <fix>")
   ```
   An LLM, a webhook or an automation **cannot** do this.

## SEV-2 runbook (analysis)

- **Benchmark regression.** Use the previous release (`--rollback`). Re-run the Phase 7 benchmark on the i5-12400 before
  claiming a fix. Values measured in the sandbox are not evidence for the target machine.
- **Corpus changed** (`index_update` CRITICAL). Run the RAG suite and battery (`tests/test_rag.py`,
  `tests/mutate_rag.py`). Record a new manifest with `--record-index` only once both are green.
- **Source failed its re-probe.** Disable it in `src/rag/sources.py`, then regenerate `LICENSES.md`
  (`python3 tools/build_licenses.py > LICENSES.md`). Answers that cite it must fall back to refusal.
- **Licence drift** (`LICENSES.md` differs from the registries). Regenerate the file and review the diff before
  committing. A new source needs a terms review in `docs/legal/`.

## Records and contacts

- Every incident gets a `DECISIONS.md` entry: what happened, the evidence (audit excerpt, `maintain.py --json` report),
  the action taken, and who approved disengaging.
- **Owner:** the repository owner (the only person who may approve a disengage, a risk-limit change, or Phase 11).
  The assistant may engage the kill switch, diagnose, and prepare a rollback. It may not disengage or approve.
- How to report an error: `docs/error-reporting.md`.
