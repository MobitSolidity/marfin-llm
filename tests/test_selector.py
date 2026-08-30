#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tool-selector verification (D-0023 / Q9).

The selector is correctness-relevant, not an optimization. If it drops the tool
a query needed, the model has no way to compute the answer and may fabricate
one -- the exact failure SS.0B forbids. So the tests here are weighted heavily
toward RECALL, and the recall probes are deliberately HELD OUT: they use
jargon-free paraphrases and Persian-only phrasing that were not used to write
the keyword lists.

Verification methods used:
  (A) measured   -- token costs tokenized with the real Qwen3 tokenizer
  (C) invariant  -- recall, monotonicity, fallback behaviour
  (D) must-hold  -- integrity properties that make silent failure impossible

Run: python3 tests/test_selector.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from _harness import check, check_true, section, summary  # noqa: E402
from tools.selector import (  # noqa: E402
    CONTEXT_TARGET, FAMILIES, MEASURED_ALL_TOKENS, MEASURED_FAMILY_TOKENS,
    NAME_KEYWORDS, TOOL_FAMILY, UNCLASSIFIED, schemas_for, score_families,
    select_families, select_tools,
)
from tools.registry import tool_names  # noqa: E402

HERE = os.path.dirname(__file__)

# ---------------------------------------------------------------------------
section("integrity -- no tool may be invisible to routing")

# (D) A tool that belongs to no family would be silently unreachable through
# the selector. That is a fabrication risk, so it must be impossible.
check_true("every registered tool has a family", not UNCLASSIFIED,
           method="(D) integrity: %s" % (sorted(UNCLASSIFIED) or "none"))
check("family map covers all tools", len(TOOL_FAMILY), len(tool_names()),
      method="(D) integrity")
check_true("all families are known names",
           set(TOOL_FAMILY.values()) <= set(FAMILIES), method="(D)")

# (D) The safety net for unclassified tools is currently DORMANT -- nothing is
# unclassified, so deleting it would break nothing and no test would notice.
# Mutation testing caught exactly that. Simulate a tool that escaped the family
# map and assert it is still exposed, so the net is verified rather than
# merely present.
import tools.selector as _sel  # noqa: E402

_saved_map = dict(_sel.TOOL_FAMILY)
try:
    orphan = sorted(_sel.TOOL_FAMILY)[0]
    del _sel.TOOL_FAMILY[orphan]
    exposed = _sel.tools_for_families(["technicals"])
    check_true("a tool with no family is still exposed", orphan in exposed,
               method="(D) simulated orphan %r" % orphan)
finally:
    _sel.TOOL_FAMILY.clear()
    _sel.TOOL_FAMILY.update(_saved_map)
check_true("family map restored after orphan test",
           _sel.TOOL_FAMILY == _saved_map, method="(D) integrity")

# ---------------------------------------------------------------------------
section("recall -- HELD-OUT queries must reach the right tool")

# These paraphrases were NOT used to design the keyword lists. Three of them
# failed on first run (see D-0026); they are kept precisely because they broke
# the selector once.
HELD_OUT = [
    ("what is this company worth", "dcf"),
    ("is the stock expensive relative to profits", "pe_ratio"),
    ("how much should I buy so I only lose 2% if stopped out", "position_size"),
    ("is it overbought right now", "rsi"),
    ("how much does the bond move if rates rise 1bp", "dv01"),
    ("what is my option worth", "black_scholes"),
    ("how sensitive is the option to the underlying", "delta"),
    ("worst peak to trough loss", "max_drawdown"),
    ("should I be worried about how much this thing swings",
     "annualized_volatility"),
    ("چقدر باید بخرم که بیشتر از ۲ درصد ضرر نکنم", "position_size"),
    ("این سهم گران است یا ارزان", "pe_ratio"),
    ("قیمت اوراق با نرخ بازده ۵ درصد چقدر است", "bond_price"),
    ("نوسان ضمنی اختیار خرید چقدر است", "implied_volatility"),
    ("ارزش ذاتی شرکت را با جریان نقدی تنزیل شده حساب کن", "dcf"),
    ("compare the option premium to the bond yield", "black_scholes"),
]
for q, want in HELD_OUT:
    got = select_tools(q)["tools"]
    check_true("recall: %s" % q[:44], want in got,
               method="(C) held-out; want %s" % want)

