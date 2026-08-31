#!/usr/bin/env python3
"""
Tool-layer verification (Phase 2 acceptance: "test structured tool calls").

Covers what the calculation tests cannot:
  1. Persian numeral arguments survive the dispatch boundary.
  2. Every failure mode returns a structured refusal, never a number.
  3. Tool schemas are well-formed and render into the SHIPPED model's chat
     template (Qwen/Qwen3.5-4B's own, not Qwen3-4B-Instruct-2507's -- D-0088).
  4. All five calculation families are reachable through one uniform contract.
  5. Argument coercion refuses wrong TYPES, not just wrong values.
  6. The rendered tool block fits the context budget (MEASURED, not assumed).

Run: python3 tests/test_tools.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tools.registry import call_tool, tool_names, tool_schemas  # noqa: E402
from calc.persian_num import parse_number, parse_percent, format_persian  # noqa: E402

PASS = FAIL = 0
FAILURES = []


def ok(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS  %-46s %s" % (name, extra))
    else:
        FAIL += 1
        FAILURES.append(name)
        print("  FAIL  %-46s %s" % (name, extra))


def near(name, got, want, tol=1e-9):
    ok(name, isinstance(got, (int, float)) and abs(got - want) <= tol,
       "got %s want %s" % (got, want))


# Wilder's published RSI dataset (New Concepts in Technical Trading Systems),
# the same series pinned in test_technicals.py. Reused here so the dispatch
# layer is checked against the identical industry reference value.
RSI_PRICES = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
              45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]


print("=" * 82)
print("TOOL LAYER VERIFICATION")
print("=" * 82)

print("\n[persian numeral parsing]")
near("parse ۱۵۰", parse_number("۱۵۰"), 150.0)
near("parse ۸٫۴۰ (U+066B decimal)", parse_number("۸٫۴۰"), 8.4)
near("parse ۱۰۰٬۰۰۰ (U+066C thousands)", parse_number("۱۰۰٬۰۰۰"), 100000.0)
near("parse ۱٬۲۳۴٬۵۶۷", parse_number("۱٬۲۳۴٬۵۶۷"), 1234567.0)
near("parse arabic-indic ٥٠٠", parse_number("٥٠٠"), 500.0)
near("parse negative -۴۲٫۵", parse_number("-۴۲٫۵"), -42.5)
near("parse ascii 1,234.56", parse_number("1,234.56"), 1234.56)
near("parse_percent ۲۵٪ -> 0.25", parse_percent("۲۵٪"), 0.25)
# The decimal/thousands distinction is the whole point of this module.
ok("۸٫۴ != ۸٬۴۰۰",
   parse_number("۸٫۴") == 8.4 and parse_number("۸٬۴۰۰") == 8400.0,
   "8.4 vs 8400 -- separators not confused")
ok("format_persian round-trips",
   parse_number(format_persian(1234567.89)) == 1234567.89,
   format_persian(1234567.89))

print("\n[ambiguous input must be refused, not guessed]")
for bad in ["1,5", "1.234,56", "abc", "", "1.2.3"]:
    try:
        v = parse_number(bad)
        ok("reject %r" % bad, False, "parsed as %s" % v)
    except ValueError:
        ok("reject %r" % bad, True, "raised ValueError")

print("\n[tool dispatch -- happy path]")
r = call_tool("position_size", {"account_equity": 50000, "risk_pct": 0.02,
                                "entry": 80, "stop": 76})
ok("position_size ok", r["ok"])
near("position_size 250 units", r["value"], 250.0, 1e-9)
ok("result carries formula", bool(r.get("formula")), r.get("formula", ""))
ok("result carries inputs", isinstance(r.get("inputs"), dict) and r["inputs"])
ok("result labelled COMPUTED", r.get("label") == "COMPUTED")

print("\n[tool dispatch -- Persian arguments]")
r = call_tool("cagr", {"start": "۱۰۰٬۰۰۰", "end": "۱۶۱٬۰۵۱", "years": 5})
ok("cagr accepts Persian digits", r["ok"])
near("cagr == 10%", r["value"], 0.1, 1e-9)
r = call_tool("risk_reward", {"entry": "۱۰۰", "stop": "۹۵", "target": "۱۱۵"})
near("risk_reward Persian args == 3", r["value"], 3.0, 1e-9)

print("\n[tool dispatch -- failures must not yield numbers]")
cases = [
    ("unknown tool", "hack_the_broker", {}, "unknown_tool"),
    ("place_order not registered", "place_order", {"symbol": "TSLA"}, "unknown_tool"),
    ("stop==entry", "position_size",
     {"account_equity": 10000, "risk_pct": 0.01, "entry": 50, "stop": 50},
     "ZeroDivisionError"),
    ("risk_pct as 5 not 0.05", "position_size",
     {"account_equity": 10000, "risk_pct": 5, "entry": 50, "stop": 45},
     "ValueError"),
    ("missing args", "cagr", {"start": 100}, "missing_argument"),
    ("unknown arg", "cagr", {"start": 100, "end": 200, "years": 1, "x": 1},
     "unknown_argument"),
    ("bad enum", "sharpe_ratio", {"returns": [0.01, 0.02], "freq": "fortnightly"},
     "invalid_argument"),
    ("ambiguous numeral", "cagr", {"start": "1,5", "end": 200, "years": 1},
     "invalid_argument"),
    ("nan injected", "annualized_volatility",
     {"returns": [0.01, float("nan"), 0.02]}, "ValueError"),
    ("arguments not a dict", "cagr", "not a dict", "bad_arguments"),
]
for desc, name, args, want_err in cases:
    r = call_tool(name, args)
    good = (r["ok"] is False and r.get("error") == want_err
            and "value" not in r)
    ok("refuse: %s" % desc, good, "%s" % r.get("error"))

print("\n[no execution capability is reachable]")
forbidden = ["place_order", "submit_order", "buy", "sell", "execute_trade",
             "cancel_order", "broker_connect", "enable_live_trading"]
names = tool_names()
ok("no order/execution tool registered",
   not any(f in names for f in forbidden),
   "%d tools, none executable" % len(names))
ok("all tools are pure calculations",
   all(not any(k in n for k in ("order", "trade", "broker", "execute"))
       for n in names))

print("\n[schemas]")
schemas = tool_schemas()
ok("schema count matches tools", len(schemas) == len(names),
   "%d schemas" % len(schemas))
well_formed = True
for s in schemas:
    fn = s.get("function", {})
    if not fn.get("name") or not fn.get("description"):
        well_formed = False
    p = fn.get("parameters", {})
    if p.get("type") != "object" or "properties" not in p:
        well_formed = False
    for req in p.get("required", []):
        if req not in p["properties"]:
            well_formed = False
ok("all schemas well-formed", well_formed)
ok("schemas JSON-serializable", bool(json.dumps(schemas)))

print("\n[all five calculation families reachable through one contract]")
# One representative per family. The point is not the arithmetic (proven in the
# per-module suites) but that dispatch, coercion and disclosure behave the same
# regardless of which family answers.
family_cases = [
    ("returns/risk", "cagr", {"start": 100000, "end": 161051, "years": 5}, 0.1),
    ("valuation", "pe_ratio", {"price": 150, "eps": 8.4}, 150 / 8.4),
    ("technicals", "rsi", {"prices": RSI_PRICES}, 70.46413502109705),
    ("fixed income", "bond_price",
     {"face_value": 1000, "coupon_rate": 0.05, "ytm": 0.05,
      "years_to_maturity": 10}, 1000.0),
    ("derivatives", "black_scholes",
     {"spot": 100, "strike": 100, "time_to_expiry": 1.0, "volatility": 0.2,
      "risk_free_rate": 0.05}, 10.450583572185565),
]
for fam, name, args, want in family_cases:
    r = call_tool(name, args)
    ok("%s: %s dispatches" % (fam, name), r.get("ok") is True, r.get("message", ""))
    near("%s: %s value" % (fam, name), r.get("value"), want, 1e-9)

# Every successful result must carry the disclosure fields SYSTEM_PROMPT.md 5.3
# requires. A bare number is exactly what this engine exists to prevent.
required_fields = ("name", "value", "formula", "inputs", "units", "label")
missing = []
for fam, name, args, _ in family_cases:
    r = call_tool(name, args)
    for f in required_fields:
        if f not in r:
            missing.append("%s.%s" % (name, f))
ok("every result carries full disclosure", not missing, str(missing[:5]))

print("\n[dict- and list-valued results survive dispatch]")
# Several new tools return structured values rather than a scalar. If JSON
# serialization broke for these the model would receive nothing usable.
r = call_tool("macd", {"prices": [float(i) for i in range(1, 60)]})
ok("macd returns dict", r["ok"] and isinstance(r["value"], dict),
   str(sorted(r["value"])) if r["ok"] else r.get("message", ""))
ok("macd dict has all three legs",
   r["ok"] and set(r["value"]) == {"macd", "signal", "histogram"})
r = call_tool("bollinger_bands", {"prices": [float(i % 7) + 10 for i in range(40)]})
ok("bollinger returns four bands",
   r["ok"] and set(r["value"]) == {"upper", "middle", "lower", "bandwidth"})
ok("bollinger upper > middle > lower",
   r["ok"] and r["value"]["upper"] > r["value"]["middle"] > r["value"]["lower"])
r = call_tool("cash_flow_schedule", {"face_value": 1000, "coupon_rate": 0.05,
                                     "years_to_maturity": 2, "frequency": 2})
ok("cash_flow_schedule returns list of 4",
   r["ok"] and isinstance(r["value"], list) and len(r["value"]) == 4)
ok("final schedule row repays principal",
   r["ok"] and r["value"][-1]["principal"] == 1000.0)
ok("structured results are JSON-serializable", bool(json.dumps(r)))

print("\n[ESTIMATED must not be laundered into COMPUTED]")
# 0 forbids presenting an estimate as a measurement. The label is the
# mechanism, so it has to survive the dispatch boundary intact.
r = call_tool("margin_estimate", {"position_value": 10000, "leverage": 2})
ok("margin_estimate labelled ESTIMATED", r["ok"] and r["label"] == "ESTIMATED",
   r.get("label", ""))
r = call_tool("liquidation_estimate", {"entry_price": 100, "leverage": 2})
ok("liquidation_estimate labelled ESTIMATED",
   r["ok"] and r["label"] == "ESTIMATED", r.get("label", ""))
near("liquidation price 75", r["value"], 75.0, 1e-9)
r = call_tool("pe_ratio", {"price": 150, "eps": 8.4})
ok("deterministic tool labelled COMPUTED", r["label"] == "COMPUTED", r["label"])
r = call_tool("forward_pe", {"price": 150, "forward_eps": 10})
ok("forward_pe warns its input is an estimate",
   "ESTIMATE" in r.get("notes", "").upper(), r.get("notes", "")[:60])

print("\n[Persian numerals reach every new family]")
r = call_tool("pe_ratio", {"price": "\u06f1\u06f5\u06f0", "eps": "\u06f8\u066b\u06f4\u06f0"})
near("pe_ratio with Persian price/eps", r.get("value"), 150 / 8.4, 1e-9)
r = call_tool("bond_price", {"face_value": "\u06f1\u066c\u06f0\u06f0\u06f0",
                             "coupon_rate": 0.05, "ytm": 0.05,
                             "years_to_maturity": 10})
near("bond_price with Persian face value", r.get("value"), 1000.0, 1e-9)
r = call_tool("sma", {"prices": ["\u06f1\u06f0", "\u06f2\u06f0", "\u06f3\u06f0"], "period": 3})
near("Persian numerals inside an array argument", r.get("value"), 20.0, 1e-9)
r = call_tool("sma", {"prices": [10, 20, 30], "period": "\u06f3"})
near("Persian numeral as an integer argument", r.get("value"), 20.0, 1e-9)

print("\n[type coercion refuses wrong types, not just wrong values]")
# The integer/boolean schema types were added with the new families. Before the
# guard existed a model emitting period=2.5 would have been silently truncated.
type_cases = [
    ("fractional period", "sma", {"prices": [1, 2, 3], "period": 2.5}),
    ("fractional frequency", "bond_price",
     {"face_value": 1000, "coupon_rate": 0.05, "ytm": 0.05,
      "years_to_maturity": 10, "frequency": 2.5}),
    ("string for boolean", "binomial_price",
     {"spot": 100, "strike": 100, "time_to_expiry": 1, "volatility": 0.2,
      "risk_free_rate": 0.05, "american": "yes"}),
    ("int for boolean", "binomial_price",
     {"spot": 100, "strike": 100, "time_to_expiry": 1, "volatility": 0.2,
      "risk_free_rate": 0.05, "steps": 50, "american": 1}),
    ("bad option_type enum", "delta",
     {"spot": 100, "strike": 100, "time_to_expiry": 1, "volatility": 0.2,
      "risk_free_rate": 0.05, "option_type": "straddle"}),
    ("bad side enum", "liquidation_estimate",
     {"entry_price": 100, "leverage": 2, "side": "sideways"}),
]
for desc, name, args in type_cases:
    r = call_tool(name, args)
    ok("refuse: %s" % desc,
       r["ok"] is False and r.get("error") == "invalid_argument"
       and "value" not in r, str(r.get("error")))
ok("whole number given as 3.0 is accepted",
   call_tool("sma", {"prices": [10, 20, 30], "period": 3.0}).get("value") == 20.0)

print("\n[domain refusals from the new families]")
# Each of these is a real analyst error that must produce a refusal rather than
# a confident wrong number.
domain_cases = [
    ("negative EPS has no P/E", "pe_ratio", {"price": 150, "eps": -2}),
    ("PEG growth as fraction not points", "peg_ratio",
     {"pe": 20, "growth_rate_pct": 0.15}),
    ("capex passed negative", "free_cash_flow",
     {"cash_flow_operations": 1000, "capital_expenditure": -200}),
    ("terminal growth above discount rate", "dcf",
     {"cash_flows": [100, 110], "discount_rate": 0.08, "terminal_growth": 0.12}),
    ("volatility as 25 not 0.25", "black_scholes",
     {"spot": 100, "strike": 100, "time_to_expiry": 1,
      "volatility": 25, "risk_free_rate": 0.05}),
    ("expired option", "black_scholes",
     {"spot": 100, "strike": 100, "time_to_expiry": 0,
      "volatility": 0.2, "risk_free_rate": 0.05}),
    ("insufficient RSI warm-up", "rsi", {"prices": [1, 2, 3], "period": 14}),
    ("inconsistent OHLC (high below low)", "atr",
     {"highs": [10, 11], "lows": [12, 9], "closes": [10, 10], "period": 1}),
    ("implausible bond price", "yield_to_maturity",
     {"price": 1e9, "face_value": 1000, "coupon_rate": 0.05,
      "years_to_maturity": 10}),
    ("zero interest expense", "interest_coverage",
     {"ebit": 500, "interest_expense": 0}),
]
for desc, name, args in domain_cases:
    r = call_tool(name, args)
    good = r["ok"] is False and "value" not in r and bool(r.get("message"))
    ok("refuse: %s" % desc, good, str(r.get("error")))
    if r["ok"] is False:
        ok("  ^ refusal tells the model not to substitute",
           "not" in r.get("guidance", "").lower())

print("\n[chat template integration]")
# CORRECTION 2026-08-31 (D-0088): this block used /tmp/qwen3_tokcfg.json, which
# is Qwen3-4B-Instruct-2507's config, NOT the shipped Qwen3.5-4B's (D-0087). It
# therefore asserted things about a template this project never renders. The
# old model's files are deliberately not accepted as a fallback: a fallback
# would silently restore the wrong-model measurement this defect came from.
tmpl_path = "/tmp/q35_tokcfg.json"
if os.path.exists(tmpl_path):
    try:
        from jinja2 import Template
        cfg = json.load(open(tmpl_path))
        t = Template(cfg["chat_template"])
        out = t.render(
            messages=[{"role": "system", "content": "You are a financial analyst."},
                      {"role": "user", "content": "P/E if price=150 and EPS=8.4?"}],
            tools=schemas, add_generation_prompt=True)
        ok("template renders with tools", "<tools>" in out and "</tools>" in out)
        ok("tool names reach the prompt", "position_size" in out and "cagr" in out)
        # MEASURED 2026-08-31, and it is NOT what the old template did. Under
        # Qwen3-4B-Instruct-2507 the render ended '<|im_start|>assistant\n';
        # Qwen3.5-4B appends an OPEN reasoning block, ending
        # '<|im_start|>assistant\n<think>\n'. Had this assertion simply been
        # pointed at the new file it would have started failing -- and had it
        # been "fixed" by loosening it, the very fact that explains D-0085 (the
        # model is handed an open <think> by default) would have been erased.
        # So it now asserts the SHIPPED behaviour explicitly.
        ok("generation prompt appended",
           out.rstrip().endswith("<|im_start|>assistant\n<think>"))
        ok("...and it opens a reasoning block, which is why D-0085 happened",
           out.endswith("<think>\n"))
        ok("tool_call protocol present", "<tool_call>" in out)
        # One name from each new family must actually survive rendering.
        ok("all five families reach the prompt",
           all(n in out for n in ("cagr", "pe_ratio", "rsi", "bond_price",
                                  "black_scholes")))

        # ---- MEASURED context cost --------------------------------------
        # Not estimated: tokenized with the SHIPPED model's tokenizer
        # (Qwen/Qwen3.5-4B). At 16K this is the binding constraint on how many
        # tools may be exposed at once. Was /tmp/qwen3_tokenizer.json until
        # 2026-08-31; see D-0088. MEASURED difference: 8,920 -> 9,122 tokens.
        tokenizer_path = "/tmp/q35_tok.json"
        if os.path.exists(tokenizer_path):
            from tokenizers import Tokenizer
            tk = Tokenizer.from_file(tokenizer_path)
            bare = t.render(messages=[{"role": "system", "content": "You are a financial analyst."},
                                      {"role": "user", "content": "P/E if price=150 and EPS=8.4?"}],
                            tools=[], add_generation_prompt=True)
            n_bare = len(tk.encode(bare).ids)
            n_full = len(tk.encode(out).ids)
            cost = n_full - n_bare
            ctx = 16384
            print("  INFO  MEASURED tool-block cost: %d tokens for %d tools "
                  "(%.1f%% of %d ctx, %.1f tokens/tool)"
                  % (cost, len(schemas), 100.0 * cost / ctx, ctx,
                     float(cost) / len(schemas)))
            # Guard rail, not a target. If the whole catalogue ever crowds out
            # the working context this test must fail loudly rather than let
            # retrieved documents get silently truncated at runtime.
            ok("tool block leaves usable context (<70% of 16K)",
               cost < 0.70 * ctx, "%d tokens" % cost)
            ok("context budget flagged for subsetting (>25% of 16K)",
               cost > 0.25 * ctx,
               "exceeds 25%% -- tool subsetting is REQUIRED, see DECISIONS D-0023")
        else:
            print("  SKIP  %s absent: 2 assertions bounding the tool block "
                  "against the SHIPPED tokenizer did not run "
                  "(token cost not measured)" % tokenizer_path)
    except ImportError as exc:
        print("  SKIP  optional dependency missing (%s): the chat-template "
              "integration assertions did not run" % exc)
else:
    print("  SKIP  %s absent: the whole chat-template integration block "
          "(7+ assertions) did NOT run. Fetch Qwen/Qwen3.5-4B's "
          "tokenizer_config.json per README Prerequisites; the old "
          "Qwen3-4B-Instruct-2507 file is deliberately NOT a fallback "
          "(D-0088)." % tmpl_path)

print("\n" + "=" * 82)
print("RESULT: %d passed, %d failed" % (PASS, FAIL))
if FAILURES:
    print("Failed: %s" % ", ".join(FAILURES))
print("=" * 82)
sys.exit(1 if FAIL else 0)
