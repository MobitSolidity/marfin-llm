"""
Phase 10 (D-0128): monitoring and maintenance checks.

Every check here is a PURE function of (the repository's own records, a policy,
and `now`). None of them reaches a network on its own: anything that needs the
network (re-probing a source, re-reading a licence page) takes an injectable
`probe` callable, and when none is supplied the check reports what is DUE rather
than pretending it ran. That keeps the whole module testable offline and keeps
the difference between "checked and fine" and "not checked" explicit.

Each check returns a list of Findings. A finding has a severity:

  CRITICAL  stop: something that can produce a wrong answer, a wrong order, or
            a licence breach right now (e.g. reconciliation never run while
            paper orders exist; a prohibited source enabled)
  WARN      due or drifting: needs a human soon (a source not re-verified
            within policy; a dependency unreviewed)
  INFO      recorded fact, no action

`summarize` (called by tools/maintain.py run_checks) aggregates them; its overall status is FAIL if any CRITICAL,
DUE if any WARN, else OK. "OK" is only ever claimed for checks that actually
ran -- a check that could not run (missing input) is a WARN, never an OK.

Stdlib only. Imports rag.sources and market.quotes for the registries, nothing
from execution except reading a paper engine's audit log file.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SEVERITIES = ("CRITICAL", "WARN", "INFO")


class Finding(dict):
    """A dict with fixed keys, so it serialises to JSON as-is."""

    def __init__(self, check, severity, subject, message, **extra):
        if severity not in SEVERITIES:
            raise ValueError("unknown severity %r" % (severity,))
        super().__init__(check=check, severity=severity, subject=subject,
                         message=message, **extra)


def _utc(now):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now


def _date(s) -> Optional[datetime.date]:
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _age_days(d: Optional[datetime.date], now) -> Optional[int]:
    return None if d is None else (now.date() - d).days


def load_policy(path=None) -> Dict[str, Any]:
    path = path or os.path.join(ROOT, "configs", "maintenance-policy.json")
    with open(path, encoding="utf-8") as fh:
        pol = json.load(fh)
    for k in ("source_reverify_days", "legal_review_days", "corpus_filing_max_age_days",
              "dependency_review_days", "risk_policy_review_days", "benchmark_max_age_days",
              "reconciliation_interval_minutes", "reconciliation_overdue_factor"):
        v = pol.get(k)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            raise ValueError("maintenance policy %s must be a positive number, got %r" % (k, v))
    return pol


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 1. Source refresh (SS.24: "Source refresh")
# ---------------------------------------------------------------------------

def check_sources(sources: Mapping[str, Any], policy, now=None,
                  probe: Optional[Callable[[Any], Mapping[str, Any]]] = None) -> List[Finding]:
    """
    Every ENABLED source must have been re-verified within policy. A disabled
    source is not refreshed (it is not used), but a source whose recorded
    status says PROHIBITED must never be enabled -- that is CRITICAL.

    With `probe`, each due source is probed now: probe(source) -> {"ok": bool,
    "detail": str}. A failed probe on an enabled source is CRITICAL (answers
    would cite a source that no longer answers); without `probe`, a due source
    is a WARN saying exactly that it was NOT probed.
    """
    now = _utc(now)
    out: List[Finding] = []
    limit = policy["source_reverify_days"]
    for key, s in sorted(sources.items()):
        status = str(getattr(s, "verified_status", "") or "")
        lic = str(getattr(s, "licence", "") or "")
        if s.enabled and ("PROHIBITED" in status.upper() or lic.upper().startswith("PROHIBITED")):
            out.append(Finding("source_refresh", "CRITICAL", key,
                               "source is ENABLED but its recorded terms say PROHIBITED"))
            continue
        if not s.enabled:
            continue
        age = _age_days(_date(getattr(s, "verified_on", None)), now)
        if "UNVERIFIED END TO END" in status.upper():
            # A dated probe that did NOT reach the data (e.g. FRED: HTTP 400
            # without a key) is not a verification, however recent.
            out.append(Finding("source_refresh", "WARN", key,
                               "enabled but never verified end to end: %s" % status[:120]))
            continue
        if age is None:
            out.append(Finding("source_refresh", "WARN", key,
                               "enabled source has no verified_on date: never verified"))
            continue
        if age <= limit:
            out.append(Finding("source_refresh", "INFO", key,
                               "verified %d days ago (limit %d)" % (age, limit), age_days=age))
            continue
        if probe is None:
            out.append(Finding("source_refresh", "WARN", key,
                               "re-verification DUE: last verified %d days ago (limit %d); "
                               "NOT probed in this run" % (age, limit), age_days=age))
            continue
        res = probe(s) or {}
        if res.get("ok") is True:
            out.append(Finding("source_refresh", "INFO", key,
                               "re-probed OK now (%s); update verified_on in "
                               "src/rag/sources.py" % res.get("detail", ""), age_days=age))
        else:
            out.append(Finding("source_refresh", "CRITICAL", key,
                               "enabled source FAILED its re-probe: %s" % res.get("detail", "no detail"),
                               age_days=age))
    return out


# ---------------------------------------------------------------------------
# 2. Index update (SS.24: "Index update")
# ---------------------------------------------------------------------------

def corpus_manifest(corpus_path) -> Dict[str, Any]:
    rows = []
    with open(corpus_path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return {"path": os.path.relpath(corpus_path, ROOT), "sha256": file_sha256(corpus_path),
            "n_passages": len(rows),
            "doc_ids": sorted({r["doc_id"] for r in rows}),
            "newest_filed": max((r.get("filed") or "") for r in rows) or None}


def check_index(corpus_path, manifest_path, policy, now=None) -> List[Finding]:
    """
    The index is the corpus file. The recorded manifest (sha256, doc ids) must
    match it, so a corpus edited without re-recording -- the index and the eval
    gold silently disagreeing -- is CRITICAL. The newest filing older than
    policy is a WARN: retrieval still works, but answers age.
    """
    now = _utc(now)
    out: List[Finding] = []
    cur = corpus_manifest(corpus_path)
    if not os.path.exists(manifest_path):
        return [Finding("index_update", "WARN", cur["path"],
                        "no recorded index manifest; run tools/maintain.py --record-index")]
    with open(manifest_path, encoding="utf-8") as fh:
        rec = json.load(fh)
    if rec.get("sha256") != cur["sha256"]:
        added = sorted(set(cur["doc_ids"]) - set(rec.get("doc_ids") or []))
        removed = sorted(set(rec.get("doc_ids") or []) - set(cur["doc_ids"]))
        out.append(Finding("index_update", "CRITICAL", cur["path"],
                           "corpus changed since its manifest was recorded (added %s, removed %s); "
                           "re-run the RAG regression and re-record" % (added, removed)))
    else:
        out.append(Finding("index_update", "INFO", cur["path"],
                           "corpus matches its manifest (%d passages)" % cur["n_passages"]))
    age = _age_days(_date(cur["newest_filed"]), now)
    if age is not None and age > policy["corpus_filing_max_age_days"]:
        out.append(Finding("index_update", "WARN", cur["path"],
                           "newest filing is %d days old (limit %d): answers about recent "
                           "periods will be correctly refused, not answered" %
                           (age, policy["corpus_filing_max_age_days"]), age_days=age))
    return out


# ---------------------------------------------------------------------------
# 3. Stale-data alerts (SS.24: "Stale-data alerts")
# ---------------------------------------------------------------------------

def check_quotes(quotes: Iterable[Any], max_age_s: float, now=None) -> List[Finding]:
    """
    A quote used for anything time-sensitive must be fresh. Each quote object
    needs .symbol (or .instrument_id), .timestamp (aware) and, if present,
    .delay_status. Older than max_age_s, or from the future, or labelled
    END_OF_DAY/DELAYED, is a WARN with the exact age -- the system must not
    present it as current.
    """
    now = _utc(now)
    out: List[Finding] = []
    for q in quotes:
        sym = getattr(q, "symbol", None) or getattr(q, "instrument_id", "?")
        ts = getattr(q, "timestamp", None)
        if ts is None or ts.tzinfo is None:
            out.append(Finding("stale_data", "WARN", sym, "quote has no aware timestamp"))
            continue
        age = (now - ts).total_seconds()
        delay = str(getattr(q, "delay_status", "") or "")
        if age < 0:
            out.append(Finding("stale_data", "WARN", sym, "quote is %.0f s in the FUTURE" % -age))
        elif age > max_age_s:
            out.append(Finding("stale_data", "WARN", sym,
                               "quote is %.0f s old (limit %.0f s)" % (age, max_age_s), age_s=age))
        elif delay in ("END_OF_DAY", "DELAYED"):
            out.append(Finding("stale_data", "WARN", sym,
                               "quote is labelled %s; never present it as live" % delay))
        else:
            out.append(Finding("stale_data", "INFO", sym, "fresh (%.1f s)" % age))
    return out


# ---------------------------------------------------------------------------
# 4. Dependency monitoring (SS.24: "Dependency monitoring")
# ---------------------------------------------------------------------------

def parse_requirements(path) -> Dict[str, str]:
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            name = line
            spec = ""
            for op in (">=", "==", "<=", "~=", ">", "<"):
                if op in line:
                    name, spec = line.split(op, 1)
                    spec = op + spec
                    break
            out[name.strip().lower()] = spec.strip()
    return out


def check_dependencies(requirements_path, lock_path, policy, now=None,
                       installed: Optional[Mapping[str, str]] = None) -> List[Finding]:
    """
    The lock file (releases/dependencies.lock.json) records, per requirement,
    the version that was reviewed and when. Findings:
      - a requirement with no lock entry: WARN (never reviewed)
      - a lock entry older than policy: WARN (review due)
      - `installed` (name -> version, e.g. from importlib.metadata on the target)
        differing from the reviewed version: WARN, naming both
      - a requirement with no version floor: WARN (unbounded upgrades)
    """
    now = _utc(now)
    out: List[Finding] = []
    req = parse_requirements(requirements_path)
    lock = {}
    if os.path.exists(lock_path):
        with open(lock_path, encoding="utf-8") as fh:
            lock = json.load(fh).get("packages", {})
    for name, spec in sorted(req.items()):
        if not spec:
            out.append(Finding("dependencies", "WARN", name, "no version constraint"))
        ent = lock.get(name)
        if not ent:
            out.append(Finding("dependencies", "WARN", name, "never reviewed: no lock entry"))
            continue
        age = _age_days(_date(ent.get("reviewed_on")), now)
        if age is None or age > policy["dependency_review_days"]:
            out.append(Finding("dependencies", "WARN", name,
                               "review due (last %s, limit %d days)"
                               % (ent.get("reviewed_on"), policy["dependency_review_days"])))
        if installed is not None:
            have = installed.get(name)
            if have is None:
                out.append(Finding("dependencies", "WARN", name, "not installed"))
            elif ent.get("version") and have != ent["version"]:
                out.append(Finding("dependencies", "WARN", name,
                                   "installed %s differs from reviewed %s: re-run the regression "
                                   "suite before trusting results" % (have, ent["version"])))
        if not any(f["subject"] == name and f["severity"] != "INFO" for f in out):
            out.append(Finding("dependencies", "INFO", name, "reviewed %s" % ent.get("version")))
    return out


# ---------------------------------------------------------------------------
# 5. License monitoring (SS.24: "License monitoring")
# ---------------------------------------------------------------------------

def check_licenses(licenses_path, render: Callable[[], str], legal_docs: Mapping[str, str],
                   policy, now=None) -> List[Finding]:
    """
    LICENSES.md must equal the generator's output (the registry and the record
    agree), and each legal review doc must have been re-done within policy
    (its "Reviewed on"/"Amended on" date). Drift is CRITICAL; an overdue review
    is a WARN.
    """
    now = _utc(now)
    out: List[Finding] = []
    with open(licenses_path, encoding="utf-8") as fh:
        if fh.read() != render():
            out.append(Finding("licenses", "CRITICAL", "LICENSES.md",
                               "LICENSES.md differs from the live registries: regenerate with "
                               "python3 tools/build_licenses.py > LICENSES.md and review the diff"))
        else:
            out.append(Finding("licenses", "INFO", "LICENSES.md", "matches the live registries"))
    import re
    for name, path in sorted(legal_docs.items()):
        with open(path, encoding="utf-8") as fh:
            head = fh.read(4000)
        # Accept the phrasings the review docs actually use ("Reviewed on",
        # "Amended on", "Date", "fetched ... on"). MEASURED: the AI-web-search
        # review dates itself only as "fetched and payload-checked on **2026-08-30**".
        dates = [_date(m) for m in re.findall(
            r"(?:Reviewed on|Amended on|Date|fetched[^.\n]{0,40}? on)[^0-9]{0,20}(\d{4}-\d{2}-\d{2})", head)]
        dates = [d for d in dates if d]
        if not dates:
            out.append(Finding("licenses", "WARN", name, "no review date found in the document"))
            continue
        age = _age_days(max(dates), now)
        sev = "WARN" if age > policy["legal_review_days"] else "INFO"
        out.append(Finding("licenses", sev, name,
                           "last reviewed %s (%d days; limit %d)%s"
                           % (max(dates), age, policy["legal_review_days"],
                              " -- re-review DUE" if sev == "WARN" else ""), age_days=age))
    return out


# ---------------------------------------------------------------------------
# 6. Benchmark refresh (SS.24: "Benchmark refresh")
# ---------------------------------------------------------------------------

def check_benchmark(verdict_path, baseline_path, policy, now=None) -> List[Finding]:
    """
    Compare the latest verdict file with the recorded release baseline:
    a threshold that was PASS and is now FAIL is CRITICAL (a regression); a
    measured value that moved the wrong way is a WARN; a benchmark older than
    policy is a WARN (refresh due -- it needs the target machine).
    """
    now = _utc(now)
    out: List[Finding] = []
    with open(verdict_path, encoding="utf-8") as fh:
        cur = {r["threshold"]: r for r in json.load(fh)["results"]}
    with open(baseline_path, encoding="utf-8") as fh:
        base = json.load(fh)
    bres = base["results"]
    for name, b in sorted(bres.items()):
        c = cur.get(name)
        if c is None:
            out.append(Finding("benchmark", "WARN", name, "missing from the current verdict"))
            continue
        cv = (c.get("deciding") or {}).get("value")
        if b["verdict"] == "PASS" and c["verdict"] != "PASS":
            out.append(Finding("benchmark", "CRITICAL", name,
                               "REGRESSION: PASS at baseline, %s now (%r -> %r)"
                               % (c["verdict"], b.get("value"), cv)))
        elif b.get("value") is not None and cv is not None and b.get("direction") in ("min", "max"):
            worse = cv < b["value"] if b["direction"] == "min" else cv > b["value"]
            if worse:
                out.append(Finding("benchmark", "WARN", name,
                                   "moved the wrong way: %r -> %r" % (b["value"], cv)))
    age = _age_days(_date(base.get("measured_on")), now)
    if age is None or age > policy["benchmark_max_age_days"]:
        out.append(Finding("benchmark", "WARN", "baseline",
                           "benchmark is %s days old (limit %d): refresh on the target machine"
                           % (age, policy["benchmark_max_age_days"])))
    if not any(f["severity"] != "INFO" for f in out):
        out.append(Finding("benchmark", "INFO", "baseline", "no regression vs %s" % base.get("measured_on")))
    return out


def baseline_from_verdict(verdict_path, measured_on, direction_of: Mapping[str, str]) -> Dict[str, Any]:
    with open(verdict_path, encoding="utf-8") as fh:
        v = json.load(fh)
    return {"source": os.path.relpath(verdict_path, ROOT), "measured_on": measured_on,
            "results": {r["threshold"]: {"verdict": r["verdict"],
                                         "value": (r.get("deciding") or {}).get("value"),
                                         "direction": direction_of.get(r["threshold"])}
                        for r in v["results"]}}


# ---------------------------------------------------------------------------
# 7. Broker reconciliation schedule (SS.24)
# ---------------------------------------------------------------------------

def check_reconciliation(audit_records: List[Mapping[str, Any]], policy, now=None) -> List[Finding]:
    """
    From a paper engine's audit log: if any order was submitted, a reconcile
    must have run within interval * overdue_factor, and the LAST reconcile must
    be ok. Submissions with no reconcile ever: CRITICAL. A failed last
    reconcile: CRITICAL. Overdue: WARN.
    """
    now = _utc(now)
    subs = [r for r in audit_records if r.get("event") in ("submitted", "submit_unknown")]
    recs = [r for r in audit_records if r.get("event") == "reconcile"]
    if not subs:
        return [Finding("reconciliation", "INFO", "paper", "no submissions; nothing to reconcile")]
    if not recs:
        return [Finding("reconciliation", "CRITICAL", "paper",
                        "%d submission(s) and NO reconciliation ever" % len(subs))]
    last = recs[-1]
    out: List[Finding] = []
    if last.get("ok") is not True:
        out.append(Finding("reconciliation", "CRITICAL", "paper",
                           "last reconciliation FAILED: %s" % (last.get("problems") or [])[:3]))
    at = datetime.datetime.strptime(last["at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=datetime.timezone.utc)
    mins = (now - at).total_seconds() / 60.0
    limit = policy["reconciliation_interval_minutes"] * policy["reconciliation_overdue_factor"]
    last_sub = max(datetime.datetime.strptime(r["at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=datetime.timezone.utc) for r in subs)
    if last_sub > at:
        out.append(Finding("reconciliation", "WARN", "paper",
                           "orders submitted after the last reconciliation"))
    if mins > limit:
        out.append(Finding("reconciliation", "WARN", "paper",
                           "last reconciliation %.0f min ago (limit %.0f)" % (mins, limit)))
    if not out:
        out.append(Finding("reconciliation", "INFO", "paper", "reconciled %.0f min ago, ok" % mins))
    return out


# ---------------------------------------------------------------------------
# 8. Risk-policy review (SS.24)
# ---------------------------------------------------------------------------

def check_risk_policy(policy_path, maint_policy, now=None,
                      limits_factory: Optional[Callable[..., Any]] = None) -> List[Finding]:
    """
    configs/risk-policy.json: must be PAPER, must construct a valid RiskLimits
    (limits_factory), must have been reviewed within policy, and -- recorded
    honestly -- whether a HUMAN has approved it (WARN until one has).
    """
    now = _utc(now)
    with open(policy_path, encoding="utf-8") as fh:
        rp = json.load(fh)
    out: List[Finding] = []
    if rp.get("environment") != "PAPER":
        out.append(Finding("risk_policy", "CRITICAL", "environment",
                           "risk policy environment is %r; only PAPER exists" % rp.get("environment")))
    if limits_factory is not None:
        try:
            lim = dict(rp["limits"])
            limits_factory(lim.pop("instrument_allowlist"), **lim)
        except Exception as exc:                     # noqa: BLE001 -- reported, not swallowed
            out.append(Finding("risk_policy", "CRITICAL", "limits",
                               "limits do not construct a valid RiskLimits: %s" % exc))
    age = _age_days(_date(rp.get("reviewed_on")), now)
    if age is None or age > maint_policy["risk_policy_review_days"]:
        out.append(Finding("risk_policy", "WARN", "review",
                           "risk-policy review DUE (last %s, limit %d days)"
                           % (rp.get("reviewed_on"), maint_policy["risk_policy_review_days"])))
    if rp.get("human_approved") is not True:
        out.append(Finding("risk_policy", "WARN", "approval",
                           "no human has approved these limits yet"))
    if not out:
        out.append(Finding("risk_policy", "INFO", "review", "reviewed %s, human-approved" % rp.get("reviewed_on")))
    return out


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def summarize(findings: List[Finding]) -> Dict[str, Any]:
    n = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITIES}
    status = "FAIL" if n["CRITICAL"] else ("DUE" if n["WARN"] else "OK")
    return {"status": status, "counts": n, "findings": findings}
