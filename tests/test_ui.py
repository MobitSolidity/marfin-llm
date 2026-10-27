# -*- coding: utf-8 -*-
"""
D-0140: scripts/ui.py (the local web UI) and execution/live_readiness.py (the Phase 11 gate).

Offline. The UI is driven through App.handle() (pure), plus one real loopback HTTP
round-trip. The paper engine runs in a temporary directory, and the execution mode comes
from a temporary config file. (V) verified invariant, (A) adversarial: must refuse,
(B) hand-checked value, (M) measured.
"""
import datetime
import json
import os
import re
import sys
import tempfile
import threading
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from _harness import check, check_true, section, summary          # noqa: E402
from execution import mode as M                                     # noqa: E402
from execution import paper as PP                                   # noqa: E402
from execution import live_readiness as LR                          # noqa: E402
from tools import registry as REG                                   # noqa: E402

TMP = tempfile.mkdtemp(prefix="marfin_ui_test_")


def conf(text):
    p = os.path.join(TMP, "exec_%d.conf" % abs(hash(text)))
    open(p, "w").write(text)
    M._reset_cache_for_tests(p)


conf("mode = ANALYSIS_ONLY\n")
import ui as U                                                      # noqa: E402

NOW = datetime.datetime(2026, 10, 26, 15, 0, tzinfo=datetime.timezone.utc)


def app(**kw):
    d = tempfile.mkdtemp(dir=TMP)
    kw.setdefault("paper_dir", os.path.join(d, "paper"))
    kw.setdefault("ask_audit_path", os.path.join(d, "ask.jsonl"))
    kw.setdefault("clock", lambda: NOW)
    kw.setdefault("maintain", lambda: {"status": "OK", "counts": {"INFO": 1},
                                       "findings": [{"severity": "INFO", "check": "c", "subject": "s",
                                                     "message": "<b>m</b>"}]})
    return U.App(**kw)


def strip(body):
    return re.sub(r"<style>.*?</style>", "", body, flags=re.S)


# ===========================================================================
section("Phase 11 live policy: tighter than paper, never active, never approved by default")
# ===========================================================================
LIVE = json.load(open(LR.LIVE_POLICY, encoding="utf-8"))
PAPER = json.load(open(LR.PAPER_POLICY, encoding="utf-8"))
check_true("shipped live policy has no problems", LR.check_live_policy(LIVE, PAPER) == [], "(V)")
check_true("live policy is a DRAFT, not approved, broker not chosen, no live account",
           LIVE["status"] == "DRAFT_NOT_ACTIVE" and LIVE["human_approved"] is False
           and LIVE["broker"] is None and LIVE["account_allowlist"] == [], "(V)")
check_true("every live limit is at least as strict as paper",
           all(LIVE["limits"][k] <= PAPER["limits"][k] for k in LR._SMALLER_IS_STRICTER), "(V)")
check_true("per-order confirmation ALWAYS, no automation policy",
           LIVE["per_order_confirmation"] == "ALWAYS" and LIVE["automation_policy"] is None, "(V)")


def mut(**ch):
    d = json.loads(json.dumps(LIVE))
    for k, v in ch.items():
        if k in d["limits"]:
            d["limits"][k] = v
        else:
            d[k] = v
    return LR.check_live_policy(d, PAPER)


check_true("a looser order limit than paper is refused",
           any("LOOSER" in p for p in mut(max_order_notional=20000.0)), "(A)")
check_true("a looser daily loss than paper is refused",
           any("max_daily_loss" in p for p in mut(max_daily_loss=5000.0)), "(A)")
check_true("an instrument outside the paper allowlist is refused",
           any("TSLA" in p for p in mut(instrument_allowlist=["AAPL", "TSLA"])), "(A)")
check_true("short selling live while paper forbids it is refused",
           any("allow_short" in p for p in LR.check_live_policy(
               dict(LIVE, limits=dict(LIVE["limits"], allow_short=True)),
               dict(PAPER, limits=dict(PAPER["limits"], allow_short=False)))), "(A)")
check_true("per-order confirmation weakened without an automation policy is refused",
           any("per_order_confirmation" in p for p in mut(per_order_confirmation="NEVER")), "(A)")
check_true("a PAPER- account on the live allowlist is refused",
           any("LIVE-" in p for p in mut(account_allowlist=["PAPER-0001"])), "(A)")
