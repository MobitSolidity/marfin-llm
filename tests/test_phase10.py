# -*- coding: utf-8 -*-
"""
Phase 10 (D-0128): monitoring and maintenance, SS.24.

One section per SS.24 Phase 10 task. Every check in src/maintenance/monitor.py
is driven with synthetic inputs and a fixed clock, through its CRITICAL, WARN
and INFO paths; the release/rollback rules run in a throw-away root; the CLI is
run as a subprocess against the real repository. Nothing reaches a network.

(V) verified invariant, (A) adversarial: must be refused or flagged, (B) hand
arithmetic on dates.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from _harness import check, check_raises, check_true, section, summary  # noqa: E402
from maintenance import monitor as MON                                   # noqa: E402
from maintenance import release as REL                                   # noqa: E402
from execution import paper as PP                                        # noqa: E402

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
POL = MON.load_policy()
TMP = tempfile.mkdtemp(prefix="p10_")


def sev(fs, s):
    return [f for f in fs if f["severity"] == s]


def w(name, text):
    p = os.path.join(TMP, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


def wj(name, obj):
    return w(name, json.dumps(obj))


def days_ago(n):
    return (NOW - datetime.timedelta(days=n)).date().isoformat()


# ===========================================================================
section("0. maintenance policy")
# ===========================================================================
check("source re-verify every 90 days", POL["source_reverify_days"], 90, method="(V)")
check("reconcile every 15 minutes", POL["reconciliation_interval_minutes"], 15, method="(V)")
check("risk-policy review every 90 days", POL["risk_policy_review_days"], 90, method="(V)")
check("benchmark max age 60 days", POL["benchmark_max_age_days"], 60, method="(V)")
for bad in (0, -1, "90", True, None):
    p = wj("pol_bad.json", dict(POL, source_reverify_days=bad))
    check_raises("policy refuses source_reverify_days=%r" % (bad,), lambda p=p: MON.load_policy(p))
check_raises("Finding refuses an unknown severity", lambda: MON.Finding("x", "ERROR", "s", "m"))
check_raises("a naive `now` is refused", lambda: MON.check_quotes([], 5, datetime.datetime(2026, 1, 1)))

# ===========================================================================
section("1. source refresh")
# ===========================================================================
SRC = {
    "fresh": NS(enabled=True, verified_on=days_ago(10), verified_status="MEASURED ok", licence="CC0"),
    "edge": NS(enabled=True, verified_on=days_ago(90), verified_status="MEASURED ok", licence="CC0"),
    "old": NS(enabled=True, verified_on=days_ago(91), verified_status="MEASURED ok", licence="CC0"),
    "nodate": NS(enabled=True, verified_on=None, verified_status="", licence="CC0"),
    "keyless": NS(enabled=True, verified_on=days_ago(1),
                  verified_status="MEASURED: HTTP 400; UNVERIFIED end to end", licence="public domain"),
    "off": NS(enabled=False, verified_on=None, verified_status="", licence="CC0"),
    "banned": NS(enabled=True, verified_on=days_ago(1), verified_status="PROHIBITED by terms", licence="x"),
    "banned_off": NS(enabled=False, verified_on=None, verified_status="PROHIBITED", licence="x"),
}
fs = {f["subject"]: f for f in MON.check_sources(SRC, POL, NOW)}
check_true("10-day-old verification is INFO", fs["fresh"]["severity"] == "INFO", "(B)")
check_true("exactly 90 days is still INFO (limit inclusive)", fs["edge"]["severity"] == "INFO", "(B)")
check_true("91 days is WARN and says NOT probed",
           fs["old"]["severity"] == "WARN" and "NOT probed" in fs["old"]["message"], "(B)")
check_true("no verified_on date is WARN", fs["nodate"]["severity"] == "WARN", "(A)")
check_true("a recent probe that never reached data is still WARN (FRED case)",
           fs["keyless"]["severity"] == "WARN" and "end to end" in fs["keyless"]["message"], "(A)")
check_true("a disabled source is not reported", "off" not in fs, "(V)")
check_true("an ENABLED prohibited source is CRITICAL", fs["banned"]["severity"] == "CRITICAL", "(A)")
check_true("a disabled prohibited source is fine", "banned_off" not in fs, "(V)")
fs = {f["subject"]: f for f in MON.check_sources(SRC, POL, NOW, probe=lambda s: {"ok": True, "detail": "200"})}
check_true("an overdue source that re-probes OK is INFO", fs["old"]["severity"] == "INFO", "(V)")
fs = {f["subject"]: f for f in MON.check_sources(SRC, POL, NOW, probe=lambda s: {"ok": False, "detail": "404"})}
check_true("an overdue source that FAILS its probe is CRITICAL", fs["old"]["severity"] == "CRITICAL", "(A)")
fs = {f["subject"]: f for f in MON.check_sources(SRC, POL, NOW, probe=lambda s: None)}
check_true("a probe returning nothing counts as failed, not ok", fs["old"]["severity"] == "CRITICAL", "(A)")
called = []
MON.check_sources(SRC, POL, NOW, probe=lambda s: called.append(s) or {"ok": True})
check("only the overdue source is probed", len(called), 1, method="(V)")
from rag import sources as S                                            # noqa: E402
real = MON.check_sources(S.SOURCES, POL, NOW)
check("real registry: no CRITICAL", len(sev(real, "CRITICAL")), 0, method="(V)")
check_true("real registry: fred is INFO now -- verified end to end with the owner's key (D-0133)",
           any(f["subject"] == "fred" and f["severity"] == "INFO" for f in real), "(V)")
check("real registry: no source WARN at 2026-10-21", len(sev(real, "WARN")), 0, method="(V)")

# ===========================================================================
section("2. index update")
# ===========================================================================
rows = [{"doc_id": "A", "filed": "2025-01-01", "text": "a"}, {"doc_id": "B", "filed": "2026-02-01", "text": "b"}]
corpus = w("corpus.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n")
m = MON.corpus_manifest(corpus)
check("manifest counts passages", m["n_passages"], 2, method="(V)")
check_true("manifest newest_filed is the max date", m["newest_filed"] == "2026-02-01", "(V)")
man = wj("index-manifest.json", m)
fs = MON.check_index(corpus, man, POL, NOW)
check_true("unchanged corpus: INFO only", not sev(fs, "WARN") and not sev(fs, "CRITICAL"), "(V)")
fs = MON.check_index(corpus, os.path.join(TMP, "missing.json"), POL, NOW)
check_true("no manifest is WARN, not OK", fs[0]["severity"] == "WARN", "(A)")
w("corpus.jsonl", "\n".join(json.dumps(r) for r in rows + [{"doc_id": "C", "filed": "2026-03-01"}]) + "\n")
crit = sev(MON.check_index(corpus, man, POL, NOW), "CRITICAL")
check_true("an edited corpus is CRITICAL and names the added doc",
           len(crit) == 1 and "'C'" in crit[0]["message"], "(A)")
w("corpus.jsonl", json.dumps(rows[0]) + "\n")
crit = sev(MON.check_index(corpus, man, POL, NOW), "CRITICAL")
check_true("a removed doc is named", bool(crit) and "removed ['B']" in crit[0]["message"], "(A)")
w("corpus.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n")
fs = MON.check_index(corpus, man, POL, NOW + datetime.timedelta(days=600))
check_true("newest filing older than 550 days is WARN", len(sev(fs, "WARN")) == 1, "(B)")
real = MON.check_index(os.path.join(ROOT, "evals", "rag_corpus_combined.jsonl"),
                       os.path.join(ROOT, "releases", "index-manifest.json"), POL, NOW)
check("real corpus matches its recorded manifest", len(sev(real, "CRITICAL")), 0, method="(V)")


# ===========================================================================
section("3. stale-data alerts")
# ===========================================================================
def qt(age_s, delay="REALTIME", aware=True, sym="AAPL"):
    ts = NOW - datetime.timedelta(seconds=age_s)
    return NS(symbol=sym, timestamp=ts if aware else ts.replace(tzinfo=None), delay_status=delay)


fs = MON.check_quotes([qt(1), qt(5), qt(6), qt(-3), qt(1, "END_OF_DAY"), qt(1, "DELAYED"),
                       qt(1, aware=False), NS(symbol="X", timestamp=None)], 5.0, NOW)
check_true("1 s old is INFO", fs[0]["severity"] == "INFO", "(B)")
check_true("exactly 5 s is INFO (limit inclusive)", fs[1]["severity"] == "INFO", "(B)")
check_true("6 s old is WARN with the age", fs[2]["severity"] == "WARN" and "6 s" in fs[2]["message"], "(B)")
check_true("a future quote is WARN", fs[3]["severity"] == "WARN" and "FUTURE" in fs[3]["message"], "(A)")
check_true("END_OF_DAY is WARN even when recent", fs[4]["severity"] == "WARN", "(A)")
check_true("DELAYED is WARN even when recent", fs[5]["severity"] == "WARN", "(A)")
check_true("a naive timestamp is WARN", fs[6]["severity"] == "WARN", "(A)")
check_true("no timestamp is WARN", fs[7]["severity"] == "WARN", "(A)")
qs = PP.QuoteSnapshot("MSFT", 99.99, 100.01, 100.0, NOW - datetime.timedelta(seconds=30), "OPEN", "t")
fs = MON.check_quotes([qs], 5.0, NOW)
check_true("a real QuoteSnapshot (instrument_id) is read and flagged",
           fs[0]["subject"] == "MSFT" and fs[0]["severity"] == "WARN", "(V)")

# ===========================================================================
section("4. dependency monitoring")
# ===========================================================================
req = w("requirements.txt", "# comment\nalpha>=1.0\nbeta==2.0  # pinned\ngamma\ndelta>=0.1\n")
check_true("requirements parsed, comments ignored",
           MON.parse_requirements(req) == {"alpha": ">=1.0", "beta": "==2.0", "gamma": "", "delta": ">=0.1"}, "(V)")
lock = wj("lock.json", {"packages": {"alpha": {"version": "1.2", "reviewed_on": days_ago(5)},
                                     "beta": {"version": "2.0", "reviewed_on": days_ago(91)},
                                     "gamma": {"version": "3", "reviewed_on": days_ago(1)}}})
by = {}
for f in MON.check_dependencies(req, lock, POL, NOW):
    by.setdefault(f["subject"], []).append(f["severity"])
check_true("reviewed recently: INFO", by["alpha"] == ["INFO"], "(V)")
check_true("review older than 90 days: WARN", "WARN" in by["beta"], "(B)")
check_true("no version constraint: WARN", "WARN" in by["gamma"], "(A)")
check_true("no lock entry: WARN", by["delta"] == ["WARN"], "(A)")
fs = MON.check_dependencies(req, lock, POL, NOW, installed={"alpha": "1.3", "gamma": "3"})
msgs = {}
for f in sev(fs, "WARN"):
    msgs.setdefault(f["subject"], []).append(f["message"])
check_true("installed version differing from reviewed is WARN, naming both",
           any("1.3" in x and "1.2" in x for x in msgs.get("alpha", [])), "(A)")
check_true("a reviewed package not installed is WARN",
           any("not installed" in x for x in msgs.get("beta", [])), "(A)")
lock2 = wj("lock2.json", {"packages": {"alpha": {"version": "1.2", "reviewed_on": None}}})
fs = MON.check_dependencies(w("req2.txt", "alpha>=1.0\n"), lock2, POL, NOW)
check_true("a lock entry with no review date is WARN (review due)",
           [f["severity"] for f in fs] == ["WARN"] and "review due" in fs[0]["message"], "(A)")
real = MON.check_dependencies(os.path.join(ROOT, "requirements.txt"),
                              os.path.join(ROOT, "releases", "dependencies.lock.json"), POL, NOW)
check("real requirements: every package reviewed, no WARN", len(sev(real, "WARN")), 0, method="(V)")

# ===========================================================================
section("5. licence monitoring")
# ===========================================================================
lic = w("LICENSES.md", "rendered\n")
d1 = w("legal/a.md", "# A\nReviewed on 2026-10-01.\n")
d2 = w("legal/b.md", "# B\nAmended on **%s**\n" % days_ago(121))
d3 = w("legal/c.md", "# C\nfetched and payload-checked on **2026-08-30**\n")
d4 = w("legal/d.md", "# D\nno date here\n")
fs = {f["subject"]: f for f in MON.check_licenses(lic, lambda: "rendered\n",
                                                   {"a": d1, "b": d2, "c": d3, "d": d4}, POL, NOW)}
check_true("LICENSES.md equal to render(): INFO", fs["LICENSES.md"]["severity"] == "INFO", "(V)")
check_true("19-day-old review: INFO", fs["a"]["severity"] == "INFO", "(B)")
check_true("121-day-old review: WARN, re-review DUE",
           fs["b"]["severity"] == "WARN" and "DUE" in fs["b"]["message"], "(B)")
check_true("'fetched ... on <date>' phrasing is recognised (51 days)",
           fs["c"]["severity"] == "INFO" and fs["c"].get("age_days") == 51, "(B)")
check_true("no date in a review doc is WARN", fs["d"]["severity"] == "WARN", "(A)")
fs = MON.check_licenses(lic, lambda: "rendered differently\n", {}, POL, NOW)
check_true("LICENSES.md drift from the registries is CRITICAL", fs[0]["severity"] == "CRITICAL", "(A)")
import build_licenses as BL                                             # noqa: E402
import maintain as MT                                                    # noqa: E402
real = MON.check_licenses(os.path.join(ROOT, "LICENSES.md"), BL.render,
                          {k: os.path.join(ROOT, v) for k, v in MT.LEGAL.items()}, POL, NOW)
check("real LICENSES.md matches the live registries", len(sev(real, "CRITICAL")), 0, method="(V)")
check("real legal docs all dated and within 120 days at 2026-10-20", len(sev(real, "WARN")), 0, method="(V)")
# ===========================================================================
section("6. benchmark refresh / regression")
# ===========================================================================
def verdict(**vals):
    return wj("verdict.json", {"results": [{"threshold": k, "verdict": v[0], "deciding": {"value": v[1]}}
                                           for k, v in vals.items()]})


base = wj("baseline.json", {"measured_on": days_ago(10), "results": {
    "acc_min": {"verdict": "PASS", "value": 95.0, "direction": "min"},
    "err_max": {"verdict": "PASS", "value": 0.0, "direction": "max"},
    "cite_min": {"verdict": "FAIL", "value": 90.0, "direction": "min"}}})
fs = MON.check_benchmark(verdict(acc_min=("PASS", 95.0), err_max=("PASS", 0.0), cite_min=("FAIL", 91.0)),
                         base, POL, NOW)
check_true("same or better: INFO only", [f["severity"] for f in fs] == ["INFO"], "(V)")
fs = MON.check_benchmark(verdict(acc_min=("FAIL", 80.0), err_max=("PASS", 0.0), cite_min=("FAIL", 90.0)),
                         base, POL, NOW)
check_true("PASS -> FAIL is a CRITICAL regression",
           any(f["subject"] == "acc_min" and f["severity"] == "CRITICAL" for f in fs), "(A)")
fs = MON.check_benchmark(verdict(acc_min=("PASS", 94.0), err_max=("PASS", 1.0), cite_min=("FAIL", 89.0)),
                         base, POL, NOW)
check("three values moved the wrong way (min down, max up, min down)", len(sev(fs, "WARN")), 3, method="(B)")
fs = MON.check_benchmark(verdict(acc_min=("PASS", 95.0), err_max=("PASS", 0.0)), base, POL, NOW)
check_true("a threshold missing from the verdict is WARN",
           any(f["subject"] == "cite_min" and f["severity"] == "WARN" for f in fs), "(A)")
fs = MON.check_benchmark(verdict(acc_min=("PASS", 95.0), err_max=("PASS", 0.0), cite_min=("FAIL", 90.0)),
                         base, POL, NOW + datetime.timedelta(days=51))
check_true("a 61-day-old benchmark is WARN (refresh on the target)",
           any(f["subject"] == "baseline" and f["severity"] == "WARN" for f in fs), "(B)")
fs = MON.check_benchmark(verdict(acc_min=("PASS", 95.0), err_max=("PASS", 0.0), cite_min=("FAIL", 90.0)),
                         base, POL, NOW + datetime.timedelta(days=50))
check_true("a 60-day-old benchmark is still INFO (limit inclusive)", not sev(fs, "WARN"), "(B)")
real = MON.check_benchmark(MT.CURRENT_VERDICT, os.path.join(ROOT, "releases", "benchmark-baseline.json"), POL, NOW)
check("real baseline: no regression vs the current verdict",
      len(sev(real, "CRITICAL")) + len(sev(real, "WARN")), 0, method="(V)")
b = json.load(open(os.path.join(ROOT, "releases", "benchmark-baseline.json")))
check("baseline records all 12 Phase 7 thresholds", len(b["results"]), 12, method="(V)")
check_true("every baseline threshold has a direction",
           all(r["direction"] in ("min", "max") for r in b["results"].values()), "(V)")
check_true("baseline equals a fresh derivation from the verdict file",
           b == MON.baseline_from_verdict(MT.CURRENT_VERDICT, "2026-10-21", MT.DIRECTION), "(V)")
check_true("the baseline is the owner's Phase 8C run of the recommended configuration",
           b["source"] == "evidence/phase8c_verdict_2026-10-21.json" and b["measured_on"] == "2026-10-21", "(V)")


# ===========================================================================
section("7. broker reconciliation schedule")
# ===========================================================================
def rec(event, minutes_ago, **kw):
    t = NOW - datetime.timedelta(minutes=minutes_ago)
    return dict(event=event, at=t.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), **kw)


check_true("no submissions: INFO", MON.check_reconciliation([], POL, NOW)[0]["severity"] == "INFO", "(V)")
fs = MON.check_reconciliation([rec("submitted", 5)], POL, NOW)
check_true("submissions and no reconcile ever: CRITICAL", fs[0]["severity"] == "CRITICAL", "(A)")
fs = MON.check_reconciliation([rec("submit_unknown", 5)], POL, NOW)
check_true("an UNKNOWN submission counts as a submission", fs[0]["severity"] == "CRITICAL", "(A)")
fs = MON.check_reconciliation([rec("submitted", 20), rec("reconcile", 10, ok=True)], POL, NOW)
check_true("reconciled 10 min ago after the last order: INFO", [f["severity"] for f in fs] == ["INFO"], "(V)")
fs = MON.check_reconciliation([rec("submitted", 20), rec("reconcile", 10, ok=False, problems=["x"])], POL, NOW)
check_true("a failed last reconcile: CRITICAL", bool(sev(fs, "CRITICAL")), "(A)")
fs = MON.check_reconciliation([rec("submitted", 20), rec("reconcile", 15, ok=False),
                               rec("reconcile", 10, ok=True)], POL, NOW)
check_true("an earlier failure fixed by a later ok reconcile: INFO", not sev(fs, "CRITICAL"), "(V)")
fs = MON.check_reconciliation([rec("submitted", 40), rec("reconcile", 31, ok=True)], POL, NOW)
check_true("31 min since reconcile (limit 15 x 2 = 30): WARN", bool(sev(fs, "WARN")), "(B)")
fs = MON.check_reconciliation([rec("submitted", 40), rec("reconcile", 30, ok=True)], POL, NOW)
check_true("exactly 30 min: still INFO", not sev(fs, "WARN"), "(B)")
fs = MON.check_reconciliation([rec("reconcile", 10, ok=True), rec("submitted", 5)], POL, NOW)
check_true("an order after the last reconcile: WARN",
           any("after the last" in f["message"] for f in sev(fs, "WARN")), "(A)")

# End to end with a real paper engine and its hash-chained audit log.
from execution import mode as M                                         # noqa: E402
M._reset_cache_for_tests(w("execution.conf", "mode = PAPER_TRADING\ni_have_enabled_paper_trading = yes\n"))
T0 = datetime.datetime(2026, 10, 20, 11, 0, tzinfo=UTC)
sd = os.path.join(TMP, "engine")
eng = PP.PaperEngine(sd, {"PAPER-0001": 100000.0}, PP.RiskLimits(("AAPL",)))


def qa(t):
    return PP.QuoteSnapshot("AAPL", 99.99, 100.01, 100.0, t, "OPEN", "t", bid_size=1e9, ask_size=1e9)


p = eng.preview("PAPER-0001", "PAPER", "AAPL", "buy", 10, "market", "c1", qa(T0), now=T0)
t1 = T0 + datetime.timedelta(seconds=1)
eng.commit(p["preview_id"], p["confirmation_token"], "k1", "HUMAN", qa(t1), now=t1)


def recon(r):
    return [f["severity"] for f in r["findings"] if f["check"] == "reconciliation"]


r1 = MT.run_checks(now=T0 + datetime.timedelta(minutes=2), audit_dir=sd)
check_true("CLI path: real engine with an unreconciled order is FAIL",
           r1["status"] == "FAIL" and recon(r1) == ["CRITICAL"], "(A)")
eng.reconcile(now=T0 + datetime.timedelta(minutes=3))
r2 = MT.run_checks(now=T0 + datetime.timedelta(minutes=5), audit_dir=sd)
check_true("after reconcile: reconciliation is INFO", recon(r2) == ["INFO"], "(V)")
r3 = MT.run_checks(now=T0 + datetime.timedelta(minutes=40), audit_dir=sd)
check_true("37 min later the schedule is overdue: WARN", recon(r3) == ["WARN"], "(B)")
ap = os.path.join(sd, "audit.jsonl")
lines = open(ap).read().splitlines()
lines[1] = lines[1].replace('"event": ', '"event": "x', 1).replace('"x"', '"x', 1)
open(ap, "w").write("\n".join(lines) + "\n")
r4 = MT.run_checks(now=T0 + datetime.timedelta(minutes=5), audit_dir=sd)
check_true("an edited audit log is CRITICAL, not a crash",
           any(f["subject"] == "audit" and f["severity"] == "CRITICAL" for f in r4["findings"]), "(A)")
r5 = MT.run_checks(now=NOW, audit_dir=os.path.join(TMP, "no_engine"))
check_true("a missing audit log is WARN (nothing checked), never OK",
           any(f["subject"] == "audit" and f["severity"] == "WARN" for f in r5["findings"]), "(A)")

# ===========================================================================
section("8. risk-policy review")
# ===========================================================================
RP = json.load(open(os.path.join(ROOT, "configs", "risk-policy.json")))
check_true("risk policy is PAPER", RP["environment"] == "PAPER", "(V)")
check_true("the owner approved the limits (D-0129) and the file says who", RP["human_approved"] is True
           and RP["reviewed_by"].startswith("owner") and RP["reviewed_on"] == "2026-10-21", "(V)")
_lim = dict(RP["limits"])
rl = PP.RiskLimits(_lim.pop("instrument_allowlist"), **_lim)
check("configured max order notional is 10000", rl.max_order_notional, 10000.0, method="(V)")
check_true("configured as the owner set it: shorting allowed, leverage 1", rl.allow_short is True
           and rl.max_leverage == 1.0, "(V)")
_owner = json.load(open("/home/user/uploaded_files/risk-policy.json.txt")) if os.path.exists(
    "/home/user/uploaded_files/risk-policy.json.txt") else None
check_true("the limits are the owner's file verbatim (when that file is present)",
           _owner is None or _owner["limits"] == RP["limits"], "(V)")


def rp(**kw):
    d = json.loads(json.dumps(RP))
    d.update(kw)
    return wj("rp.json", d)


fs = MON.check_risk_policy(rp(human_approved=True), POL, NOW, PP.RiskLimits)
check_true("approved, reviewed today, valid: INFO only", [f["severity"] for f in fs] == ["INFO"], "(V)")
fs = MON.check_risk_policy(rp(), POL, NOW + datetime.timedelta(days=1), PP.RiskLimits)
check_true("the repo's approved policy: INFO only", [f["severity"] for f in fs] == ["INFO"], "(V)")
fs = MON.check_risk_policy(rp(human_approved=False), POL, NOW, PP.RiskLimits)
check_true("not human-approved: WARN", [f["subject"] for f in sev(fs, "WARN")] == ["approval"], "(V)")
fs = MON.check_risk_policy(rp(environment="LIVE", human_approved=True), POL, NOW, PP.RiskLimits)
check_true("a LIVE risk policy is CRITICAL", bool(sev(fs, "CRITICAL")), "(A)")
fs = MON.check_risk_policy(rp(human_approved=True, limits=dict(RP["limits"], max_order_notional=-1)),
                           POL, NOW, PP.RiskLimits)
check_true("a negative limit is CRITICAL (RiskLimits refuses it)", bool(sev(fs, "CRITICAL")), "(A)")
fs = MON.check_risk_policy(rp(human_approved=True, limits=dict(RP["limits"], instrument_allowlist=[])),
                           POL, NOW, PP.RiskLimits)
check_true("an empty allowlist is CRITICAL", bool(sev(fs, "CRITICAL")), "(A)")
fs = MON.check_risk_policy(rp(human_approved=True, reviewed_on=days_ago(91)), POL, NOW, PP.RiskLimits)
check_true("a review older than 90 days is WARN", bool(sev(fs, "WARN")), "(B)")
fs = MON.check_risk_policy(rp(human_approved=True, reviewed_on=days_ago(90)), POL, NOW, PP.RiskLimits)
check_true("a review exactly 90 days old is INFO", not sev(fs, "WARN"), "(B)")
fs = MON.check_risk_policy(rp(human_approved="yes"), POL, NOW, PP.RiskLimits)
check_true("human_approved must be literally true, not truthy", bool(sev(fs, "WARN")), "(A)")

# ===========================================================================
section("9. versioning")
# ===========================================================================
check_true("parse_version accepts 0.10.0", REL.parse_version("0.10.0") == (0, 10, 0), "(V)")
for bad in ("0.10", "v0.10.0", "0.10.0-rc1", "", None):
    check_raises("parse_version refuses %r" % (bad,), lambda b=bad: REL.parse_version(b), REL.ReleaseError)
check_true("0.10.0 sorts after 0.9.9 (numeric, not string)",
           REL.parse_version("0.10.0") > REL.parse_version("0.9.9"), "(V)")
check_true("VERSION file is 0.11.1 (D-0136: fixes to the owner-reported ask.py defects)", REL.read_version() == "0.11.1", "(V)")

R = os.path.join(TMP, "repo")
for rel in REL.PINNED_FILES:
    pth = os.path.join(R, rel)
    os.makedirs(os.path.dirname(pth), exist_ok=True)
    open(pth, "w").write("content of %s\n" % rel)
SHA = "a" * 64
PO = {"display": True}
INF = {"ctx": 16384}


def mk(v, sha=SHA, po=PO, inf=INF):
    open(os.path.join(R, "VERSION"), "w").write(v + "\n")
    return REL.build_manifest(v, sha, po, inf, None, None, root=R, now=NOW)


check_raises("build_manifest refuses a non-sha model",
             lambda: REL.build_manifest("1.0.0", "xyz", PO, INF, None, None, root=R), REL.ReleaseError)
os.rename(os.path.join(R, "requirements.txt"), os.path.join(R, "req.bak"))
check_raises("build_manifest refuses a missing pinned file", lambda: mk("1.0.0"), REL.ReleaseError)
os.rename(os.path.join(R, "req.bak"), os.path.join(R, "requirements.txt"))
m1 = mk("1.0.0")
check("manifest pins every file", len(m1["files"]), len(REL.PINNED_FILES), method="(V)")
REL.write_release(m1, root=R)
check_raises("rewriting an existing release is refused (immutable)",
             lambda: REL.write_release(m1, root=R), REL.ReleaseError)


def refusal(fn):
    try:
        fn()
    except REL.ReleaseError as exc:
        return str(exc)
    return ""


check_true("... and the refusal says why: immutable",
           "immutable" in refusal(lambda: REL.write_release(m1, root=R)), "(A)")
check_raises("nothing changed: no release",
             lambda: REL.write_release(dict(m1, version="1.0.1"), root=R), REL.ReleaseError)
check_true("required_bump: same -> none", REL.required_bump(m1, m1) == "none", "(V)")
check_true("required_bump: model sha -> minor",
           REL.required_bump(m1, dict(m1, model_sha256="b" * 64)) == "minor", "(V)")
check_true("required_bump: prompt options -> minor",
           REL.required_bump(m1, dict(m1, prompt_options={"display": False})) == "minor", "(V)")
check_true("required_bump: inference -> minor",
           REL.required_bump(m1, dict(m1, inference={"ctx": 8192})) == "minor", "(V)")
check_true("required_bump: files only -> patch",
           REL.required_bump(m1, dict(m1, files=dict(m1["files"], VERSION="x"))) == "patch", "(V)")
m_bad = mk("1.0.1", sha="b" * 64)
check_raises("a model change released as a PATCH is refused",
             lambda: REL.write_release(m_bad, root=R), REL.ReleaseError)
check_true("... and nothing was written", not os.path.exists(os.path.join(R, "releases", "1.0.1.json")), "(V)")
REL.write_release(mk("1.1.0", sha="b" * 64), root=R)
check_raises("a version lower than the newest release is refused",
             lambda: REL.write_release(mk("1.0.5", sha="c" * 64), root=R), REL.ReleaseError)
# A files-only change released as 1.0.2 would satisfy the bump rule against
# 1.0.0, so only the "versions only increase" guard can refuse it.
msg = refusal(lambda: REL.write_release(mk("1.0.2"), root=R))
check_true("a well-bumped but LOWER version (1.0.2 after 1.1.0) is refused: versions only increase",
           "only increase" in msg and not os.path.exists(os.path.join(R, "releases", "1.0.2.json")), "(A)")
open(os.path.join(R, "src/llm/style.py"), "w").write("changed\n")
REL.write_release(mk("1.1.1", sha="b" * 64), root=R)
check_true("list order is semver",
           [x["version"] for x in REL.list_releases(R)] == ["1.0.0", "1.1.0", "1.1.1"], "(V)")
R2 = os.path.join(TMP, "repo2")
shutil.copytree(R, R2)
shutil.rmtree(os.path.join(R2, "releases"))
REL.write_release(REL.build_manifest("1.2.0", SHA, PO, INF, None, None, root=R2, now=NOW), root=R2)
REL.write_release(REL.build_manifest("1.10.0", "d" * 64, PO, INF, None, None, root=R2, now=NOW), root=R2)
check_true("1.10.0 sorts after 1.2.0 (string order would invert them)",
           [x["version"] for x in REL.list_releases(R2)] == ["1.2.0", "1.10.0"], "(A)")
check_true("... so unreleased_changes compares with 1.10.0, the newest",
           REL.unreleased_changes(R2)["version"] == "1.10.0", "(A)")
open(os.path.join(R, "releases", "notes.json"), "w").write("{}")
check("non-version files in releases/ are ignored", len(REL.list_releases(R)), 3, method="(V)")

# ===========================================================================
section("10. rollback")
# ===========================================================================
check_true("tree matches the newest release", REL.verify_against(REL.list_releases(R)[-1], root=R)["ok"], "(V)")
v = REL.verify_against(REL.list_releases(R)[0], root=R)
check_true("tree differs from 1.0.0 in VERSION and style.py",
           not v["ok"] and set(v["differs"]) == {"VERSION", "src/llm/style.py"}, "(V)")
check_true("unreleased_changes: none against newest", REL.unreleased_changes(R)["ok"], "(V)")
check_true("unreleased_changes: None when no release exists",
           REL.unreleased_changes(os.path.join(TMP, "empty")) is None, "(V)")
open(os.path.join(R, "src/rag/sources.py"), "w").write("edited, not released\n")
check_true("unreleased_changes names an edited pinned file",
           REL.unreleased_changes(R)["differs"] == ["src/rag/sources.py"], "(A)")
os.remove(os.path.join(R, "src/rag/sources.py"))
check_true("a deleted pinned file is reported missing",
           REL.unreleased_changes(R)["missing"] == ["src/rag/sources.py"], "(A)")
plan = REL.rollback_plan("1.0.0", root=R, commit_resolver=lambda v, r: "abc123",
                         commit_checker=lambda c, f, r: [])
check_true("rollback plan restores exactly the differing+missing files",
           set(plan["restore_files"]) == {"VERSION", "src/llm/style.py", "src/rag/sources.py"}, "(V)")
check_true("rollback command uses the release's commit",
           plan["command"].startswith("git checkout abc123 -- "), "(V)")
check_true("rollback says to re-run the suite and re-verify",
           "run_all.sh" in plan["then"] and "--verify 1.0.0" in plan["then"], "(V)")
check_raises("rollback to a commit that does NOT hold the release's files is refused (squashed releases)",
             lambda: REL.rollback_plan("1.0.0", root=R, commit_resolver=lambda v, r: "abc123",
                                       commit_checker=lambda c, f, r: sorted(f)), REL.ReleaseError)
check_true("... the default checker reads the files AT the commit: a bogus commit holds none of them",
           REL.commit_has_files("0" * 40, {"VERSION": "x"}) == ["VERSION"], "(A)")
_OK = lambda c, f, r: []                                                  # noqa: E731
check_true("rollback with no findable commit is refused, not a blank command (and says why)",
           "cannot be found" in refusal(lambda: REL.rollback_plan(
               "1.0.0", root=R, commit_resolver=lambda v, r: None, commit_checker=_OK)), "(A)")
check_raises("rollback to an unknown release is refused",
             lambda: REL.rollback_plan("0.9.0", root=R), REL.ReleaseError)
mf = w("model.gguf", "not the model")
check_true("rollback with the wrong model on disk is refused (and says why)",
           "is not release" in refusal(lambda: REL.rollback_plan(
               "1.0.0", root=R, model_path=mf, commit_resolver=lambda v, r: "x", commit_checker=_OK)), "(A)")
check_true("verify with the wrong model is not ok",
           REL.verify_against(REL.list_releases(R)[-1], root=R, model_path=mf)["ok"] is False, "(A)")
open(os.path.join(R, "src/rag/sources.py"), "w").write("content of src/rag/sources.py\n")
check_true("restoring the file returns the tree to the newest release", REL.unreleased_changes(R)["ok"], "(V)")
plan = REL.rollback_plan("1.1.1", root=R)
check_true("rollback to the current release: already at target, no command",
           plan["already_at_target"] and plan["command"] is None, "(V)")

# The real release.
rels = {x["version"]: x for x in REL.list_releases()}
m10 = rels.get("0.10.0", {})
check_true("release 0.10.0 is recorded", bool(m10), "(V)")
check_true("0.10.0 records the Q4_K_M model sha", m10.get("model_sha256") == MT.MODEL_SHA, "(V)")
check_true("0.10.0 records the D-0126 prompt options",
           m10.get("prompt_options") == dict(sorted(MT.PROMPT_OPTIONS.items())), "(V)")
check_true("0.10.0 records the inference settings",
           m10.get("inference") == dict(sorted(MT.INFERENCE.items())), "(V)")
check_true("0.10.0 has no git_commit (found from history; squash-safe)", m10.get("git_commit") is None, "(V)")
m101 = rels.get("0.10.1", {})
check_true("release 0.10.1 is recorded (D-0129: guard narrowed, owner-approved limits)", bool(m101), "(V)")
check_true("0.10.1 is a PATCH: same model, prompt options and inference as 0.10.0",
           bool(m101) and REL.required_bump(m10, m101) == "patch", "(V)")
check_true("0.10.1 pins the execution-guard module", "src/safety/untrusted.py" in m101.get("files", {}), "(V)")
m102 = rels.get("0.10.2", {})
check_true("release 0.10.2 is recorded (D-0130: Apache-2.0 LICENSE and NOTICE pinned)",
           bool(m102) and {"LICENSE", "NOTICE"} <= set(m102.get("files", {})), "(V)")
check_true("0.10.2 is a PATCH over 0.10.1", bool(m102) and REL.required_bump(m101, m102) == "patch", "(V)")
# The CURRENT release is the newest manifest, and it must equal VERSION. Written
# against "newest" rather than a literal version so the next patch release does
# not need these assertions rewritten (each release previously broke them).
newest = REL.list_releases()[-1]
check_true("the newest release manifest is the VERSION file's version",
           newest["version"] == REL.read_version(), "(V) %s vs %s" % (newest["version"], REL.read_version()))
vr = REL.verify_against(newest)
check_true("the working tree matches the newest release", vr["ok"],
           "(V) %s differs %r missing %r" % (newest["version"], vr["differs"], vr["missing"]))
_chain = REL.list_releases()
check_true("no release after 0.10.0 changed model, prompt options or inference (each needs only a PATCH)",
           all(REL.required_bump(a, b) == "patch" for a, b in zip(_chain, _chain[1:])), "(V)")
_m110 = {r["version"]: r for r in _chain}.get("0.11.0", {})
check_true("0.11.0 pins ask.py and macro.py (the new user-facing paths)",
           {"scripts/ask.py", "src/rag/macro.py"} <= set(_m110.get("files", {})), "(V)")
check_true("release history is 0.10.0, 0.10.1, 0.10.2, ... with no gaps or reuse",
           [r["version"] for r in _chain][:3] == ["0.10.0", "0.10.1", "0.10.2"]
           and len({r["version"] for r in _chain}) == len(_chain), "(V)")
# Every older release is a real rollback target: its commit (found from history)
# must hold exactly its files -- 0.10.0 lives in its own squashed commit 24e807d.
for _old in _chain[:-1]:
    _rb = REL.rollback_plan(_old["version"])
    check_true("rollback to %s names a commit that really holds its files" % _old["version"],
               _rb["already_at_target"] or (bool(_rb["commit"]) and REL.commit_has_files(
                   _rb["commit"], {k: _old["files"][k] for k in _rb["restore_files"]}) == []),
               "(V) %r" % {k: _rb[k] for k in ("commit", "restore_files")})
hdr = json.load(open(os.path.join(ROOT, "evidence", "phase7_gguf_headers_2026-10-16.json")))
check_true("MODEL_SHA equals the measured Q4_K_M hash",
           hdr["full_file_hashes"]["Qwen3.5-4B-Q4_K_M.gguf"]["sha256"] == MT.MODEL_SHA, "(V)")
check_true("PROMPT_OPTIONS min_trust and continue_budget match D-0126",
           MT.PROMPT_OPTIONS["min_trust"] == 80 and MT.PROMPT_OPTIONS["continue_budget"] == 256, "(V)")

# ===========================================================================
section("11. maintain CLI and summary")
# ===========================================================================
F = MON.Finding
check_true("summary FAIL on any CRITICAL",
           MON.summarize([F("a", "CRITICAL", "s", "m"), F("a", "INFO", "s", "m")])["status"] == "FAIL", "(V)")
check_true("summary DUE on WARN only", MON.summarize([F("a", "WARN", "s", "m")])["status"] == "DUE", "(V)")
check_true("summary OK on INFO only", MON.summarize([F("a", "INFO", "s", "m")])["status"] == "OK", "(V)")
check_true("summary counts are exact",
           MON.summarize([F("a", "WARN", "s", "m")] * 2)["counts"] == {"CRITICAL": 0, "WARN": 2, "INFO": 0}, "(V)")


def cli(*args):
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "maintain.py")] + list(args),
                       cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    return p.returncode, p.stdout.decode("utf-8", "replace")


out_json = os.path.join(TMP, "report.json")
rc, out = cli("--json", out_json)
rep = json.load(open(out_json))
check("CLI exit code matches its status", rc, {"OK": 0, "DUE": 1, "FAIL": 2}[rep["status"]], method="(V)")
check("CLI report on the repo: no CRITICAL", rep["counts"]["CRITICAL"], 0, method="(V)")
warns = {(f["check"], f["subject"]) for f in rep["findings"] if f["severity"] == "WARN"}
check_true("CLI: FRED is verified, so no FRED WARN (D-0133)", ("source_refresh", "fred") not in warns, "(V)")
check_true("CLI: the risk limits are approved, so no approval WARN", ("risk_policy", "approval") not in warns, "(V)")
check("CLI: no WARN on the repo today -- every owner item is closed", len(warns), 0,
      method="(V) %r" % sorted(warns))
check_true("CLI covers every check family",
           {"source_refresh", "index_update", "dependencies", "licenses", "benchmark", "risk_policy",
            "versioning"} <= {f["check"] for f in rep["findings"]}, "(V)")
check_true("CLI: tree matches its release",
           any(f["check"] == "versioning" and f["severity"] == "INFO" for f in rep["findings"]), "(V)")
rc, out = cli("--release")
check("CLI --release over an existing release exits 2", rc, 2, method="(A)")
check_true("... and says REFUSED, no traceback", "REFUSED" in out and "Traceback" not in out, "(A)")
rc, out = cli("--verify", newest["version"])
check("CLI --verify <newest> exits 0", rc, 0, method="(V)")
rc, out = cli("--verify", "0.9.0")
check("CLI --verify unknown exits 2", rc, 2, method="(A)")
rc, out = cli("--rollback", "0.9.0")
check_true("CLI --rollback unknown exits 2 with REFUSED", rc == 2 and "REFUSED" in out, "(A)")
rc, out = cli("--rollback", newest["version"])
check_true("CLI --rollback <newest>: already at target", rc == 0 and '"already_at_target": true' in out, "(V)")
rc, out = cli("--verify", "0.10.0")
check("CLI --verify 0.10.0 now exits 2 (the tree moved on)", rc, 2, method="(V)")


# run_checks wiring: the versioning finding and the risk-limit factory.
_orig_unrel, _orig_rp = MT.REL.unreleased_changes, MT.MON.check_risk_policy
seen = {}
try:
    MT.REL.unreleased_changes = lambda root: {"ok": False, "version": "0.10.0",
                                              "differs": ["src/rag/sources.py"], "missing": []}

    def _spy(*a, **kw):
        seen.update(kw)
        return _orig_rp(*a, **kw)
    MT.MON.check_risk_policy = _spy
    rr = MT.run_checks(now=NOW)
finally:
    MT.REL.unreleased_changes, MT.MON.check_risk_policy = _orig_unrel, _orig_rp
check_true("run_checks: a pinned file edited without a release is a versioning WARN",
           any(f["check"] == "versioning" and f["severity"] == "WARN" and "sources.py" in f["message"]
               for f in rr["findings"]), "(A)")
check_true("run_checks validates the risk limits with the engine's RiskLimits",
           seen.get("limits_factory") is PP.RiskLimits, "(V)")
MT.REL.unreleased_changes = lambda root: None
try:
    rr = MT.run_checks(now=NOW)
finally:
    MT.REL.unreleased_changes = _orig_unrel
check_true("run_checks: no release at all is a WARN, never OK",
           any(f["check"] == "versioning" and f["severity"] == "WARN" for f in rr["findings"]), "(A)")

# ===========================================================================
section("12. Phase 10 documents are pinned to the code")
# ===========================================================================
def read(rel):
    return open(os.path.join(ROOT, rel), encoding="utf-8").read()


IR = read("docs/incident-response.md")
MD = read("docs/maintenance.md")
MAINT = read("tools/maintain.py")
for flag in ("--release", "--verify", "--rollback", "--audit", "--record-index", "--record-baseline", "--json"):
    check_true("maintenance.md documents %s, and the CLI has it" % flag,
               flag in MD and ('"%s"' % flag) in MAINT, "(V)")
for k in ("source_reverify_days", "legal_review_days", "dependency_review_days", "risk_policy_review_days",
          "benchmark_max_age_days", "reconciliation_interval_minutes", "corpus_filing_max_age_days"):
    check_true("maintenance.md states %s = %s, as the policy does" % (k, POL[k]),
               ("| `%s` | %s |" % (k, POL[k])) in MD, "(V)")
check_true("incident runbook: disengage is HUMAN-only, as in the code",
           "HUMAN" in IR and "disengage" in IR and "def disengage(self, principal" in read("src/execution/paper.py"),
           "(V)")
for sevname in ("SEV-1", "SEV-2", "SEV-3"):
    check_true("incident runbook defines %s as a table row" % sevname, ("| **%s** |" % sevname) in IR, "(V)")
check_true("incident runbook: exit codes match the CLI docstring",
           "exit 2" in IR and "Exit status: 0 OK, 1 DUE (warnings), 2 FAIL (critical)" in MAINT, "(V)")
P10 = read("docs/phase-reports/phase-10.md")
check_true("phase-10 report exists", len(P10) > 500, "(V)")
check_true("phase-10 report says final acceptance needs the user", "user approval" in P10.lower(), "(V)")

shutil.rmtree(TMP, ignore_errors=True)
print("")
sys.exit(summary())
