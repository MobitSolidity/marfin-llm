# -*- coding: utf-8 -*-
"""
Phase 8 (D-0123): style controls from the user's Persian review, the
budgeted-thinking proposal, and the local-server runner (Ollama / LM Studio).

Offline. Servers are replaced by a recording fake that answers in each
backend's documented response shape. Style checks run against the RECORDED
Phase 7 replies, so they are pinned to what the user actually read.

Method codes: (A) defect must be caught/refused, (N) near-miss must pass,
(V) verified invariant, (M) from recorded measurement, (B) hand arithmetic.
"""
import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from _harness import check_true, summary            # noqa: E402
from llm import style as ST                          # noqa: E402
from llm import thinking as TH                       # noqa: E402
from llm import local_server as LS                   # noqa: E402
import phase4_lib as L                               # noqa: E402
import run_phase4 as RP                              # noqa: E402
import compare_quants as CQ                          # noqa: E402


def section(t):
    print("\n-- %s --" % t)


def raises(fn, exc=Exception):
    try:
        fn()
    except exc as e:
        return e
    return None


_Q5 = json.load(open(os.path.join(ROOT, "evidence", "phase7_q5km_merged_2026-10-17.json"),
                     encoding="utf-8"))
_Q4 = json.load(open(os.path.join(ROOT, "evidence", "phase7_q4km_merged_2026-10-17.json"),
                     encoding="utf-8"))
_CASES = {c["id"]: c for c in RP.load_jsonl(os.path.join(ROOT, "evals", "bilingual_eval_v1.jsonl"))}
_ALL = [(n, arm, r) for n, d in (("Q5", _Q5), ("Q4", _Q4))
        for arm, rows in d["arms"].items() for r in rows]

# ===========================================================================
section("user review (R10) recorded")
# ===========================================================================
_V = json.load(open(os.path.join(ROOT, "evidence", "phase7_persian_verdicts_2026-10-17.json"),
                    encoding="utf-8"))
check_true("24 Persian rows judged, tally Q4 10 / Q5 7 / equal 7",
           _V["n"] == 24 and _V["tally"] == {"Q4": 10, "Q5": 7, "EQUAL": 7}, "(M)")
check_true("every judged row is one the comparison listed as changed",
           {r["row"] for r in _V["rows"]} == set(json.load(open(os.path.join(
               ROOT, "evidence", "phase7_compare_q5_vs_q4_2026-10-17.json"),
               encoding="utf-8"))["persian_rows_changed"]), "(V)")

# ===========================================================================
section("style 1: LaTeX -> plain text (the user: 'no \\\\frac, only numbers')")
# ===========================================================================
_s, _n = ST.plain_math("$$ \\text{P/E} = \\frac{150}{8.40} $$")
check_true("\\frac and \\text become plain text with the numbers unchanged",
           _s == "P/E = 150 / 8.40" and _n == 1, "(B) got %r" % _s)
check_true("\\text inside a fraction is unwrapped, not parenthesised",
           ST.plain_math("$$\\frac{\\text{EPS}}{2}$$")[0] == "EPS / 2", "(B) mutation survivor D-0123")
check_true("an unlisted command (\\mathcal) is removed, not left for the reader",
           ST.plain_math("$$\\mathcal{R} = 0.1$$")[0] == "R = 0.1", "(B) mutation survivor D-0123")
check_true("nested fractions resolve",
           ST.plain_math("$$\\frac{\\frac{1}{2}}{3}$$")[0] == "(1 / 2) / 3", "(B)")
check_true("symbols map to their ordinary characters",
           ST.plain_math("$$a \\times b \\approx c \\leq d$$")[0] == "a × b ≈ c ≤ d", "(B)")
check_true("square root and superscript",
           ST.plain_math("$$\\sqrt{x^{2}}$$")[0] == "√(x^2)", "(B)")
check_true("dollar AMOUNTS are not mistaken for maths",
           ST.plain_math("Entry is $50 and stop is $60.")[0] == "Entry is $50 and stop is $60.",
           "(N)")
check_true("text without maths is returned byte-identical",
           ST.plain_math("قیمت ۱۵۰ دلار است.") == ("قیمت ۱۵۰ دلار است.", 0), "(N)")