check_true("environment other than LIVE is refused",
           any("environment" in p for p in mut(environment="PAPER")), "(A)")
check_true("an empty instrument allowlist fails RiskLimits", any("RiskLimits" in p for p in mut(
    instrument_allowlist=[])), "(A)")

# ===========================================================================
section("Phase 11 kill-switch drill (MEASURED on a paper engine)")
# ===========================================================================
_before = set(x for x in os.listdir(tempfile.gettempdir()) if x.startswith("marfin_drill_"))
D = LR.kill_switch_drill(now=NOW)
check_true("the drill removes its own temporary engine directory",
           set(x for x in os.listdir(tempfile.gettempdir()) if x.startswith("marfin_drill_")) == _before, "(V)")
check_true("drill passed", D["passed"], "(M) %s" % [s for s in D["steps"] if not s["ok"]])
check("drill has 10 steps", len(D["steps"]), 10, method="(V)")
check_true("drill is labelled PAPER, and the live drill as NOT RUN",
           D["environment"] == "PAPER" and D["live_drill"].startswith("NOT RUN"), "(V)")
class _NoKillEngine(PP.PaperEngine):
    """DEFECTIVE on purpose: the kill switch no longer blocks a preview."""
    def _risk_checks(self, *a, **k):
        c = PP.PaperEngine._risk_checks(self, *a, **k)
        c["kill_switch"] = ("PASS", "ignored")
        return c


DB = LR.kill_switch_drill(now=NOW, engine_factory=_NoKillEngine)
check_true("the drill FAILS on an engine whose kill switch does not block previews",
           DB["passed"] is False and not next(s for s in DB["steps"]
                                              if s["step"] == "preview refused while engaged")["ok"], "(A)")
names = [s["step"] for s in D["steps"]]
for n in ("LLM cannot disengage", "AUTOMATION cannot disengage", "WEBHOOK cannot disengage",
          "wrong phrase refused", "preview refused while engaged", "audit chain intact"):
    check_true("drill step present: %s" % n, n in names, "(V)")

# ===========================================================================
section("Phase 11 readiness: BLOCKED for the right reasons; cannot enable anything")
# ===========================================================================
R = LR.readiness(drill=D)
check_true("verdict BLOCKED", R["verdict"] == "BLOCKED", "(V)")
check_true("ready is False and live_trading_enabled is False",
           R["ready"] is False and R["live_trading_enabled"] is False, "(V)")
check("8 SYSTEM_PROMPT section 24 prerequisites", R["n_total"], 8, method="(V)")
met = {p["name"]: p["met"] for p in R["prerequisites"]}
check_true("met: Phase 8A PASS, no critical blockers, explicit user request",
           met["Phase 8A PASS"] and met["no critical execution blockers"] and met["explicit user request"], "(V)")
for n in ("verified broker live environment", "independent authorised market data",
          "explicit risk limits", "audit and monitoring enabled", "emergency response tested"):
    check_true("unmet: %s" % n, met[n] is False, "(V)")
check("3 of 8 met", R["n_met"], 3, method="(V)")
check_true("SS.6.1: 10 of 12 unmet (unchanged by Phase 11)", (len(R["ss61_unmet"]), R["ss61_total"]) == (10, 12),
           "(V)")
check_true("9 deliverables reported", sorted(R["deliverables"]) == sorted(LR.DELIVERABLES), "(V)")
# Even an all-green policy and drill cannot make it ready while SS.6.1 is unmet.
p_ok = os.path.join(TMP, "live_ok.json")
json.dump(dict(LIVE, human_approved=True), open(p_ok, "w"))
R2 = LR.readiness(live_path=p_ok, drill=D)
check_true("an APPROVED live policy alone does not make it ready (broker, data, SS.6.1 still unmet)",
           R2["ready"] is False and R2["n_met"] == 4, "(A) n_met=%s" % R2["n_met"])
conf("mode = LIVE_TRADING\ni_have_approved_live_trading = yes\n")
R3 = LR.readiness(live_path=p_ok, drill=D)
check_true("even mode = LIVE_TRADING with the ack line: still BLOCKED, live_trading_enabled False",
           R3["ready"] is False and R3["live_trading_enabled"] is False, "(A)")
conf("mode = ANALYSIS_ONLY\n")
src = open(os.path.join(ROOT, "src", "execution", "live_readiness.py"), encoding="utf-8").read()
check_true("live_readiness.py writes no file except inside the drill's temp dir (no open(..., 'w'))",
           "\"w\"" not in src and "'w'" not in src and "CONFIG_PATH" not in src, "(V)")