# ---------------------------------------------------------------------------
section("recall -- the bilingual eval set")

path = os.path.join(HERE, "..", "evals", "bilingual_eval_v1.jsonl")
rows = [json.loads(l) for l in open(path, encoding="utf-8")]
registered = set(tool_names())

# (D) The eval set once expected `price_to_earnings` while the registry had
# `pe_ratio`. Nothing caught it because nothing compared the two. Now something
# does: eval/registry drift fails the suite.
drift = [r["id"] for r in rows
         if r.get("expected_tool") and r["expected_tool"] not in registered]
check_true("eval expected_tool names all exist in registry", not drift,
           method="(D) anti-drift: %s" % (drift or "clean"))

routable = [r for r in rows if r.get("expected_tool")]
missed = [r["id"] for r in routable
          if r["expected_tool"] not in select_tools(r["prompt"])["tools"]]
check_true("selector recalls every eval case", not missed,
           method="(C) %d cases; missed %s" % (len(routable), missed or "none"))

fa = [r for r in routable if r.get("lang") == "fa"]
fa_missed = [r["id"] for r in fa
             if r["expected_tool"] not in select_tools(r["prompt"])["tools"]]
check_true("Persian recall equals English recall", not fa_missed,
           method="(C) %d Persian cases" % len(fa))

# ---------------------------------------------------------------------------
section("fallback -- an unmatched query must never strand the model")

s = select_tools("hello, can you help me")
check_true("no-signal query still returns tools", s["n_tools"] > 0, method="(C)")
check_true("no-signal query flags fallback", s["fallback_used"] is True,
           method="(C)")
check_true("no-signal query reports low confidence",
           s["confidence"] == "low", method="(C) %s" % s["confidence"])
check_true("empty query does not raise",
           select_tools("")["n_tools"] > 0, method="(D)")
check_true("None-safe", select_tools(None)["n_tools"] > 0, method="(D)")

# (C) Risk sizing is mandatory under SS.6.3, so returns_risk is always present.
for q in ["what is my option worth", "rsi please", "bond duration", "", "سلام"]:
    check_true("returns_risk always included: %r" % q[:20],
               "position_size" in select_tools(q)["tools"], method="(C) SS.6.3")

# ---------------------------------------------------------------------------
section("word boundaries -- short tokens must not match inside words")

# (D) The regression that motivated the fix: "iv" matched inside "relative",
# routing a valuation question to derivatives.
check("'relative' does not trigger derivatives via 'iv'",
      score_families("is the stock expensive relative to profits")["derivatives"],
      0, method="(D) regression D-0026")
check("'variance' does not trigger 'var'",
      score_families("explain variance")["returns_risk"], 0,
      method="(D) regression")
check("'parent company' does not trigger 'par'",
      score_families("the parent company")["fixed_income"], 0,
      method="(D) regression")
# ...but genuine standalone usage must still match.
check_true("standalone 'var' still matches",
           score_families("compute VaR at 95%")["returns_risk"] > 0,
           method="(C) boundary must not over-correct")
check_true("standalone 'iv' still matches",
           score_families("what is the IV")["derivatives"] > 0, method="(C)")

# (D) Persian compounds are written three ways. Mutation testing showed the
# keyword list stored ZWNJ forms while the query was de-ZWNJ'd, so the ZWNJ
# spelling could never match. All three spellings must score identically.
ZWNJ = "\u200c"
spellings = {
    "zwnj": "\u0627\u0631\u0632\u0634" + ZWNJ + "\u06af\u0630\u0627\u0631\u06cc \u0634\u0631\u06a9\u062a",
    "space": "\u0627\u0631\u0632\u0634 \u06af\u0630\u0627\u0631\u06cc \u0634\u0631\u06a9\u062a",
    "joined": "\u0627\u0631\u0632\u0634\u06af\u0630\u0627\u0631\u06cc \u0634\u0631\u06a9\u062a",
}
for label, text in spellings.items():
    check_true("Persian compound (%s) reaches valuation" % label,
               score_families(text)["valuation"] > 0,
               method="(D) regression D-0026")