check_true("an UNCLOSED $$ at a truncated end is rewritten too",
           not ST.has_latex(ST.plain_math("x:\n$$ 1.61^{0.2} \\approx")[0]), "(M) Q4 plain/FA-CALC-002")
_left = [(n, a, r["id"]) for n, a, r in _ALL if ST.has_latex(ST.plain_math(r.get("output") or "")[0])]
check_true("no LaTeX survives in ANY of the 148 recorded Phase 7 replies", _left == [],
           "(M) %s" % _left)
_had = sum(1 for n, a, r in _ALL if ST.has_latex(r.get("output") or ""))
check_true("...and 16 of them had LaTeX before (8 Q5 + 8 Q4; dollar amounts are not LaTeX)",
           _had == 16, "(M) got %d" % _had)
_chg = []
for n, arm, r in _ALL:
    if arm == "rag":
        continue
    o = r.get("output") or ""
    g1, g2 = L.grade_case(_CASES[r["id"]], o), L.grade_case(_CASES[r["id"]], ST.plain_math(o)[0])
    for k in ("value_ok", "abstention_ok", "fabricated", "banned_hits"):
        if g1.get(k) != g2.get(k):
            _chg.append((n, arm, r["id"], k))
check_true("the rewrite changes NO grade on any recorded plain/tools reply",
           _chg == [], "(M) numbers are never altered: %s" % _chg)

# ===========================================================================
section("style 2: language mixing")
# ===========================================================================
_mix = [(n, a, r["id"]) for n, a, r in _ALL if r.get("lang") == "fa" and ST.latin_runs(r.get("output"))]
check_true("exactly one recorded Persian reply has English sentences: Q4 plain/FA-CALC-002",
           _mix == [("Q4", "plain", "FA-CALC-002")], "(M) %s" % _mix)
check_true("key terms in parentheses are allowed",
           ST.latin_runs("نسبت قیمت به سود (Price to Earnings Ratio) برابر ۱۷ است.") == [], "(N)")
check_true("three Latin words in a row are a term, not a sentence",
           ST.latin_runs("سهم Apple Inc Common کاهش یافت.") == [], "(N)")
check_true("a whole English sentence inside a Persian reply is flagged",
           len(ST.latin_runs("پاسخ: The calculation steps are as follows here.")) == 1, "(A)")
check_true("LaTeX inside $...$ is not counted as English",
           ST.latin_runs("فرمول $\\text{Ending Value over Beginning Value}$ است") == [], "(N)")

# ===========================================================================
section("style 3: incomplete answers = budget exhausted")
# ===========================================================================
def _ct(r):
    m = r.get("metrics") or {}
    return (m.get("second_turn") or m).get("completion_tokens")
_hits = {n: sorted("%s/%s" % (a, r["id"]) for nn, a, r in _ALL if nn == n
                   and ST.hit_budget(_ct(r), 512)) for n in ("Q5", "Q4")}
check_true("the rows the user called incomplete all hit the 512 budget",
           {"plain/FA-LANG-001", "tools/FA-LANG-001"} <= set(_hits["Q5"])
           and {"plain/FA-LANG-001", "tools/FA-LANG-001"} <= set(_hits["Q4"]), "(M)")
check_true("7 budget hits on Q5_K_M, 6 on Q4_K_M", (len(_hits["Q5"]), len(_hits["Q4"])) == (7, 6),
           "(M) %s" % _hits)
check_true("hit_budget: at budget True, under False, unknown None",
           ST.hit_budget(512, 512) is True and ST.hit_budget(227, 512) is False
           and ST.hit_budget(None, 512) is None, "(V)")

# ===========================================================================
section("--style in the harness (opt-in; recorded runs unchanged)")
# ===========================================================================
check_true("without --style every prompt is byte-identical to before",
           RP.build_plain_prompt("q?") == RP.build_plain_prompt("q?", style=False)
           and ST.STYLE_RULES not in RP.build_plain_prompt("q?"), "(V)")
check_true("with --style the three rules are in the plain, tools and rag system prompts",
           all(ST.STYLE_RULES in str(p) for p in (
               RP.build_plain_prompt("q?", style=True),
               RP.build_tools_prompt("q?", [], style=True),
               RP.build_rag_prompt("q?", [], style=True))), "(V)")
