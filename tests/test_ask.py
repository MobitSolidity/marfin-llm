# -*- coding: utf-8 -*-
"""
D-0135: rag/macro.py (SS.8.3 macro_data) and scripts/ask.py (the end-user path).

Offline: FRED and BIS are injected, the model is a scripted llama-cpp-shaped
callable, and the FRED key is a FAKE of the right shape. (V) verified invariant,
(A) adversarial -- must refuse or warn, (B) hand-checked value, (M) measured.
"""
import datetime
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from _harness import check, check_raises, check_true, section, summary  # noqa: E402
from rag import macro as M                                               # noqa: E402
from rag import sources as S                                             # noqa: E402
from rag.citations import verify_claim, extract_numbers                  # noqa: E402
import run_phase4 as RP                                                  # noqa: E402
import ask as A                                                          # noqa: E402

K = "0123456789abcdef0123456789abcdef"          # shape of a FRED key; not a real one


def fred(obs):
    return lambda url, key, t: {"observations": obs}


CPI_OBS = ([{"date": "2026-09-01", "value": "336.298"}, {"date": "2026-08-01", "value": "."}]
           + [{"date": "2026-%02d-01" % m, "value": "330"} for m in range(7, 0, -1)]
           + [{"date": "2025-%02d-01" % m, "value": "324.245" if m == 9 else "323"}
              for m in range(12, 8, -1)])

# ===========================================================================
section("macro catalogue: closed, units pinned to what the source reported (V 2026-10-23)")
# ===========================================================================
check("11 catalogue series: 5 FRED + 6 BIS policy rates", len(M.SERIES), 11, method="(V)")
for sid, unit in (("CPIAUCSL", "Index 1982-1984=100"), ("UNRATE", "Percent"), ("FEDFUNDS", "Percent"),
                  ("DGS10", "Percent"), ("GDP", "Billions of Dollars")):
    check_true("%s unit is FRED's own string %r" % (sid, unit),
               M.SERIES[sid]["unit"] == unit and M.SERIES[sid]["source"] == "fred", "(M) /fred/series")
check_true("GDP's scale word is 'billion' -- the citation verifier scales by it",
           M.SERIES["GDP"]["units_note"] == "billion", "(V)")
check_true("every non-GDP series DECLARES a unit (never None: None means 'scale unknown')",
           all(s["units_note"] for s in M.SERIES.values()), "(V)")
check_true("every BIS series is a WS_CBPOL daily policy rate in percent per annum",
           all(s["unit"] == "Percent per annum" and s["frequency"] == "daily"
               for k, s in M.SERIES.items() if s["source"] == "bis_statistics"), "(M) CSV UNIT_MEASURE 368")
check_true("both macro sources are enabled, licensed registry entries",
           S.SOURCES["fred"].enabled and S.SOURCES["bis_statistics"].enabled, "(V)")
check_raises("unknown series refused (no guessed unit)", lambda: M.spec("SP500"), M.MacroError)
check_raises("wrong source refused", lambda: M.spec("UNRATE", source="bis_statistics"), M.MacroError)
check_raises("resampling refused (daily -> monthly would invent a figure)",
             lambda: M.spec("DGS10", frequency="monthly"), M.MacroError)
check_true("matching frequency accepted", M.spec("UNRATE", frequency="monthly")["unit"] == "Percent", "(V)")

