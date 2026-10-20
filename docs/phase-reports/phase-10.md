# Phase 10 Review — Monitoring and Maintenance

Date: 2026-10-20 · D-0128 (under the D-0126 delegation) · Labels: (V) VERIFIED · (M) MEASURED · (C) COMPUTED · (E) ESTIMATED

## Status: **BUILT, AWAITING USER APPROVAL**: all 12 SS.24 tasks are delivered and tested. SS.24 requires user approval for final acceptance; the assistant cannot give it.

| SS.24 task | Deliverable | Check |
|---|---|---|
| Source refresh | `monitor.check_sources` (with an injectable probe) | enabled + PROHIBITED → CRITICAL; over 90 days → DUE "NOT probed"; failed probe → CRITICAL |
| Index update | `check_index` + `releases/index-manifest.json` | corpus edited without re-recording → CRITICAL, naming added and removed doc ids |
| Regression tests | schedule in `docs/maintenance.md`; `tests/run_all.sh --mutate` | before every release and after any dependency change |
| Benchmark refresh | `check_benchmark` + `releases/benchmark-baseline.json` | PASS → FAIL → CRITICAL; value moved the wrong way → WARN; over 60 days → WARN |
| Stale-data alerts | `check_quotes` | over 5 s, future-dated, END_OF_DAY/DELAYED, or naive timestamp → WARN |
| Dependency monitoring | `check_dependencies` + `releases/dependencies.lock.json` | unreviewed, overdue, installed ≠ reviewed, or no constraint → WARN |
| License monitoring | `check_licenses` | `LICENSES.md` ≠ generator output → CRITICAL; legal review over 120 days → WARN |
| Versioning | `VERSION` 0.10.0; `maintenance/release.py`; `releases/0.10.0.json` | immutable manifests; a model/prompt/inference change needs at least a minor bump |
| Rollback | `--verify`, `--rollback` | exact `git checkout` plan; refused for an unknown release, a missing commit, or the wrong model |
| Incident response | `docs/incident-response.md` | SEV-1/2/3; kill switch → audit verify → reconcile → rollback → HUMAN-only disengage |
| Broker reconciliation schedule | `check_reconciliation` (from the audit log) | orders with no reconcile, or a failed last reconcile → CRITICAL; over 30 min → WARN |
| Risk-policy review | `configs/risk-policy.json` + `check_risk_policy` | non-PAPER or invalid limits → CRITICAL; over 90 days or not human-approved → WARN |

## Report today (V, `python3 tools/maintain.py`, 2026-10-20)

**STATUS: DUE**, 0 CRITICAL, 2 WARN. Both warnings are owner items, and the assistant must not clear them:
1. `fred`: enabled but never verified end to end, because no API key has been supplied (the probe returned HTTP 400
   without a key).
2. `risk_policy approval`: the paper limits were set under delegation; `human_approved` is `false` until the owner
   sets it.

## Design decisions (D-0128)
- **Offline by construction.** Every check is a pure function of repository records, the policy and `now`. Network
  probes are injected. A check that did not run is reported as DUE, never as OK.
- **No commit hash in a release manifest.** The first manifest recorded a wip commit that the squash would have
  deleted. Rollback now looks up the commit that added `releases/<v>.json` from git history, and refuses if none is
  found.
- **A broken audit chain is a finding, not a crash.** `AuditLog` refuses to open a tampered log. `maintain.py --audit`
  turns that refusal into CRITICAL. A missing log is a WARN ("nothing checked").
- `--release` over an existing version prints REFUSED and exits 2. Before this fix it ended in a traceback.

## Tests
- `tests/test_phase10.py`: every check through its CRITICAL, WARN and INFO paths, using synthetic inputs and a fixed
  clock, with inclusive limit edges checked by hand arithmetic. It also covers:
  - the release and rollback rules, in a scratch root;
  - an end-to-end run with a real paper engine and its audit log (unreconciled → FAIL, reconciled → INFO,
    overdue → WARN, tampered → CRITICAL);
  - the CLI exit codes;
  - the Phase 10 docs, pinned to the code and the policy.
- `tests/mutate_phase10.py`: each mutant weakens one guard, and `test_phase10` must fail.
  Result: 52/52 killed; the 7 first-pass survivors were fixed.
- Full `bash tests/run_all.sh --mutate`: 25 suites, 4779 assertions, 0 skipped; every battery has 0 survivors.
  The sweep found 9 **skipped** mutants in `mutate_phase4`, left behind by the D-0126 runner edits: ambiguous or
  moved anchors. They were re-anchored, and that battery is 332/332 killed again.

## Not done here (needs the owner or the target machine)
- Final acceptance of Phase 10 (needs user approval).
- Approval of the risk limits (`human_approved`).
- The FRED API key.
- The project-code licence.
- llama-cpp-python's version on the i5-12400 (`pip show llama-cpp-python` → `releases/dependencies.lock.json`).
- The benchmark refresh, which is due by 2026-12-16 (60 days after 2026-10-17) and must run on the target.
- Phase 11 (live trading) is optional and never automatic: every SS.6.1 prerequisite is still False.