check_true("style rules come after the refusal-language sentence (both on)",
           str(RP.build_plain_prompt("q?", refusal_language=True, style=True)).index(
               RP.REFUSAL_LANGUAGE_SENTENCE) < str(RP.build_plain_prompt(
                   "q?", refusal_language=True, style=True)).index(ST.STYLE_RULES), "(V)")
check_true("the style rules ask for plain formulas, the question's language, and brevity",
           "never LaTeX" in ST.STYLE_RULES and "language of the question" in ST.STYLE_RULES
           and "concise" in ST.STYLE_RULES, "(V)")
_t, _rec = RP._apply_style("x $$\\frac{1}{2}$$", "fa", {"completion_tokens": 512}, 512, True)
check_true("_apply_style rewrites and records latex / latin_runs / hit_budget",
           _t == "x 1 / 2" and _rec == {"latex_spans_rewritten": 1, "latin_runs": [],
                                        "hit_budget": True}, "(V) %r %r" % (_t, _rec))
check_true("_apply_style off: text untouched, no record",
           RP._apply_style("$$\\frac{1}{2}$$", "fa", {}, 512, False) == ("$$\\frac{1}{2}$$", None),
           "(V)")
check_true("_apply_style reads the SECOND turn's token count when there is one",
           RP._apply_style("a", "en", {"first_turn": {"completion_tokens": 9},
                                       "second_turn": {"completion_tokens": 512}}, 512, True)[1]
           ["hit_budget"] is True, "(A)")

# ===========================================================================
section("thinking: router and budgeted two-call generation")
# ===========================================================================
check_true("off-mode prefix IS the prefill every recorded run used",
           TH.assistant_prefix("off") == RP.FORCED_CLOSED_THINK, "(V) D-0091")
check_true("budgeted prefix opens the block", TH.assistant_prefix("budgeted") == "<think>\n", "(V)")
check_true("unbounded 'on' is not offered (D-0085: it never terminates)",
           bool(raises(lambda: TH.assistant_prefix("on"), ValueError)), "(A)")
check_true("a tool-answerable question is routed OFF even if its category would think",
           TH.route("multi_step_analysis", tool_available=True) == "off", "(V)")
check_true("a question with RAG evidence is routed OFF", TH.route("multi_step_analysis",
                                                                   has_evidence=True) == "off", "(V)")
check_true("open multi-step analysis with no tool is BUDGETED",
           TH.route("multi_step_analysis") == "budgeted", "(V)")
check_true("every category of the eval set is routed OFF",
           {TH.route(c["category"]) for c in _CASES.values()} == {"off"}, "(V)")
check_true("an unknown category defaults to OFF (thinking must be earned)",
           TH.route("something_new") == "off", "(A)")

_calls = []


def _never_closes(prompt, n):
    _calls.append((prompt, n))
    return ("hmm " * n, n) if prompt.endswith("<think>\n") else ("The answer is 10%.", 6)


_r = TH.generate_budgeted(_never_closes, "<|im_start|>assistant\n", 64, 128)
check_true("a model that never closes its thinking STILL gives an answer (D-0085 cannot recur)",
           _r["answer"] == "The answer is 10%." and _r["forced_close"] is True, "(A)")
check_true("the thinking call is capped at think_budget, the answer call at answer_budget",
           [c[1] for c in _calls] == [64, 128], "(V)")
check_true("the second call continues from the model's reasoning with the block force-closed",
           _calls[1][0].endswith("hmm \n</think>\n\n"), "(V)")
_calls.clear()


def _closes(prompt, n):
    _calls.append((prompt, n))
    if prompt.endswith("<think>\n"):
        return ("short plan</think>\n\nCAGR is ", 9)
    return ("10%.", 3)


_r2 = TH.generate_budgeted(_closes, "P", 64, 128)
check_true("a model that closes on its own is not force-closed, and its partial answer is kept",
           _r2["forced_close"] is False and _r2["answer"] == "CAGR is 10%."
           and _r2["reasoning"] == "short plan", "(N) %r" % _r2)
check_true("budgets below 1 are refused",
           bool(raises(lambda: TH.generate_budgeted(_closes, "P", 0, 10), ValueError)), "(A)")