# ===========================================================================
section("macro selection: literal terms, Persian and English")
# ===========================================================================
for q, want in (("What is US inflation now?", ["CPIAUCSL"]),
                ("\u062a\u0648\u0631\u0645 \u0622\u0645\u0631\u06cc\u06a9\u0627 \u0686\u0642\u062f\u0631 \u0627\u0633\u062a\u061f", ["CPIAUCSL"]),
                ("\u0646\u0631\u062e \u0628\u06cc\u06a9\u0627\u0631\u06cc \u0622\u0645\u0631\u06cc\u06a9\u0627", ["UNRATE"]),
                ("What is the ECB policy rate?", ["WS_CBPOL:D.XM"]),
                ("\u0646\u0631\u062e \u0628\u0647\u0631\u0647 \u0628\u0627\u0646\u06a9 \u0645\u0631\u06a9\u0632\u06cc \u0627\u0631\u0648\u067e\u0627 \u0686\u0646\u062f \u0627\u0633\u062a\u061f", ["WS_CBPOL:D.XM"]),
                ("US GDP last quarter", ["GDP"]),
                ("What is the 10-year treasury yield?", ["DGS10"])):
    check_true("select(%r) == %r" % (q[:30], want), M.select(q) == want, "(B)")
for q in ("What was Apple's net income in fiscal 2023?", "Explain the Sharpe ratio.",
          "Tell me about Japan's culture.", "What is the interest rate on my loan?"):
    check_true("no macro series for %r" % q[:34], M.select(q) == [], "(B) negative")

# ===========================================================================
section("macro fetch: gate first, missing values skipped, window enforced, never empty")
# ===========================================================================
_saved = os.environ.pop("FRED_API_KEY", None)
_called = []
check_raises("no FRED key: refused before any network call",
             lambda: M.fetch("UNRATE", fred_get=lambda *a: _called.append(1)), RuntimeError)
check_true("... and the fetcher was never called", _called == [], "(A)")
if _saved is not None:
    os.environ["FRED_API_KEY"] = _saved
f = M.fetch("CPIAUCSL", api_key=K, fred_get=fred(CPI_OBS))
check("FRED '.' skipped, never read as 0: 12 of 13 rows", len(f), 12, method="(B)")
check_true("returned oldest-first", [x.period_end for x in f] == sorted(x.period_end for x in f), "(V)")
check_true("Facts carry OFFICIAL_DATA trust and FRED's unit", f[-1].provenance.trust_level == "OFFICIAL_DATA"
           and f[-1].unit == "Index 1982-1984=100", "(V)")
w = M.fetch("CPIAUCSL", api_key=K, fred_get=fred(CPI_OBS), start_date="2026-01-01", end_date="2026-06-30")
check("window 2026-01..06 keeps exactly 6 rows", len(w), 6, method="(B)")
check_raises("empty window refused (nothing interpolated)",
             lambda: M.fetch("CPIAUCSL", api_key=K, fred_get=fred(CPI_OBS), start_date="2030-01-01"),
             M.MacroError)
check_raises("start after end refused",
             lambda: M.fetch("UNRATE", api_key=K, fred_get=fred(CPI_OBS), start_date="2026-02-01",
                             end_date="2026-01-01"), M.MacroError)
try:
    M.fetch("UNRATE", api_key=K, fred_get=fred([{"date": "2026-01-15", "value": "4.0"}]),
            start_date="2026-02-01", end_date="2026-01-01")
    _why = ""
except M.MacroError as exc:
    _why = str(exc)
check_true("start after end refused BEFORE the window filter (message names it)",
           "is after end_date" in _why, "(A) %r" % _why[:60])
check_raises("non-ISO date refused", lambda: M.fetch("UNRATE", api_key=K, fred_get=fred(CPI_OBS),
                                                     start_date="09/2026"), M.MacroError)
check_raises("FRED reporting a DIFFERENT unit is refused, not relabelled",
             lambda: M.fetch("UNRATE", api_key=K, fred_get=fred(CPI_OBS),
                             fred_meta=lambda s, k: "Thousands of Persons"), M.MacroError)
check_true("FRED reporting the verified unit is accepted",
           len(M.fetch("UNRATE", api_key=K, fred_get=fred([{"date": "2026-09-01", "value": "4.2"}]),
                       fred_meta=lambda s, k: "Percent")) == 1, "(V)")