check_true("all three Persian spellings agree",
           len({score_families(t)["valuation"] > 0
                for t in spellings.values()}) == 1, method="(C)")
for label, text in spellings.items():
    check_true("Persian compound (%s) routes to a valuation tool" % label,
               "dcf" in select_tools(text)["tools"], method="(C)")

# ---------------------------------------------------------------------------
section("token budget -- MEASURED, and the saving must be real")

# (A) These constants are measured with the real tokenizer against the real
# chat template. Pinning them means a future tool addition that blows the
# budget fails a test instead of degrading Phase 3 silently.
check("all-tools cost is the measured 8920", MEASURED_ALL_TOKENS, 8920,
      method="(A) real Qwen3 tokenizer")
check_true("every family has a measured cost",
           all(f in MEASURED_FAMILY_TOKENS for f in FAMILIES), method="(A)")

worst = max(select_tools(q)["estimated_tokens"] for q, _ in HELD_OUT)
check_true("worst-case subset still beats the full catalogue",
           worst < MEASURED_ALL_TOKENS,
           method="(A) worst %d < %d" % (worst, MEASURED_ALL_TOKENS))
check_true("worst-case subset leaves >50%% of context for RAG",
           worst < 0.50 * CONTEXT_TARGET,
           method="(A) %d of %d" % (worst, CONTEXT_TARGET))

mean = sum(select_tools(r["prompt"])["estimated_tokens"]
           for r in rows) / float(len(rows))
check_true("mean eval-set cost under 25% of context",
           mean < 0.25 * CONTEXT_TARGET, method="(A) mean %.0f" % mean)
check_true("mean saving over 5000 tokens",
           MEASURED_ALL_TOKENS - mean > 5000,
           method="(A) saves %.0f" % (MEASURED_ALL_TOKENS - mean))

# ---------------------------------------------------------------------------
section("estimates must not under-predict the real rendered cost")

# (A) A budget that under-predicts is worse than no budget: it authorises a
# prompt that then overflows. Verified against the real template, so the
# estimate is required to be conservative.
tok_path = "/tmp/qwen3_tokenizer.json"
cfg_path = "/tmp/qwen3_tokcfg.json"
if os.path.exists(tok_path) and os.path.exists(cfg_path):
    from tokenizers import Tokenizer
    from jinja2 import Template
    tk = Tokenizer.from_file(tok_path)
    tpl = Template(json.load(open(cfg_path))["chat_template"])

    def rendered_cost(q, schemas):
        msgs = [{"role": "system", "content": "You are a financial analyst."},
                {"role": "user", "content": q}]
        bare = len(tk.encode(tpl.render(messages=msgs, tools=[],
                                        add_generation_prompt=True)).ids)
        full = len(tk.encode(tpl.render(messages=msgs, tools=schemas,
                                        add_generation_prompt=True)).ids)
        return full - bare

    under = []
    for q, _ in HELD_OUT:
        est = select_tools(q)["estimated_tokens"]
        act = rendered_cost(q, schemas_for(q))
        if act > est:
            under.append((q[:30], est, act))
    check_true("estimate never under-predicts actual", not under,
               method="(A) %s" % (under[:2] or "conservative on all"))
else:
    print("  SKIP  tokenizer absent; rendered-cost check not run")

# ---------------------------------------------------------------------------
section("selection behaviour")

s = select_tools("rsi and macd crossover")
check_true("focused query selects few families", len(s["families"]) <= 2,
           method="(C) %s" % s["families"])
check_true("focused query is high confidence", s["confidence"] == "high",
           method="(C) %s" % s["confidence"])