check_true("live_readiness imports only execution.* from the project",
           set(re.findall(r"^from (\w+)", src, re.M)) <= {"__future__", "execution", "typing"}, "(V)")

# ===========================================================================
section("UI: every page renders; nothing 500s without a model")
# ===========================================================================
A = app()
for path, _t in U.NAV:
    r = A.handle("GET", path)
    check_true("GET %s -> 200, no internal error" % path, r.status == 200 and "INTERNAL ERROR" not in r.body,
               "(V) %d" % r.status)
check("unknown page -> 404", A.handle("GET", "/nope").status, 404, method="(V)")
check_true("every page is right-to-left Persian", 'dir="rtl"' in A.handle("GET", "/").body
           and 'lang="fa"' in A.handle("GET", "/").body, "(V)")
check_true("security headers: CSP default-src 'none', frames denied",
           "default-src 'none'" in A.handle("GET", "/").headers["Content-Security-Policy"]
           and A.handle("GET", "/").headers["X-Frame-Options"] == "DENY", "(V)")
check_true("no <script> anywhere in the UI's own markup", all(
    "<script" not in A.handle("GET", p).body for p, _ in U.NAV), "(V)")
check_true("dashboard says the model is not loaded", "بارگذاری نشده" in A.handle("GET", "/").body, "(V)")
check_true("dashboard says live trading is disabled with 10 of 12 unmet",
           "(10 از 12" in A.handle("GET", "/").body, "(V)")

# ===========================================================================
section("UI: loopback only, CSRF on every POST, methods")
# ===========================================================================
for h in ("evil.example", "evil.example:8765", "192.168.1.5:8765", "127.0.0.1.evil.example", ""):
    check("Host %r refused (DNS rebinding)" % h, A.handle("GET", "/", host=h).status, 403, method="(A)")
for h in ("127.0.0.1:8765", "localhost:8765", "[::1]:8765", "localhost"):
    check("Host %r accepted" % h, A.handle("GET", "/", host=h).status, 200, method="(V)")
check("POST without the token -> 403", A.handle("POST", "/calc", form={"tool": "pe_ratio"}).status, 403,
      method="(A)")
check("POST with a wrong token -> 403", A.handle("POST", "/calc", form={"csrf": "x", "tool": "pe_ratio"}).status,
      403, method="(A)")
check_true("each App gets a different token", app().csrf != app().csrf, "(V)")
check("PUT -> 405", A.handle("PUT", "/").status, 405, method="(A)")
check_true("every form on every page carries the token", all(
    strip(A.handle("GET", p).body).count('method="post"') == strip(A.handle("GET", p).body).count('name="csrf"')
    for p, _ in U.NAV), "(V)")

# ===========================================================================
section("UI: calculators -- all 85, forms from schemas, registry does the refusing")
# ===========================================================================
idx = A.handle("GET", "/calc").body
check("all registered tools are listed", sum(1 for n in REG.tool_names() if "/calc?tool=%s\"" % n in idx),
      len(REG.tool_names()), method="(V)")
check("85 tools", len(REG.tool_names()), 85, method="(V)")
bad = [n for n in REG.tool_names() if A.handle("GET", "/calc", {"tool": n}).status != 200]
check_true("every tool's form renders", bad == [], "(V) %s" % bad)


def calc(tool, **f):
    return A.handle("POST", "/calc", form=dict(f, csrf=A.csrf, tool=tool)).body


b = calc("pe_ratio", price="۱۵۰", eps="۸٫۴۰")
check_true("P/E with Persian digits = 17.857142857142858 (150/8.40)", "<code>17.857142857142858</code>" in b,
           "(B)")