# ===========================================================================
section("local server: requests (Ollama raw / LM Studio completions)")
# ===========================================================================
_u, _p = LS.build_request("ollama", None, "marfin-q4", "PROMPT", 512, 0.0, 7, ["<|im_end|>"], 16384, 6)
check_true("Ollama: /api/generate with raw=true (no server-side template)",
           _u == "http://127.0.0.1:11434/api/generate" and _p["raw"] is True
           and _p["prompt"] == "PROMPT" and _p["stream"] is False, "(V)")
check_true("Ollama: greedy, seed, budget, stop, ctx, threads all sent as options",
           _p["options"] == {"temperature": 0.0, "seed": 7, "num_predict": 512,
                             "stop": ["<|im_end|>"], "num_ctx": 16384, "num_thread": 6,
                             "repeat_penalty": 1.0}, "(V)")
_u2, _p2 = LS.build_request("lmstudio", None, "qwen3.5-4b", "PROMPT", 512, 0.0, 7, ["<|im_end|>"])
check_true("LM Studio: /v1/completions (text completion, no chat template)",
           _u2 == "http://127.0.0.1:1234/v1/completions" and _p2["prompt"] == "PROMPT"
           and "messages" not in _p2, "(V)")
for bad in ("http://192.168.1.5:11434", "https://example.com", "http://evil.localhost.com:1"):
    check_true("non-loopback server %s is REFUSED" % bad,
               bool(raises(lambda: LS.build_request("ollama", bad, "m", "p", 1, 0, 1, []),
                           LS.ServerError)), "(A)")
check_true("unknown backend is refused",
           bool(raises(lambda: LS.build_request("vllm", None, "m", "p", 1, 0, 1, []),
                       LS.ServerError)), "(A)")
check_true("no model id is refused",
           bool(raises(lambda: LS.build_request("ollama", None, " ", "p", 1, 0, 1, []),
                       LS.ServerError)), "(A)")

# ===========================================================================
section("local server: responses and the ModelRunner contract")
# ===========================================================================
_t, _m = LS.parse_response("ollama", {"response": "hi", "eval_count": 50,
                                      "eval_duration": 10_000_000_000,
                                      "prompt_eval_count": 1963,
                                      "prompt_eval_duration": 30_000_000_000,
                                      "done_reason": "stop"}, 41.0)
check_true("Ollama timings come from the server: 50 tokens / 10 s = 5.0 tok/s, prefill 30 s",
           _t == "hi" and _m["decode_tps"] == 5.0 and _m["prefill_seconds"] == 30.0
           and _m["timing_source"] == "server", "(B)")
_t2, _m2 = LS.parse_response("lmstudio", {"choices": [{"text": "yo", "finish_reason": "length"}],
                                          "usage": {"completion_tokens": 20,
                                                    "prompt_tokens": 5}}, 4.0)
check_true("LM Studio decode rate is labelled wall-clock (it includes prefill)",
           _m2["decode_tps"] == 5.0 and "wall_clock" in _m2["timing_source"], "(V)")
check_true("a reply without the backend's text field is an ERROR, not an empty answer",
           bool(raises(lambda: LS.parse_response("ollama", {"done": True}, 1), LS.ServerError))
           and bool(raises(lambda: LS.parse_response("lmstudio", {"choices": []}, 1),
                           LS.ServerError)), "(A)")


class _FakeServer(object):
    def __init__(self, reply):
        self.reply, self.seen = reply, []

    def __call__(self, url, payload, timeout):
        self.seen.append((url, payload))
        return {"response": self.reply, "eval_count": 8, "eval_duration": 2e9,
                "prompt_eval_count": 10, "prompt_eval_duration": 1e9, "done_reason": "stop"}


_fs = _FakeServer("<think>reasoning</think>\n\nBuy nothing.")
_sr = LS.ServerRunner("ollama", "marfin-q4", post=_fs)
_ans, _met = _sr.generate(RP.build_plain_prompt("q?"))
check_true("ServerRunner strips <think> with the same splitter as every runner",
           _ans == "Buy nothing." and _met["had_thinking"] is True
           and _sr.thinking_replies == 1, "(V)")
check_true("ServerRunner sends the harness's EXACT rendered prompt (prefill included)",
           _fs.seen[0][1]["prompt"] == str(RP.build_plain_prompt("q?"))
           and _fs.seen[0][1]["prompt"].endswith(RP.FORCED_CLOSED_THINK), "(V)")
