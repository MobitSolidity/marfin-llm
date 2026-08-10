#!/usr/bin/env python3
"""
Tool-layer verification (Phase 2 acceptance: "test structured tool calls").

Covers three things the calculation tests cannot:
  1. Persian numeral arguments survive the dispatch boundary.
  2. Every failure mode returns a structured refusal, never a number.
  3. Tool schemas are well-formed and render into the real Qwen3 chat template.

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

print("\n[chat template integration]")
tmpl_path = "/tmp/qwen3_tokcfg.json"
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
        ok("generation prompt appended", out.rstrip().endswith("<|im_start|>assistant"))
        ok("tool_call protocol present", "<tool_call>" in out)
    except ImportError:
        print("  SKIP  jinja2 not installed")
else:
    print("  SKIP  %s absent (fetch tokenizer_config.json to enable)" % tmpl_path)

print("\n" + "=" * 82)
print("RESULT: %d passed, %d failed" % (PASS, FAIL))
if FAILURES:
    print("Failed: %s" % ", ".join(FAILURES))
print("=" * 82)
sys.exit(1 if FAIL else 0)