b = calc("cagr", start="100000", end="161051", years="5")
check_true("CAGR 100000 -> 161051 over 5y = 0.1", "<code>0.10000000000000009</code>" in b, "(B)")
b = calc("position_size", account_equity="50,000", risk_pct="0.02", entry="80", stop="76")
check_true("position size = 250", "<code>250.0</code>" in b, "(B)")
b = calc("position_size", account_equity="50000", risk_pct="0.02", entry="50", stop="50")
check_true("zero stop distance is a REFUSAL, not a number", "امتناع" in b and "COMPUTED" not in b, "(A)")
b = calc("pe_ratio", price="nan", eps="1")
check_true("NaN refused by the registry gateway", "امتناع" in b and "non-finite" in b, "(A)")
b = calc("pe_ratio", price="150")
check_true("missing required argument refused", "missing_argument" in b, "(A)")
b = calc("sma", prices="1, 2، ۳ 4 5", period="5")
check_true("array field: commas, Persian comma, Persian digits, spaces -> SMA 3", "<code>3.0</code>" in b, "(B)")
check_true("parse_array", U.parse_array("1, 2 ، ۳;4") == ["1", "2", "۳", "4"], "(V)")
b = calc("no_such_tool", x="1")
check_true("unknown tool: refused and the list is shown", "ابزار ناشناخته" in b and "/calc?tool=cagr" in b, "(A)")
b = calc("pe_ratio", price="<script>alert(1)</script>", eps="1")
check_true("hostile input echoed only escaped", "<script>alert" not in b and "&lt;script&gt;" in b, "(A)")
_real_call = U.REG.call_tool
U.REG.call_tool = lambda n, a: {"ok": True, "name": n, "value": "<i>v</i>", "formula": "<i>f</i>",
                                "inputs": {"x": "<i>in</i>"}, "units": "<i>u</i>", "notes": "<i>n</i>"}
try:
    b = calc("pe_ratio", price="1", eps="1")
finally:
    U.REG.call_tool = _real_call
check_true("every field of a tool result is escaped (value, formula, inputs, units, notes)",
           "<i>" not in strip(b) and strip(b).count("&lt;i&gt;") == 5, "(A)")
enum_tool = next(n for n in REG.tool_names() if any(
    "enum" in s for s in REG._REGISTRY[n]["schema"]["function"]["parameters"]["properties"].values()))
check_true("enum fields render as <select> (%s)" % enum_tool,
           "<select" in A.handle("GET", "/calc", {"tool": enum_tool}).body, "(V)")

# ===========================================================================
section("UI: ask page -- Assistant output rendered by ask.turn_html, escaped")
# ===========================================================================


class FakeBot(object):
    def __init__(self):
        self.asked = []

    def answer(self, q):
        self.asked.append(q)
        return {"question": q, "lang": "fa", "route": "tools", "data_as_of": None,
                "warnings": ["<b>w</b>"], "reply": "<script>alert(1)</script> **۲۵۰ سهم**",
                "tool_results": [{"name": "position_size", "arguments": {"entry": 80}, "ok": True,
                                  "value": 250.0, "unit": None}],
                "evidence": [{"text": "<img src=x>", "citation": "c", "trust": "90"}],
                "notices": ["n"], "check": None}


bot = FakeBot()
B = app(assistant=bot, model_label="m.gguf")
r = B.handle("POST", "/ask", form={"csrf": B.csrf, "question": "<img src=x onerror=1> چند سهم؟"})
check_true("the question reached the Assistant verbatim", bot.asked == ["<img src=x onerror=1> چند سهم؟"], "(V)")
check_true("reply <script> escaped; bold kept", "<script>alert" not in r.body
           and "&lt;script&gt;" in r.body and "<b>۲۵۰ سهم</b>" in r.body, "(A)")
check_true("question, warning and evidence escaped", "<img src=x" not in r.body and "<b>w</b>" not in r.body,
           "(A)")
check_true("tool result line shown", "position_size" in r.body and "250.0" in r.body, "(V)")
check_true("Persian turn rendered right-to-left", '<div class="turn" dir="rtl">' in r.body, "(V)")
r = B.handle("POST", "/ask", form={"csrf": B.csrf, "question": "   "})
check_true("empty question refused, Assistant not called", "سؤال خالی" in r.body and len(bot.asked) == 1, "(A)")
r = A.handle("POST", "/ask", form={"csrf": A.csrf, "question": "x"})
check_true("no model: refused with the start command", "بدون مدل" in r.body and "--model" in r.body, "(A)")
B.handle("POST", "/ask", form={"csrf": B.csrf, "question": "second"})
r = B.handle("GET", "/ask")
check_true("history newest first", r.body.index("second") < r.body.index("چند سهم"), "(V)")


class Boom(object):
    def answer(self, q):
        raise RuntimeError("model crashed <x>")