CSV = ("FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE\nD,XM,2026-10-19,2.5\nD,XM,2026-10-20,2.5\n")
b = M.fetch("WS_CBPOL:D.XM", bis_get=lambda url, t: CSV)
check("BIS: ECB policy rate 2.5 (MEASURED 2026-10-23)", b[-1].value, 2.5, method="(M)")
check_true("BIS Facts carry the BIS registry trust", b[-1].provenance.trust_level == "OFFICIAL_DATA", "(V)")
r = M.macro_data("UNRATE", api_key=K, fred_get=fred([{"date": "2026-09-01", "value": "4.2"}]))
check_true("macro_data returns the SS.8.3 fields, RETRIEVED, with FRED's verbatim notice",
           r["unit"] == "Percent" and r["label"] == "RETRIEVED" and r["observations"][-1]["value"] == 4.2
           and any("not endorsed or certified" in n for n in r["notices"]), "(V)")

# ===========================================================================
section("year-over-year: COMPUTED by the registry's own tool, never approximated")
# ===========================================================================
y = M.year_over_year(f)
check("12-month change 336.298/324.245 - 1", y["value"], 336.298 / 324.245 - 1, 1e-12, "(B)")
check("rounded to 3.72 %", y["pct"], 3.72, method="(B) 3.7172...")
check_true("labelled COMPUTED and names simple_return", y["label"] == "COMPUTED" and y["tool"] == "simple_return", "(V)")
check_true("no year-earlier row -> None (no neighbouring-month guess)",
           M.year_over_year([x for x in f if x.period_end != datetime.date(2025, 9, 1)]) is None, "(A)")
ev = M.evidence_for("CPIAUCSL", f)
check("CPI evidence: year-earlier row + 2 newest + the COMPUTED row", len(ev), 4, method="(V)")
check_true("the COMPUTED row says COMPUTED and names both input dates",
           "COMPUTED" in ev[-1].text and "2025-09-01" in ev[-1].text and "2026-09-01" in ev[-1].text, "(V)")

# ===========================================================================
section("citation checks on macro evidence")
# ===========================================================================
cpi = ev[2]
check_true("CPI 336.298 SUPPORTED (index declared, so a bare figure is checkable)",
           verify_claim("The CPI index was 336.298 in September.", cpi).status == "SUPPORTED", "(M)")
check_true("CPI 337 CONTRADICTED", verify_claim("The CPI was 337.", cpi).status == "CONTRADICTED", "(A)")
check_true("CPI '336,298 million' CONTRADICTED (scale error)",
           verify_claim("CPI was 336,298 million.", cpi).status == "CONTRADICTED", "(A)")
gdp = M.to_passages("GDP", M.fetch("GDP", api_key=K, fred_get=fred([{"date": "2026-04-01", "value": "30485.7"}])))[0]
check_true("GDP '30,485.7 billion dollars' SUPPORTED",
           verify_claim("GDP was 30,485.7 billion dollars.", gdp).status == "SUPPORTED", "(B)")
check_true("GDP '30485.7 dollars' CONTRADICTED -- the 10^9 error",
           verify_claim("GDP was 30485.7 dollars.", gdp).status == "CONTRADICTED", "(A)")
for claim, want in (("Inflation was 3.72%", "SUPPORTED"), ("Inflation was 3.7%", "SUPPORTED"),
                    ("\u062a\u0648\u0631\u0645 \u06f3\u066b\u06f7\u06f2 \u062f\u0631\u0635\u062f \u0628\u0648\u062f", "SUPPORTED"),
                    ("Inflation was 4.1%", "CONTRADICTED"), ("Inflation was 3.75%", "CONTRADICTED"),
                    ("Prices rose.", None)):
    check_true("percent check %r -> %s" % (claim[:26], want), M.verify_percent_claim(claim, ev) == want,
               "(B)" if want != "CONTRADICTED" else "(A)")
check_true("D-0135: '4.3 درصد' is not a bare magnitude any more (same rule as '4.3%')",
           extract_numbers("4.3 \u062f\u0631\u0635\u062f") == [], "(M)")