check_true("ServerRunner refuses a non-loopback URL at construction",
           bool(raises(lambda: LS.ServerRunner("ollama", "m", base_url="http://10.0.0.2:11434"),
                       LS.ServerError)), "(A)")


class _ScriptedServer(object):
    def __call__(self, url, payload, timeout):
        q = payload["prompt"].split("Question: ")[-1]
        return {"response": "I do not have the information needed to answer this question."
                if "price" in q.lower() else "The answer is 17.86.",
                "eval_count": 12, "eval_duration": 3e9}


_cases = [c for c in _CASES.values() if c["id"] in ("EN-CALC-001", "EN-ABST-001")]
_rows = RP.run_arm_plain(LS.ServerRunner("ollama", "m", post=_ScriptedServer()), _cases,
                         {}, refusal_language=True, execution_guard=True, style=True)
check_true("the plain arm runs end to end on a server runner and is graded",
           len(_rows) == 2 and all("style" in r for r in _rows), "(V)")

# ===========================================================================
section("merge and compare know the runtime")
# ===========================================================================
import merge_phase4 as MG                            # noqa: E402
_d1 = copy.deepcopy(_Q4)
_d1["arms"] = {"plain": _d1["arms"]["plain"]}
_d2 = copy.deepcopy(_Q4)
_d2["arms"] = {"tools": _d2["arms"]["tools"]}
_d2["server"] = {"backend": "ollama"}
import tempfile                                      # noqa: E402
import shutil                                        # noqa: E402
import atexit                                        # noqa: E402
_tmp = tempfile.mkdtemp(prefix="phase8_")
atexit.register(shutil.rmtree, _tmp, True)
_paths = []
for i, d in enumerate((_d1, _d2)):
    pth = os.path.join(_tmp, "a%d.json" % i)
    json.dump(d, open(pth, "w", encoding="utf-8"))
    _paths.append(pth)
_merged, _probs = MG.merge(_paths)
check_true("an Ollama arm and an in-process arm are NOT merged as one run",
           any("disagree" in x for x in _probs), "(A)")
_srv = copy.deepcopy(_Q4)
_srv["server"] = {"backend": "ollama"}
check_true("same weights, different runtime: compared as RUNTIME, not repeatability",
           CQ.compare(_Q4, _srv)["kind"].startswith("RUNTIME"), "(V)")
_srv5 = copy.deepcopy(_srv)
check_true("different weights AND runtime: REFUSED (effects cannot be separated)",
           CQ.compare(_Q5, _srv5)["label"] == "REFUSED", "(A)")
check_true("in-process vs in-process stays QUANTISATION",
           CQ.compare(_Q5, _Q4)["kind"] == "QUANTISATION", "(V)")

# ===========================================================================
section("compare_style: isolates the --style effect")
# ===========================================================================
import compare_style as CS                           # noqa: E402
_d4 = CS.defects(_Q4)
check_true("Phase 7 Q4_K_M baseline defects: 8 LaTeX, 1 Persian-with-English, 6 budget hits",
           (len(_d4["latex_in_model_text"]), len(_d4["latin_runs_fa"]), len(_d4["hit_budget"]))
           == (8, 1, 6), "(M)")
_after = copy.deepcopy(_Q4)
_after["model"]["prompt_options"] = dict(_after["model"]["prompt_options"], style=True)
for r in _after["arms"]["plain"]:
    r["output"] = ST.plain_math(r.get("output") or "")[0]
_cs = CS.compare(_Q4, _after)
check_true("same weights/runtime, style off -> on: accepted as STYLE",
           _cs["label"] == "COMPUTED_FROM_MEASURED" and _cs["kind"].startswith("STYLE"), "(V)")
check_true("LaTeX the MODEL wrote is still counted after the harness rewrote it "
           "(the rule's effect is not credited to the rewrite)",
           _cs["defect_counts"]["latex_in_model_text"][1] == 8, "(A)")
check_true("...while LaTeX SHOWN to the user drops for the rewritten arm",
           _cs["defect_counts"]["latex_shown_to_user"][1] < 8, "(V)")
check_true("same run twice is refused (no style change)",
           CS.compare(_Q4, _Q4)["label"] == "REFUSED", "(A)")