r = app(assistant=Boom()).handle("POST", "/ask", form={"csrf": "", "question": "q"})
check("bad token still 403 before the model is touched", r.status, 403, method="(A)")
C = app(assistant=Boom())
r = C.handle("POST", "/ask", form={"csrf": C.csrf, "question": "q"})
check_true("an exception is a labelled 500 INTERNAL ERROR, escaped", r.status == 500
           and "INTERNAL ERROR (RuntimeError)" in r.body and "&lt;x&gt;" in r.body, "(V)")

# ===========================================================================
section("UI: macro page -- catalogue only; a refusal is shown, never a number")
# ===========================================================================
calls = []


def fake_macro(series, start_date=None, end_date=None, limit=13):
    calls.append((series, start_date, end_date, limit))
    if series == "UNRATE":
        raise RuntimeError("FRED_API_KEY is not set")
    return {"series": series, "source": "bis_statistics", "unit": "Percent per annum", "frequency": "daily",
            "observations": [{"date": "2026-10-20", "value": 4.0}], "notices": ["Source: BIS <x>"]}


E = app(macro_fetch=fake_macro)
r = E.handle("GET", "/macro")
check("all 11 series offered", r.body.count("<option value="), 11, method="(V)")
r = E.handle("POST", "/macro", form={"csrf": E.csrf, "series": "WS_CBPOL:D.US", "start": "2026-10-01",
                                     "limit": "5"})
check_true("BIS series fetched with the window and limit", calls[-1] == ("WS_CBPOL:D.US", "2026-10-01", None, 5)
           and "2026-10-20" in r.body and "RETRIEVED" in r.body, "(V) %s" % (calls[-1:],))
check_true("notice shown, escaped", "Source: BIS &lt;x&gt;" in r.body, "(V)")
r = E.handle("POST", "/macro", form={"csrf": E.csrf, "series": "UNRATE"})
check_true("source failure shown as a refusal", "دریافت نشد" in r.body and "FRED_API_KEY" in r.body, "(A)")
n = len(calls)
r = E.handle("POST", "/macro", form={"csrf": E.csrf, "series": "SP500"})
check_true("non-catalogue series refused before any fetch", "دریافت نشد" in r.body and len(calls) == n, "(A)")
check_true("default fetcher is rag.macro.macro_data", U.App().macro_fetch is U.MACRO.macro_data, "(V)")

# ===========================================================================
section("UI: paper trading -- preview, typed confirmation, HUMAN commit, kill switch")
# ===========================================================================
P = app()
Q = {"instrument": "AAPL", "side": "buy", "quantity": "10", "order_type": "market", "bid": "100",
     "ask": "100.02", "last": "100.01", "market_status": "OPEN"}


def post(a, **f):
    return a.handle("POST", "/paper", form=dict(f, csrf=a.csrf)).body


body = P.handle("GET", "/paper").body
check_true("paper banner shown", "PAPER TRADING" in body, "(V)")
check_true("ANALYSIS_ONLY: the page explains how to enable paper (the file, not a button)",
           "i_have_enabled_paper_trading = yes" in body and "این برنامه خودش این فایل را نمی‌نویسد" in body, "(V)")
b = post(P, action="preview", **Q)
check_true("preview works in ANALYSIS_ONLY (preview_order is permitted there)", ">PASS<" in b, "(V)")
pid = re.search(r'name="preview_id" value="([^"]+)"', b).group(1)
tok = re.search(r'name="token" value="([^"]+)"', b).group(1)
b = post(P, action="commit", preview_id=pid, token=tok, phrase="CONFIRM", **Q)
check_true("commit refused while paper trading is not enabled", "امتناع" in b and "not enabled" in b
           and not P.engine().orders, "(A)")
conf("mode = PAPER_TRADING\ni_have_enabled_paper_trading = yes\n")
P = app()
b = post(P, action="preview", **dict(Q, quantity="۱۰"))
check_true("Persian quantity accepted", ">PASS<" in b, "(V)")
check_true("quote labelled USER_SUPPLIED in the audit log", any(
    "USER_SUPPLIED" in json.dumps(r_, ensure_ascii=False) for r_ in P.engine().audit.records()), "(V)")