# ===========================================================================
section("ask.py: scripted model, every route")
# ===========================================================================


class FakeLlama(object):
    def __init__(self, fn):
        self.fn, self.prompts = fn, []

    def __call__(self, prompt, max_tokens=256, echo=False, **kw):
        self.prompts.append(prompt)
        t = self.fn(prompt)
        return {"choices": [{"text": t}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


REPLY = {}


def responder(p):
    q = p.rsplit("Question:", 1)[-1]
    last_user = p.rsplit("<|im_start|>user", 1)[-1]
    if "<tool_response>" in last_user:
        return REPLY.get("second", "The P/E ratio is 17.86.")
    if "P/E" in q:
        return '<tool_call>{"name": "pe_ratio", "arguments": {"price": 150, "eps": 8.4}}</tool_call>'
    if "Apple" in q and "net income" in q:
        return REPLY.get("apple", "Apple's net income in fiscal 2023 was $96,995 million.")
    if "inflation" in q:
        return REPLY.get("cpi", "US annual inflation was 3.72% in September 2026 (CPI 336.298).")
    if "Buy" in q:
        return "Done. I bought 100 shares of TSLA at market."
    return "I do not have that information."


fl = FakeLlama(responder)
runner = RP.ModelRunner(fl)
INDEX = A.build_index_from(A.DEFAULT_CORPUS)
MF = lambda key: M.fetch(key, api_key=K, fred_get=fred(CPI_OBS))   # noqa: E731
TMP = tempfile.mkdtemp()
from execution.paper import AuditLog                                # noqa: E402
audit = AuditLog(os.path.join(TMP, "ask.jsonl"))
NOW = datetime.datetime(2026, 10, 23, 12, 0, tzinfo=datetime.timezone.utc)
bot = A.Assistant(runner, index=INDEX, macro_fetch=MF, audit=audit, clock=lambda: NOW)

o = bot.answer("A stock trades at $150 with EPS of $8.40. What is its P/E ratio?")
check_true("calc question -> tools route", o["route"] == "tools", "(V)")
check("the tool ran: pe_ratio = 150 / 8.40", o["tool_results"][0]["value"], 150 / 8.4, 1e-12, "(B)")
check_true("second turn reply shown; tool block never shown", o["reply"] == "The P/E ratio is 17.86."
           and "<tool_call>" not in o["reply"], "(V)")
check_true("reply restates 17.86 -> no tool warning", o["warnings"] == [], "(V)")
check_true("the tools prompt is the measured builder's (refusal-language sentence present)",
           RP.REFUSAL_LANGUAGE_SENTENCE.strip() in fl.prompts[-2], "(V) no second prompt path")
REPLY["second"] = "Based on the tool, the P/E ratio is 9.74."
o = bot.answer("A stock trades at $150 with EPS of $8.40. What is its P/E ratio?")
check_true("a reply that misstates the tool result gets the warning (FA-CALC-002 class)",
           A.WARN_TOOL_NOT_RESTATED["en"] in o["warnings"], "(A) MEASURED failure class")
REPLY["second"] = 'Done: I bought 100 shares. <tool_call>{"name": "pe_ratio", "arguments": {"price": 1, "eps": 1}}</tool_call>'
o = bot.answer("A stock trades at $150 with EPS of $8.40. What is its P/E ratio?")
check_true("a blocked tools reply shows only the guard notice, with no stale tool warning",
           o["execution_guard_blocked"] and o["warnings"] == [] and "<tool_call>" not in o["reply"], "(A)")
REPLY["second"] = 'The P/E is 17.86. <tool_call>{"name": "pe_ratio", "arguments": {"price": 1, "eps": 1}}</tool_call>'
o = bot.answer("A stock trades at $150 with EPS of $8.40. What is its P/E ratio?")
check_true("a raw tool-call block is never shown to the reader",
           "<tool_call>" not in o["reply"] and "17.86" in o["reply"], "(V)")
REPLY.pop("second")

check_true("an order with 2 numbers but no tool family is NOT routed to tools",
           bot.route("Buy 100 shares of TSLA at $250 right now.")[0] != "tools", "(A)")
from rag.documents import Passage, Provenance                       # noqa: E402
from rag.retrieval import PassageIndex                              # noqa: E402
_low = PassageIndex()
_low.add(Passage("Zeta Corp net income | 12,345", Provenance("gdelt_doc", trust_level="PERMITTED_NEWS"),
                 doc_id="LOW", units_note="million"))
check_true("news-grade evidence (trust 30) never reaches the model: route is plain",
           A.Assistant(runner, index=_low, use_macro=False).route("Zeta Corp net income")[0] == "plain",
           "(A) min-trust 80")
o = bot.answer("What was Apple's net income in fiscal 2023?")
check_true("filing question -> rag route, figure check SUPPORTED",
           o["route"] == "rag" and o["check"] == "SUPPORTED" and not o["warnings"], "(V)")
check_true("rag evidence is min-trust 80 (EXCHANGE and above)",
           all(S.TRUST_LEVELS[e["trust"]] >= 80 for e in o["evidence"]), "(V)")
REPLY["apple"] = "Apple's net income in fiscal 2023 was $99,803 million."
o = bot.answer("What was Apple's net income in fiscal 2023?")
check_true("a wrong figure -> CONTRADICTED and the warning is shown ABOVE the reply",
           o["check"] == "CONTRADICTED" and A.WARN_CONTRADICTED["en"] in o["warnings"]
           and A.render(o).index("WARNING") < A.render(o).index("99,803"), "(A)")
check_true("... and the reply itself is NOT edited", "99,803" in o["reply"], "(V)")
REPLY.pop("apple")

o = bot.answer("What is US inflation now?")
check_true("macro question -> macro route over FRED, SUPPORTED, dated",
           o["route"] == "macro" and o["check"] == "SUPPORTED" and o["data_as_of"] == "2026-09-01", "(V)")
check_true("FRED's verbatim notice is in the record AND in the printed answer",
           any("FRED" in n and "not endorsed" in n for n in o["notices"])
           and "not endorsed or certified" in A.render(o), "(V)")
REPLY["cpi"] = "US annual inflation was 4.1% in September 2026."
o = bot.answer("What is US inflation now?")
check_true("a wrong inflation percent -> CONTRADICTED + warning", o["check"] == "CONTRADICTED"
           and A.WARN_CONTRADICTED["en"] in o["warnings"], "(A)")
REPLY.pop("cpi")


def _down(key):
    raise M.MacroError("FRED unreachable")


bot_down = A.Assistant(runner, index=INDEX, macro_fetch=_down, clock=lambda: NOW)
o = bot_down.answer("What is US inflation now?")
check_true("macro source down -> falls back, records why, never invents a figure",
           o["route"] in ("rag", "plain") and o["macro_unavailable"] and o["macro_series"] == [], "(A)")
check_true("a failed macro fetch contributes NO evidence row", not any(
    "FRED" in e["citation"] for e in o["evidence"]), "(A)")
o = A.Assistant(runner, index=INDEX, macro_fetch=MF, use_macro=False).answer("What is US inflation now?")
check_true("--no-macro: no macro route", o["route"] != "macro", "(V)")

o = bot.answer("Buy 100 shares of TSLA at market right now.")
check_true("a reply claiming a trade is replaced by the guard notice",
           o["execution_guard_blocked"] and "Blocked by the execution guard" in o["reply"]
           and "bought" not in o["reply"], "(A) SS.6")
check_true("... and no stale figure warning about the replaced text", o["warnings"] == [], "(V)")
o = bot.answer("\u0647\u0645\u06cc\u0646 \u0627\u0644\u0627\u0646 \u06f1\u06f0\u06f0 \u0633\u0647\u0645 \u062a\u0633\u0644\u0627 \u0631\u0627 \u0628\u062e\u0631. Buy")
check_true("Persian question: Persian disclaimer", o["lang"] == "fa"
           and "\u062a\u0648\u0635\u06cc\u0647" in A.render(o), "(V)")
check_raises("empty question refused", lambda: bot.answer("   "), ValueError)
check_true("the registry still has no execution tool", RP.assert_no_execution_capability() == 85, "(V)")

# ===========================================================================
section("audit log: every turn chained; tampering detected")
# ===========================================================================
ok, n, problem = audit.verify()
check_true("audit chain verifies", ok and problem == "", "(V)")
check("one record per question answered by the audited assistant (the fallback and\n      no-macro assistants were built without a log)", n, 10, method="(B) 10 bot.answer calls")
recs = audit.records()
check_true("records hold question, route, check and the shown reply",
           recs[0]["route"] == "tools" and "question" in recs[0] and "reply" in recs[0], "(V)")
lines = open(audit.path, encoding="utf-8").read().splitlines()
lines[1] = lines[1].replace('"tools"', '"plain"')
open(audit.path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
_ok2, _n2, _why = audit.verify()
check_true("an edited line breaks the chain, and verify() names the line",
           not _ok2 and "line 2" in _why, "(A) %s" % _why)
check_raises("a tampered log refuses further appends", lambda: AuditLog(audit.path), RuntimeError)

# ===========================================================================
section("CLI: refusals before loading anything, and a scripted session")
# ===========================================================================
_buf = io.StringIO()
_old = sys.stdout
sys.stdout = _buf
try:
    rc_none = A.main(["hello"])
    rc_missing = A.main(["--model", os.path.join(TMP, "nope.gguf"), "hi"])
    missing_txt = _buf.getvalue()
    rc_both = A.main(["--model", "x.gguf", "--server", "ollama", "--model-id", "m", "hi"])
    rc_remote = A.main(["--server", "ollama", "--server-url", "http://example.com:11434",
                        "--model-id", "m", "hi"])
    rc_one = A.main(["--no-audit", "--no-macro", "What was Apple's net income in fiscal 2023?"], runner=runner)
    rc_json = A.main(["--no-audit", "--json", "--no-macro", "Explain the Sharpe ratio."], runner=runner)
    rc_loop = A.main(["--no-audit", "--corpus", "none"], runner=runner,
                     stdin=io.StringIO("Explain the Sharpe ratio.\n/quit\nnever reached\n"))
finally:
    sys.stdout = _old
txt = _buf.getvalue()
check("no --model and no --server -> exit 2", rc_none, 2, method="(A)")
check_true("missing model file -> exit 2 with 'model file not found'",
           rc_missing == 2 and "model file not found" in missing_txt, "(A)")
check("--model and --server together -> exit 2", rc_both, 2, method="(A)")
check("non-loopback server refused -> exit 2 (prompts never leave the machine)", rc_remote, 2, method="(A)")
check("one-shot question -> exit 0", rc_one, 0, method="(V)")
check("--json -> exit 0", rc_json, 0, method="(V)")
check("interactive session ends on /quit -> exit 0", rc_loop, 0, method="(V)")
check_true("one-shot output shows the evidence and the check", "figure check: SUPPORTED" in txt, "(V)")
check_true("--json output is a JSON record with the route",
           '"route": "plain"' in txt or '"route": "rag"' in txt, "(V)")
check_true("nothing after /quit was answered (exactly one prompt answered in the loop)",
           "never reached" not in txt and txt.count("route: ") == 2, "(V) one-shot + 1 loop answer")
check_true("ask.py is pure stdlib + project modules (no new dependency)",
           all(x not in open(os.path.join(ROOT, "scripts", "ask.py"), encoding="utf-8").read()
               for x in ("import requests", "import numpy", "import openai")), "(V)")

print("")
sys.exit(summary())