s = select_tools("compare the option premium to the bond yield")
check_true("cross-domain query widens", len(s["families"]) >= 3,
           method="(C) %s" % s["families"])

# (C) Monotonicity: adding a family's vocabulary must never REMOVE that family.
base = set(select_families("what is the rsi"))
more = set(select_families("what is the rsi and the bond duration"))
check_true("adding vocabulary never drops a family", base <= more,
           method="(C) monotonic")

# (C) The budget backstop must still honour the core guarantee.
s = select_tools("option bond rsi valuation return", max_families=2)
check_true("max_families caps the selection", len(s["families"]) <= 2,
           method="(C)")
check_true("cap still keeps returns_risk", "returns_risk" in s["families"],
           method="(C) SS.6.3 survives truncation")

# (D) The above passes even with the guard deleted, because returns_risk
# happens to rank top-2 anyway -- the same "tested where it never fires" blind
# spot that R14's mutation battery exposed. This case forces the guard to
# ENGAGE: a query with strong non-risk signal and no risk vocabulary at all,
# truncated to one family. Without the displacement logic, returns_risk is
# dropped and mandatory risk tooling disappears.
forced = select_families(
    "black scholes implied volatility greeks delta gamma vega theta strike",
    max_families=1)
check_true("truncation displaces rather than drops the core family",
           "returns_risk" in forced,
           method="(D) regression; got %s" % forced)
check_true("truncation still respects the cap", len(forced) == 1,
           method="(D) %s" % forced)

# (D) schemas_for must agree with select_tools exactly.
q = "what is my option worth"
names_from_schemas = {x["function"]["name"] for x in schemas_for(q)}
check_true("schemas_for matches select_tools",
           names_from_schemas == set(select_tools(q)["tools"]), method="(D)")
check_true("schemas_for output is JSON-serializable",
           bool(json.dumps(schemas_for(q))), method="(D)")

# (D) Provenance: a selector that cannot explain itself cannot be debugged.
s = select_tools("rsi")
for field in ("families", "tools", "scores", "estimated_tokens",
              "confidence", "fallback_used", "label"):
    check_true("result discloses %s" % field, field in s, method="(D)")


section("R18 -- every registered tool is reachable by its own name")

# THE RISK THIS CLOSES, MEASURED 2026-08-30: R18 read "router keyword lists
# need maintenance as tools are added". Asking for each of the 84 registered
# tools by its own name, SIX did not come back: black_76, cash_flow_schedule,
# ev_sales, forward_pe, pb_ratio and ps_ratio. The hand-written list stored
# "p/b", "p/s" and "ev/" with a slash, so "pb ratio" matched nothing, and
# "forward pe" scored derivatives on the word "forward" alone.
#
# Patching those six names would have fixed the symptom and left the risk
# intact. The fix DERIVES a keyword from every registered tool name, and this
# test is what makes that derivation load-bearing: a tool added later without
# a matching hand-written keyword still has to pass here.
#
# WHY "asked by its own name" is the right probe: it is the weakest possible
# request. If naming a tool outright does not surface it, no paraphrase will,
# and under SS.0B a missing tool can become a fabricated number.
unreachable = []
for _t in sorted(tool_names()):
    _got = {x["function"]["name"] for x in schemas_for(_t.replace("_", " "))}
    if _t not in _got:
        unreachable.append(_t)
check_true("every registered tool is reachable by its own name",
           unreachable == [],
           method="(D) MEASURED; unreachable=%s" % unreachable)

# (D) The six that were actually broken, named individually so a regression
# reports WHICH one came back rather than only a count.
for _name, _query in (("black_76", "black 76"),
                      ("cash_flow_schedule", "cash flow schedule"),
                      ("ev_sales", "ev sales"),
                      ("forward_pe", "forward pe"),
                      ("pb_ratio", "pb ratio"),
                      ("ps_ratio", "ps ratio")):
    _got = {x["function"]["name"] for x in schemas_for(_query)}
    check_true("%s reachable via %r" % (_name, _query), _name in _got,
               method="(D) regression, was broken before 2026-08-30")