pid = re.search(r'name="preview_id" value="([^"]+)"', b).group(1)
tok = re.search(r'name="token" value="([^"]+)"', b).group(1)
b = post(P, action="commit", preview_id=pid, token=tok, phrase="confirm", **Q)
check_true("wrong / lower-case phrase: nothing submitted", "phrase not typed" in b and not P.engine().orders, "(A)")
b = post(P, action="commit", preview_id=pid, token="forged", phrase="CONFIRM", **Q)
check_true("forged token refused by the engine", "token does not match" in b and not P.engine().orders, "(A)")
b = post(P, action="commit", preview_id=pid, token=tok, phrase="CONFIRM", **Q)
check_true("typed CONFIRM + real token -> FILLED paper order", "FILLED" in b and len(P.engine().orders) == 1, "(V)")
check_true("the commit was made as HUMAN", any(r_.get("event") == "submitted" and r_.get("principal") == "HUMAN"
                                                for r_ in P.engine().audit.records()), "(V)")
b = post(P, action="commit", preview_id=pid, token=tok, phrase="CONFIRM", **Q)
check("re-submitting the same form is an idempotent replay (still 1 order)", len(P.engine().orders), 1,
      method="(A)")
check_true("cash debited by 10 x 100.02 + fee", P.engine().cash[U.PAPER_ACCOUNT] < U.PAPER_CASH - 1000.0, "(B)")
b = post(P, action="preview", **dict(Q, instrument="TSLA"))
check_true("instrument off the allowlist: REFUSE, no token", ">REFUSE<" in b and 'name="token"' not in b, "(A)")
b = post(P, action="preview", **dict(Q, quantity="5000"))
check_true("over the order notional: REFUSE", ">REFUSE<" in b, "(A)")
b = post(P, action="preview", **dict(Q, market_status="CLOSED"))
check_true("market CLOSED: REFUSE", ">REFUSE<" in b, "(A)")
b = post(P, action="preview", **dict(Q, bid="abc"))
check_true("non-number price refused, not crashed", "امتناع" in b and "not a number" in b, "(A)")
b = post(P, action="preview", **dict(Q, bid="101", ask="100"))
check_true("crossed quote refused", "crossed" in b, "(A)")
b = post(P, action="nuke")
check_true("unknown action refused", "unknown action" in b, "(A)")
b = post(P, action="reconcile")
check_true("reconcile OK", 'تطبیق: <span class="ok">OK' in b, "(V)")
b = post(P, action="kill_on", reason="test")
check_true("kill switch engaged from the UI", P.engine().kill.engaged() and "فعال: هیچ" in b, "(V)")
b = post(P, action="preview", **dict(Q, quantity="1"))
check_true("engaged: preview REFUSE on kill_switch", ">REFUSE<" in b and 'kill_switch</td><td class="bad">FAIL' in b,
           "(A)")
b = post(P, action="kill_off", phrase="I confirm", reason="r")
check_true("disengage with the wrong phrase refused", "امتناع" in b and P.engine().kill.engaged(), "(A)")
b = post(P, action="kill_off", phrase=PP.KillSwitch.PHRASE, reason="")
check_true("disengage without a reason refused", P.engine().kill.engaged(), "(A)")
b = post(P, action="kill_off", phrase=PP.KillSwitch.PHRASE, reason="test over")
check_true("disengage with the phrase and a reason", not P.engine().kill.engaged(), "(V)")
src_ui = open(os.path.join(ROOT, "scripts", "ui.py"), encoding="utf-8").read()
check_true("the UI never commits as anything but HUMAN, and never as LIVE",
           src_ui.count('"HUMAN"') >= 3 and '"LIVE"' not in src_ui and "submit_live_order" not in src_ui, "(V)")
check_true("the UI never writes the execution config", "CONFIG_PATH" in src_ui
           and "open(M.CONFIG_PATH" not in src_ui and "_reset_cache_for_tests" not in src_ui, "(V)")
conf("mode = ANALYSIS_ONLY\n")