check_true("different weights are refused", CS.compare(_Q5, _after)["label"] == "REFUSED", "(A)")
_svr = copy.deepcopy(_after)
_svr["server"] = {"backend": "ollama"}
check_true("a runtime change is refused", CS.compare(_Q4, _svr)["label"] == "REFUSED", "(A)")
_oth = copy.deepcopy(_after)
_oth["model"]["prompt_options"]["min_trust"] = 0
check_true("another prompt option changing is refused",
           CS.compare(_Q4, _oth)["label"] == "REFUSED", "(A)")
_rg = copy.deepcopy(_after)
_rv = [r for r in _rg["arms"]["plain"] if r.get("value_ok") is True][0]
_rv["value_ok"] = False
check_true("a row the style rules broke is listed as a REGRESSION",
           any(e["row"] == "plain/" + _rv["id"] for e in CS.compare(_Q4, _rg)["regressions"]), "(A)")

# ===========================================================================
section("deploy/ollama/Modelfile matches the harness")
# ===========================================================================
_mf = open(os.path.join(ROOT, "deploy", "ollama", "Modelfile"), encoding="utf-8").read()
check_true("SYSTEM is the harness system prompt with refusal-language and style rules",
           _mf.split('SYSTEM """', 1)[1].split('"""', 1)[0]
           == RP.system_base(True) + ST.STYLE_RULES, "(V)")
check_true("TEMPLATE pre-closes the think block exactly as every measured run did",
           RP.FORCED_CLOSED_THINK in _mf.split('TEMPLATE """', 1)[1].split('"""', 1)[0], "(V)")
check_true("FROM is the Q4_K_M chosen in D-0123, and its sha256 is stated",
           "Qwen3.5-4B-Q4_K_M.gguf" in _mf.split("FROM", 1)[1].split("\n", 1)[0]
           and "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4" in _mf, "(V)")
for _k, _v in (("temperature", "0"), ("seed", "20260831"), ("num_ctx", "16384"),
               ("num_predict", "512")):
    check_true("PARAMETER %s %s, as measured" % (_k, _v),
               "PARAMETER %s %s\n" % (_k, _v) in _mf, "(V)")
check_true("both stop strings are set",
           'PARAMETER stop "<|im_end|>"' in _mf and 'PARAMETER stop "<|im_start|>user"' in _mf, "(V)")

# ===========================================================================
section("D-0124: fixes from the Phase 8 run (2026-10-18)")
# ===========================================================================
import glob as _glob                                   # noqa: E402
import merge_phase4 as MG8                             # noqa: E402
import grade_merged as GM8                             # noqa: E402
_eval_text = "".join(open(f, encoding="utf-8").read()
                     for f in _glob.glob(os.path.join(ROOT, "evals", "*.jsonl")))
check_true("the style example is NOT an eval answer (was 150 / 8.40 = 17.86, EN/FA-CALC-001)",
           "150 / 8.40" not in ST.STYLE_RULES and "17.86" not in ST.STYLE_RULES, "(A)")
check_true("the new example's numbers (240, 12 -> 20) appear in no eval file",
           "240" not in _eval_text and "Ratio = 240" in ST.STYLE_RULES, "(V)")
check_true("the language rule names both directions (EN rows were answered in Persian)",
           "English question gets an English answer" in ST.STYLE_RULES, "(V)")
_tp = str(RP.build_tools_prompt("q?", [], style=True))
check_true("tools arm with --style says: call the tool first (tool calls fell 8/10 -> 2/10)",
           ST.STYLE_TOOLS_NOTE in _tp and _tp.index(ST.STYLE_RULES) < _tp.index(ST.STYLE_TOOLS_NOTE),
           "(V)")
check_true("the tool note is NOT in the plain or rag prompts, nor without --style",
           ST.STYLE_TOOLS_NOTE not in str(RP.build_plain_prompt("q?", style=True))
           and ST.STYLE_TOOLS_NOTE not in str(RP.build_rag_prompt("q?", [], style=True))
           and ST.STYLE_TOOLS_NOTE not in str(RP.build_tools_prompt("q?", [])), "(A)")
