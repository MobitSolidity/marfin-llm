# -*- coding: utf-8 -*-
"""Mutation battery for Phase 10 (D-0128): each mutant weakens one maintenance guard; test_phase10 must fail."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ORACLE = os.path.join(HERE, "test_phase10.py")
MON = "src/maintenance/monitor.py"
REL = "src/maintenance/release.py"
CLI = "tools/maintain.py"

MUTATIONS = [
    # source refresh
    (MON, "prohibited+enabled not critical", 'if s.enabled and ("PROHIBITED" in status.upper()', 'if False and ("PROHIBITED" in status.upper()'),
    (MON, "unverified-end-to-end ignored", 'if "UNVERIFIED END TO END" in status.upper():', 'if False:'),
    (MON, "source limit exclusive", "if age <= limit:", "if age < limit:"),
    (MON, "failed probe reported ok", 'if res.get("ok") is True:', 'if True:'),
    (MON, "undated source treated as fresh", "if age is None:\n            out.append(Finding(\"source_refresh\"", "if False:\n            out.append(Finding(\"source_refresh\""),
    # index
    (MON, "corpus hash not compared", 'if rec.get("sha256") != cur["sha256"]:', 'if False:'),
    (MON, "filing age ignored", 'if age is not None and age > policy["corpus_filing_max_age_days"]:', 'if False:'),
    # quotes
    (MON, "future quote accepted", "if age < 0:", "if age < -1e9:"),
    (MON, "quote limit off by tolerance", "elif age > max_age_s:", "elif age > max_age_s * 2:"),
    (MON, "delayed quote presented as live", 'elif delay in ("END_OF_DAY", "DELAYED"):', 'elif delay in ("END_OF_DAY",):'),
    (MON, "naive timestamp accepted", "if ts is None or ts.tzinfo is None:", "if ts is None:"),
    # dependencies
    (MON, "unconstrained requirement ok", "        if not spec:\n", "        if False:\n"),
    (MON, "installed drift ignored", 'elif ent.get("version") and have != ent["version"]:', 'elif False:'),
    (MON, "dependency review never due", 'if age is None or age > policy["dependency_review_days"]:', 'if age is not None and age > policy["dependency_review_days"]:'),
    # licences
    (MON, "LICENSES drift not critical", 'out.append(Finding("licenses", "CRITICAL", "LICENSES.md",', 'out.append(Finding("licenses", "WARN", "LICENSES.md",'),
    (MON, "fetched-on phrasing dropped", "|fetched[^.\\n]{0,40}? on)", ")"),
    (MON, "legal review never overdue", 'sev = "WARN" if age > policy["legal_review_days"] else "INFO"', 'sev = "INFO"'),
    # benchmark
    (MON, "regression only a warning", '            out.append(Finding("benchmark", "CRITICAL", name,', '            out.append(Finding("benchmark", "WARN", name,'),
    (MON, "max-direction inverted", 'worse = cv < b["value"] if b["direction"] == "min" else cv > b["value"]', 'worse = cv < b["value"] if b["direction"] == "min" else cv < b["value"]'),
    (MON, "benchmark age ignored", 'if age is None or age > policy["benchmark_max_age_days"]:', 'if age is None:'),
    # reconciliation
    (MON, "unknown submission not counted", '("submitted", "submit_unknown")', '("submitted",)'),
    (MON, "never-reconciled not critical", '"%d submission(s) and NO reconciliation ever"', '"%d submission(s) and NO reconciliation ever" if False else ""'),
    (MON, "failed reconcile accepted", 'if last.get("ok") is not True:', 'if last.get("ok") is False and False:'),
    (MON, "overdue factor ignored", 'limit = policy["reconciliation_interval_minutes"] * policy["reconciliation_overdue_factor"]', 'limit = policy["reconciliation_interval_minutes"] * 4'),
    (MON, "order after reconcile ignored", "if last_sub > at:", "if False:"),
    (MON, "first reconcile used, not last", "last = recs[-1]", "last = recs[0]"),
    # risk policy
    (MON, "LIVE risk policy accepted", 'if rp.get("environment") != "PAPER":', 'if rp.get("environment") not in ("PAPER", "LIVE"):'),
    (MON, "invalid limits accepted", "limits_factory(lim.pop(\"instrument_allowlist\"), **lim)", "pass"),
    (MON, "truthy approval accepted", 'if rp.get("human_approved") is not True:', 'if not rp.get("human_approved"):'),
    (MON, "risk review never overdue", 'if age is None or age > maint_policy["risk_policy_review_days"]:', 'if age is None:'),
    # summary / policy
    (MON, "critical reported as DUE", 'status = "FAIL" if n["CRITICAL"] else', 'status = "DUE" if n["CRITICAL"] else'),
    (MON, "zero thresholds accepted", "or v <= 0:", "or v < 0:"),
    # release
    (REL, "release overwrite allowed", 'if os.path.exists(path):\n        raise ReleaseError("release %s already exists', 'if False:\n        raise ReleaseError("release %s already exists'),
    (REL, "version regression allowed", 'if [m for m in list_releases(root) if parse_version(m["version"]) >= parse_version(v)]:', 'if False:'),
    (REL, "behaviour change needs only patch", '        return "minor"\n', '        return "patch"\n'),
    (REL, "empty release allowed", 'if need == "none":', 'if False:'),
    (REL, "semver sorted as strings", 'return sorted(out, key=lambda m: parse_version(m["version"]))', 'return sorted(out, key=lambda m: m["version"])'),
    (REL, "pinned file hash not compared", "elif file_sha256(p) != sha:", "elif False:"),
    (REL, "missing pinned file not reported", "            missing.append(rel)\n", "            pass\n"),
    (REL, "wrong model rollback allowed", 'if v["model"] is not None and not v["model"]["ok"]:', 'if False:'),
    (REL, "rollback without a commit allowed", "if restore and not commit:", "if False:"),
    (REL, "model sha unchecked at build", 'if not re.fullmatch(r"[0-9a-f]{64}", str(model_sha256 or "")):', 'if False:'),
    (REL, "semver accepts suffixes", '_SEMVER = re.compile(r"^(\\d+)\\.(\\d+)\\.(\\d+)$")', '_SEMVER = re.compile(r"^(\\d+)\\.(\\d+)\\.(\\d+)")'),
    # CLI
    (CLI, "release refusal crashes", "        except REL.ReleaseError as exc:\n            print(\"REFUSED: %s\" % exc)\n            return 2\n        print(\"commit it", "        except KeyError as exc:\n            print(\"REFUSED: %s\" % exc)\n            return 2\n        print(\"commit it"),
    (CLI, "broken audit chain not reported", "            except PP.PaperError as exc:", "            except KeyError as exc:"),
    (CLI, "missing audit log silent", '"no audit log at %s: nothing was checked"', '"no audit log at %s: nothing was checked" if False else None'),
    (CLI, "unreleased edits not flagged", 'elif not u["ok"]:', 'elif False:'),
    (CLI, "risk policy unchecked", "                               limits_factory=PP.RiskLimits)", "                               limits_factory=None)"),
    # policy file
    ("configs/maintenance-policy.json", "reconcile interval widened", '"reconciliation_interval_minutes": 15', '"reconciliation_interval_minutes": 30'),
    ("configs/risk-policy.json", "human approval falsely claimed", '"human_approved": false', '"human_approved": true'),
    # docs
    ("docs/maintenance.md", "documented threshold drifts", "| `legal_review_days` | 120 |", "| `legal_review_days` | 180 |"),
    ("docs/incident-response.md", "SEV level dropped", "| **SEV-3** |", "| **SEV-x** |"),
]


def oracle():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run([sys.executable, ORACLE], cwd=ROOT, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    except subprocess.TimeoutExpired:
        return False
    return p.returncode == 0


def main():
    if not oracle():
        print("ABORT: oracle fails before mutation")
        return 1
    killed = survived = skipped = 0
    surv, skips = [], []
    for i, (f, desc, find, repl) in enumerate(MUTATIONS, 1):
        path = os.path.join(ROOT, f)
        orig = open(path, encoding="utf-8").read()
        if orig.count(find) != 1:
            skipped += 1
            skips.append("%s: %s (count=%d)" % (f, desc, orig.count(find)))
            print("  %2d. SKIP     %s" % (i, desc))
            continue
        try:
            open(path, "w", encoding="utf-8").write(orig.replace(find, repl, 1))
            ok = oracle()
        finally:
            open(path, "w", encoding="utf-8").write(orig)
        if ok:
            survived += 1
            surv.append("%s: %s" % (f, desc))
            print("  %2d. SURVIVED %s" % (i, desc))
        else:
            killed += 1
            print("  %2d. killed   %s" % (i, desc))
    intact = oracle()
    print("=" * 70)
    print("  seeded %d  killed %d  survived %d  skipped %d  restored+green %s"
          % (len(MUTATIONS), killed, survived, skipped, intact))
    for s in surv:
        print("  SURVIVOR:", s)
    for s in skips:
        print("  SKIPPED: ", s)
    return 0 if (survived == 0 and skipped == 0 and intact) else 1


if __name__ == "__main__":
    sys.exit(main())