# ===========================================================================
section("UI: audit, maintenance, providers, phase 11 pages")
# ===========================================================================
b = P.handle("GET", "/audit").body
check_true("paper audit chain shown as intact with records", "سالم" in b and "kill_switch_engaged" in b, "(V)")
log = os.path.join(P.paper_dir, "audit.jsonl")
lines = open(log, encoding="utf-8").read().splitlines()
lines[0] = lines[0].replace('"preview"', '"previeW"')
open(log, "w", encoding="utf-8").write("\n".join(lines) + "\n")
b = P.handle("GET", "/audit").body
check_true("an edited audit line shows the chain as BROKEN", "شکسته" in b and "hash mismatch" in b, "(A)")
check_true("missing ask log: 'no records yet', not an error", "هنوز رکوردی" in A.handle("GET", "/audit").body, "(V)")
b = A.handle("GET", "/maintenance").body
check_true("maintenance report rendered and escaped", "OK" in b and "&lt;b&gt;m&lt;/b&gt;" in b, "(V)")
os.environ["OPENAI_API_KEY"] = "sk-THIS-IS-A-FAKE-KEY-0000000000"
b = A.handle("GET", "/providers").body
check_true("providers page never shows a key", "sk-THIS-IS-A-FAKE" not in b and "OPENAI_API_KEY" in b, "(A)")
del os.environ["OPENAI_API_KEY"]
b = app(readiness=lambda: R).handle("GET", "/phase11").body
check_true("phase 11 page: BLOCKED, 3 of 8, 10 of 12, drill steps", "BLOCKED" in b and "3 از 8" in b
           and "10 از 12" in b and "WEBHOOK cannot disengage" in b, "(V)")
check_true("phase 11 page has no form at all (nothing to press)", "<form" not in strip(b), "(V)")

# ===========================================================================
section("UI: real loopback HTTP round-trip and CLI refusals")
# ===========================================================================
from http.server import ThreadingHTTPServer                        # noqa: E402
H = app()
srv = ThreadingHTTPServer(("127.0.0.1", 0), U.make_handler(H))
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % port
with urllib.request.urlopen(base + "/") as resp:
    check_true("GET / over HTTP: 200, utf-8 html, no-store", resp.status == 200
               and "utf-8" in resp.headers["Content-Type"] and resp.headers["Cache-Control"] == "no-store", "(M)")
data = urllib.parse.urlencode({"csrf": H.csrf, "tool": "cagr", "start": "100000", "end": "161051",
                               "years": "5"}).encode()
with urllib.request.urlopen(base + "/calc", data=data) as resp:
    check_true("POST /calc over HTTP computes", "0.10000000000000009" in resp.read().decode("utf-8"), "(M)")
try:
    urllib.request.urlopen(base + "/calc", data=b"x=" + b"a" * (U.MAX_BODY + 10))
    big = None
except urllib.error.HTTPError as exc:
    big = exc.code
check("oversized body -> 413", big, 413, method="(A)")
req = urllib.request.Request(base + "/", headers={"Host": "attacker.example"})
try:
    urllib.request.urlopen(req)
    rb = None
except urllib.error.HTTPError as exc:
    rb = exc.code
check("rebinding Host header over HTTP -> 403", rb, 403, method="(A)")
srv.shutdown()
srv.server_close()
import argparse                                                     # noqa: E402


def args(**kw):
    d = dict(host=U.HOST, model=None, server=None)
    d.update(kw)
    return argparse.Namespace(**d)


gguf = os.path.join(TMP, "real.gguf")
open(gguf, "wb").write(b"GGUF")
check_true("--host 0.0.0.0 refused", "--host 0.0.0.0 refused" in (U.refuse_args(args(host="0.0.0.0")) or ""), "(A)")
check_true("--host 192.168.1.5 refused", "refused" in (U.refuse_args(args(host="192.168.1.5")) or ""), "(A)")
check_true("--model and --server together refused",
           "not both" in (U.refuse_args(args(model=gguf, server="ollama")) or ""), "(A)")
check_true("missing model file refused",
           "not found" in (U.refuse_args(args(model=os.path.join(TMP, "none.gguf"))) or ""), "(A)")
check_true("valid arguments accepted (no model; existing model; server)",
           U.refuse_args(args()) is None and U.refuse_args(args(model=gguf)) is None
           and U.refuse_args(args(server="lmstudio")) is None, "(V)")
_rc = []
_t = threading.Thread(target=lambda: _rc.append(U.main(["--host", "0.0.0.0", "--no-open", "--port", "0"])),
                      daemon=True)
_t.start()
_t.join(5)
check_true("main() exits 2 on a refused argument, before serving (does not hang)", _rc == [2], "(A) %s" % _rc)
check_true("ui.py is stdlib + project modules only", all(x not in src_ui for x in (
    "import requests", "import flask", "import numpy", "import fastapi")), "(V)")
check_true("server binds the HOST constant 127.0.0.1", U.HOST == "127.0.0.1"
           and "ThreadingHTTPServer((HOST, a.port)" in src_ui, "(V)")

import shutil                                                       # noqa: E402
shutil.rmtree(TMP, ignore_errors=True)
print("")
sys.exit(summary())