check_true("without --style the tools prompt is unchanged (recorded runs reproduce)",
           str(RP.build_tools_prompt("q?", [])) == str(RP.build_tools_prompt("q?", [], style=False)),
           "(V)")
_u3, _p3 = LS.build_request("lmstudio", None, "m", "P", 5, 0.0, 7, [])
check_true("repeat_penalty 1.0 is sent to BOTH servers (their default is 1.1)",
           _p3["repeat_penalty"] == 1.0 and LS.REPEAT_PENALTY == 1.0, "(V)")
check_true("the Modelfile pins repeat_penalty 1.0", "PARAMETER repeat_penalty 1.0\n" in _mf, "(V)")
check_true("the Modelfile documents that interactive `ollama run` needs --think=false",
           "--think=false" in _mf, "(V)")


class _CountSrv(object):
    def __init__(self):
        self.prompts = []

    def __call__(self, url, payload, timeout):
        self.prompts.append(payload["prompt"])
        n = len(payload["prompt"]) // 4
        return {"response": "x", "eval_count": 1, "eval_duration": 1e9,
                "prompt_eval_count": n, "prompt_eval_duration": 1e9}


_cs8 = _CountSrv()
_srv = LS.ServerRunner("ollama", "m", post=_cs8)
check_true("ServerRunner counts tokens with the server (prompt_eval_count)",
           _srv.count_tokens("abcdefgh") == 2, "(V)")
check_true("a server runner records sampling as applied, not unknown",
           _srv.sampling_supported is True and _srv.is_server is True, "(V)")
_lat = RP.measure_latency(_srv)
check_true("server TTFT prompt is TOKENIZED via the server (was 'estimated', 4433 tokens)",
           _lat["ttft_prompt_built_by"] == "tokenized"
           and 1638 <= _lat["ttft_prompt_tokens"] <= 2560, "(B) %r" % _lat["ttft_prompt_tokens"])
_lat2 = RP.measure_latency(_srv)
_probes = [p for p in _cs8.prompts if p.startswith("[ttft probe")]
check_true("each server TTFT probe is unique, so the KV cache cannot serve it (1.04 s cache hit)",
           len(_probes) == 2 and _probes[0] != _probes[1], "(A)")
_dsrv = {"label": "MEASURED_LOCAL_SERVER", "server": {"backend": "ollama"},
         "timestamp": "t", "arms": {"plain": []}, "summaries": {"plain": {}},
         "model": {"file": "f", "ctx": 1, "threads": 1, "max_tokens": 1,
                   "tool_call_cap": 8, "identity": {"sha256": "s"}},
         "latency": {"ttft_seconds": 1, "decode_tokens_per_sec": 1},
         "peak_rss_gib": 0.05,
         "peak_rss_label": "MEASURED_PEAK_HARNESS_ONLY_MODEL_IN_SERVER_PROCESS"}
import tempfile as _tf                                 # noqa: E402
_td = _tf.mkdtemp()
_fa, _fb = os.path.join(_td, "a.json"), os.path.join(_td, "b.json")
_db = json.loads(json.dumps(_dsrv)); _db["arms"] = {"rag": []}; _db["summaries"] = {"rag": {}}
json.dump(_dsrv, open(_fa, "w")); json.dump(_db, open(_fb, "w"))
_mo = os.path.join(_td, "m.json")
MG8.main([_fa, _fb, "--out", _mo])
_merged = json.load(open(_mo))
check_true("merge keeps the server block (it was dropped: Ollama merged looked in-process)",
           (_merged.get("server") or {}).get("backend") == "ollama", "(V)")
_g = GM8.grade_one("peak_rss_8k_gib_max", 6.0, GM8.SPEC["peak_rss_8k_gib_max"], _merged)
check_true("a harness-only RSS (0.05 GiB) is UNMEASURED, not a PASS",
           _g["verdict"] == "UNMEASURED", "(A) %r" % _g["verdict"])
_g2 = GM8.grade_one("peak_rss_8k_gib_max", 6.0, GM8.SPEC["peak_rss_8k_gib_max"],
                    {"peak_rss_gib": 4.71, "peak_rss_label": "MEASURED_PEAK"})
check_true("an in-process RSS is still graded (4.71 <= 6.0 PASS)", _g2["verdict"] == "PASS", "(V)")

print("")
sys.exit(summary())