# (D) The derivation must cover every family, or a family could quietly lose
# its safety net while the aggregate test still passes.
for _f in FAMILIES:
    check_true("derived name keywords exist for %s" % _f,
               len(NAME_KEYWORDS.get(_f, ())) > 0, method="(D)")

# (D) Derived keywords must be DERIVED, not hand-copied: every one has to
# trace back to a real registered tool in that same family. This is what stops
# the block from decaying into a second hand-maintained list.
_registry = set(tool_names())
_untraceable = []
for _f, _words in NAME_KEYWORDS.items():
    for _w in _words:
        _joined = _w.replace(" ", "_")
        if _joined in _registry:
            continue
        if any(TOOL_FAMILY.get(_t) == _f and _w in _t.split("_")
               for _t in _registry):
            continue
        _untraceable.append((_f, _w))
check_true("every derived keyword traces to a registered tool",
           _untraceable == [],
           method="(D) untraceable=%s" % _untraceable[:5])

# (D) Short FRAGMENTS must not become signals, while short WHOLE NAMES must.
#
# This assertion was written wrongly the first time and the correction is kept
# rather than hidden: it rejected every keyword under 4 characters, and failed
# on 11 of them -- dcf, roa, roe, adx, atr, ema, obv, rsi, sma, wma, rho. Every
# one of those is the COMPLETE name of a registered tool, and asking for "rsi"
# must obviously return the rsi tool. The test was wrong, not the module.
#
# The real rule has two halves. A whole tool name is always a signal, however
# short, because naming it is an explicit request. A FRAGMENT of a multi-word
# name is only a signal at 4+ characters, because "ev", "pe", "pb" and "to"
# are ambiguous across families -- "ev" alone would pull enterprise-value
# tooling into any query mentioning a car.
_registry_flat = {t.replace("_", " ") for t in tool_names()}
for _f, _words in NAME_KEYWORDS.items():
    _bad = [w for w in _words
            if len(w) < 4 and w not in _registry_flat]
    check_true("no sub-4-char fragment keyword in %s" % _f,
               _bad == [], method="(D) got %s" % _bad)

# (D) And the floor really is applied to fragments: no fragment shorter than 4
# characters may appear unless it is also a whole tool name. Asserted by
# reconstructing the derivation independently of the module.
_leaked = []
for _t, _f in TOOL_FAMILY.items():
    for _part in _t.split("_"):
        if len(_part) >= 4 or _part in _registry_flat:
            continue
        if _part in NAME_KEYWORDS.get(_f, ()):
            _leaked.append((_t, _part))
check_true("short fragments of multi-word names are excluded",
           _leaked == [], method="(D) leaked=%s" % _leaked[:5])

# (D) RECALL-FIRST IS PRESERVED. Adding signals must never REMOVE a family
# from a selection, or the fix would trade one silent failure for another.
# These pairs are the pre-fix selections, MEASURED against the old module.
for _q, _expected in (
        ("What is the P/E ratio of Apple?", {"valuation", "returns_risk"}),
        ("RSI is overbought, should I sell?", {"technicals", "returns_risk"}),
        ("compute the bond duration", {"fixed_income", "returns_risk"}),
        ("Calculate the implied volatility", {"derivatives", "returns_risk"}),
        ("drawdown of my portfolio", {"returns_risk"}),
        ("\u0627\u0631\u0632\u0634 \u0630\u0627\u062a\u06cc \u0633\u0647\u0627\u0645",
         {"valuation", "returns_risk"}),
):
    _now = set(select_families(_q))
    check_true("recall preserved for %r" % _q[:34],
               _expected <= _now,
               method="(D) pre-fix=%s now=%s" % (sorted(_expected), sorted(_now)))

# (D) The FRAGMENT signal must be load-bearing on its own.
#
# WHY THIS EXISTS, MEASURED 2026-08-30: the seven mutants seeded against this
# fix left FOUR alive, and the reachability assertion above could not see any
# of them. The cause is real overlap -- all 57 multi-word tools have at least
# one 4+ character fragment, so the whole-name signal and the fragment signal
# each reach every tool independently, and deleting either one changes nothing
# that "reachable by its own name" can detect.
#
# Two of those survivors are genuinely EQUIVALENT, PROVEN rather than assumed.
# Both were re-run against 569 exhaustive probes -- all 84 tool names, every
# underscore fragment of every name, and 400 name pairs -- and each produced
# 0 family-set differences from the unmutated module:
#   - misrouting derived keywords to returns_risk changes nothing, because
#     returns_risk is a CORE family present in every selection anyway.
#   - dropping the whole-name signal is covered by the fragments: MEASURED,
#     all 57 multi-word tools have at least one 4+ character fragment, so
#     either signal alone reaches every tool.
# An equivalent mutant cannot be killed by any assertion, because there is no
# behaviour to observe. Final battery: 7 seeded, 5 killed, 2 equivalent,
# 0 genuine survivors.
#
# One survivor is NOT equivalent. Raising the fragment floor to 99 kills every
# fragment, and MEASURED across the same 14 queries it changes 3 selections --
# "cash flow schedule" silently loses the `valuation` family. That is a RECALL
# LOSS, the exact class of failure this module exists to prevent, and nothing
# above noticed it. These assertions close that hole.
for _q, _need in (("cash flow schedule", "valuation"),
                  ("cash flow schedule for a bond", "valuation"),
                  ("bond price", "derivatives")):
    _f = select_families(_q)
    check_true("fragment signal keeps %s for %r" % (_need, _q[:26]),
               _need in _f,
               method="(D) MEASURED; lost when the fragment floor is raised")

# (D) And assert the floor's VALUE directly, so a silent retune is caught even
# where the behavioural probes happen to overlap.
check("fragment floor is 4", _sel._NAME_PART_MIN, 4,
      method="(D) 4 excludes ev/pe/pb/to and admits real words")

# (D) THE HAND-WRITTEN VOCABULARY IS STILL LOAD-BEARING, AND THE R18 FIX HID
# THAT. MEASURED, and found by re-running the PERMANENT battery after the fix:
# the mutant "technicals vocabulary gutted" (which deletes the literal list
# "rsi", "macd", "moving average", "sma", "ema", "wma", "bollinger") used to be
# KILLED and afterwards SURVIVED. It was not equivalent. Six of those seven
# words are the names of registered tools, so the derivation now recovers them
# and the old kill was masked -- but "moving average" is NOT a tool name
# (the tools are sma/ema/wma), so deleting the list silently drops technicals
# for the plain-English phrase a non-specialist would actually type:
#     "moving average"                    -> ['returns_risk'] only
#     "50 day moving average"             -> ['returns_risk'] only
#     "show me the moving average of AAPL"-> ['returns_risk'] only
# That is a recall loss of exactly the kind the selector exists to prevent, so
# it is asserted behaviourally here rather than left to the mutant. Note the
# derivation is NOT a replacement for the curated vocabulary: it covers what
# tools are CALLED, never what users call them.
for _q in ("moving average",
           "50 day moving average",
           "show me the moving average of AAPL"):
    _f = select_families(_q)
    check_true("plain-English %r reaches technicals" % _q,
               "technicals" in _f,
               method="(D) MEASURED; lost when the curated list is deleted")

# (D) The widening must stay inside the context budget it exists to protect.
_worst = sum(MEASURED_FAMILY_TOKENS[f] for f in FAMILIES)
check_true("all five families still fit the context target",
           _worst < CONTEXT_TARGET,
           method="(D) MEASURED %d of %d" % (_worst, CONTEXT_TARGET))

# (D) A meaningless query must still not explode into everything. This is the
# precision floor: recall-first permits waste, not surrender.
for _q in ("hello", "what is the weather",
           "\u0633\u0644\u0627\u0645"):
    _f = select_families(_q)
    check_true("%r stays at the core set" % _q, _f == ["returns_risk"],
               method="(D) got %s" % _f)

sys.exit(summary())
