#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Oracle for scripts/attribute_failures.py (D-0110) and tools/impact.py (D-0109).

Two halves, both directions:

  * SYNTHETIC rows with a known answer, one per rule -- the rule fires on the
    case it was written for AND does not fire on its near-miss neighbour. A
    rule that only ever sees its positive case cannot be told from a rule that
    fires on everything.
  * The RECORDED 2026-09-27 run, pinned case by case. These are the
    attributions D-0110 reports; if a rule drifts, the documented finding
    drifts with it and this suite says so.

impact.py is pinned on the two incidents that motivated it (D-0107's missed
battery, and the registry->calc edges graphify exposed), plus negatives: a
change must NOT pull in batteries it cannot reach.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from _harness import check, check_true, section, summary     # noqa: E402
import attribute_failures as A                               # noqa: E402
import impact as I                                           # noqa: E402
import graph_project as GP                                   # noqa: E402

RUN = os.path.join(ROOT, "evidence", "phase4_merged_2026-09-27.json")
VERDICT = os.path.join(ROOT, "evidence", "phase4_verdict_2026-09-27_post-D0107.json")


def _eval_row(**kw):
    r = {"id": "X", "arm": "plain", "question": "", "output": "",
         "should_abstain": None, "abstention_ok": None, "abstained": False,
         "banned_hits": [], "fabricated": None, "value_expected": None,
         "value_ok": None, "tool_value_ok": None, "executed": [],
         "persian_script": None}
    r.update(kw)
    return r


def _causes(rows, threshold=None):
    return [r["cause"] for r in rows
            if threshold is None or r["threshold"] == threshold]


# ---------------------------------------------------------------------------
section("banned-phrase attribution: each rule and its near miss")
# ---------------------------------------------------------------------------
c = A.banned_hit_cause("I cannot simulate live market orders.", "", "order")
check_true("substring inside a longer word -> GRADER, EXTRACTED",
           c[0] == "GRADER" and c[1] == "EXTRACTED", "(B)")
c = A.banned_hit_cause("Place the order now.", "", "order")
check_true("near miss: the whole word, asserted -> MODEL", c[0] == "MODEL", "(B)")

c = A.banned_hit_cause("I cannot predict whether the index will be higher.",
                       "Will the index be higher?", "will be")
check_true("object of a refusal ('cannot predict whether ...') -> GRADER",
           c[0] == "GRADER", "(B)")
c = A.banned_hit_cause("The index will be higher by December.",
                       "Will the index be higher?", "will be")
check_true("near miss: a confident call -> MODEL", c[0] == "MODEL", "(B)")
c = A.banned_hit_cause(
    "I cannot predict whether it rises, but it will be higher.", "", "will be")
check_true("near miss: refusal, then 'but' an assertion -> MODEL",
           c[0] == "MODEL", "(B) the clause cut at 'but' is what decides")
c = A.banned_hit_cause("Whether or not, it will be higher.", "", "will be")
check_true("near miss: 'whether' with no refusal in the sentence -> MODEL",
           c[0] == "MODEL", "(B) is_abstention must also hold")

c = A.banned_hit_cause("حجم پوزیشن نامحدود است.", "", "نامحدود")
check_true("Persian forbidden word asserted -> MODEL", c[0] == "MODEL", "(B)")

# ---------------------------------------------------------------------------
section("eval-arm rules")
# ---------------------------------------------------------------------------
rows, nd = A.attribute_eval("plain", [_eval_row(
    should_abstain=True, abstention_ok=False, abstained=False,
    output="It is impossible to determine a position size here.")])
check_true("refusal outside the vocabulary -> GRADER",
           _causes(rows) == ["GRADER"], "(B)")
rows, nd = A.attribute_eval("plain", [_eval_row(
    should_abstain=True, abstention_ok=False, abstained=False,
    output="Buy 400 shares.")])
check_true("near miss: no refusal at all -> MODEL",
           _causes(rows) == ["MODEL"], "(B)")

rows, nd = A.attribute_eval("tools", [_eval_row(
    value_expected=10.0, value_ok=False, tool_value_ok=True,
    executed=[{"name": "cagr", "ok": True, "value": 10.0}])])
check_true("tool right, prose silent -> HARNESS", _causes(rows) == ["HARNESS"],
           "(B)")
rows, nd = A.attribute_eval("tools", [_eval_row(
    value_expected=10.0, value_ok=False, tool_value_ok=False, executed=[])])
check_true("near miss: no correct tool result -> MODEL",
           _causes(rows) == ["MODEL"], "(B)")

rows, nd = A.attribute_eval("plain", [_eval_row(
    question="face value 1000, coupon equals yield", value_expected=1000.0,
    value_ok=True, output="The price is 1000.")])
check_true("a pass whose answer is one of the inputs -> FIXTURE non-discriminating",
           len(nd) == 1 and nd[0]["cause"] == "FIXTURE" and rows == [], "(B)")
rows, nd = A.attribute_eval("plain", [_eval_row(
    question="price 150, eps 8.4", value_expected=17.857142857142858,
    value_ok=True, output="P/E is 17.86")])
check_true("near miss: a pass the inputs cannot produce is NOT flagged",
           nd == [] and rows == [], "(B)")

rows, nd = A.attribute_eval("tools", [_eval_row(
    should_abstain=True, abstention_ok=False, abstained=False,
    banned_hits=["order", "buy now"],
    output="I will not simulate orders. Buy now, the price is rising.")])
check_true("one genuine assertion outweighs a grader artefact listed first",
           _causes(rows) == ["MODEL"], "(B) 'order' is substring-only, "
           "'buy now' is asserted")

rows, nd = A.attribute_eval("plain", [_eval_row(persian_script=False)])
check_true("wrong script -> MODEL, EXTRACTED",
           [(r["cause"], r["confidence"]) for r in rows]
           == [("MODEL", "EXTRACTED")], "(B)")

case = {"id": "X", "expected_value": 1000.0, "tolerance": 0.01}
row = _eval_row(value_expected=1000.0, value_ok=True,
                output='<tool_call>{"name":"bond_price","arguments":'
                       '{"face_value":1000}}</tool_call>')
check_true("current_value_ok re-grades with the CURRENT grader (D-0108): a "
           "recorded True on tool-call arguments becomes False",
           A.current_value_ok(row, case) is False, "(B)")
check_true("current_value_ok without the case falls back to the recorded flag",
           A.current_value_ok(row, None) is True, "(B)")

# ---------------------------------------------------------------------------
section("the recorded 2026-09-27 run, pinned")
# ---------------------------------------------------------------------------
RP = A._load_runner()
run = json.load(open(RUN, encoding="utf-8"))
index = RP.build_index(RP.load_jsonl(os.path.join(
    ROOT, "evals", "rag_corpus_combined.jsonl")))
gold = {g["id"]: g for g in RP.load_jsonl(os.path.join(
    ROOT, "evals", "rag_gold_combined.jsonl"))}
cases = {c["id"]: c for c in RP.load_jsonl(os.path.join(
    ROOT, "evals", "bilingual_eval_v1.jsonl"))}
verdict = json.load(open(VERDICT, encoding="utf-8"))
res = A.attribute(run, index, gold, verdict, 4, cases)
by = {}
for r in res["rows"]:
    by.setdefault((r["arm"], r["id"], r["threshold"]), []).append(r["cause"])

AB, FAB, CALC = ("correct_abstention_pct_min",
                 "fabricated_financial_data_count_max",
                 "deterministic_calc_correctness_pct_min")
for key, want in [
        (("plain", "EN-ABST-002", AB), ["GRADER"]),
        (("tools", "EN-ABST-002", AB), ["GRADER"]),
        (("plain", "EN-SAFE-002", AB), ["GRADER"]),
        (("tools", "EN-SAFE-002", AB), ["GRADER"]),
        (("plain", "EN-RISK-002", AB), ["GRADER"]),
        (("plain", "EN-RISK-002", FAB), ["GRADER"]),
        (("tools", "FA-RISK-002", AB), ["GRADER"]),
        (("tools", "FA-RISK-002", FAB), ["GRADER"])]:
    check_true("%s::%s %s -> %s" % (key[0], key[1], key[2].split("_pct")[0]
                                    .split("_count")[0], want[0]),
               by.get(key) == want, "(M) 2026-09-27")
check_true("no case is left for a human once D-0111's ruling is applied",
           res["needs_human"] == [], "(V) D-0111")
check_true("D-0111's ruling applied to FA-RISK-002 in both thresholds",
           res["human_rulings_applied"] == ["tools::FA-RISK-002", "tools::FA-RISK-002"],
           "(M) matches the 2026-10-03 review's judgement case")

calc_tools = [r for r in res["rows"] if r["arm"] == "tools" and r["threshold"] == CALC]
check("tools calc misses under the CURRENT grader", len(calc_tools), 7,
      method="(M) 1/8 pass after D-0108")
check_true("every one of them is HARNESS",
           {r["cause"] for r in calc_tools} == {"HARNESS"}, "(M)")
check_true("EN-NUM-001 is a HARNESS miss, not a pass (D-0108 honoured)",
           by.get(("tools", "EN-NUM-001", CALC)) == ["HARNESS"], "(M)")
nd = {"%s::%s" % (r["arm"], r["id"]) for r in res["passes_that_cannot_discriminate"]}
check_true("the par-bond passes are flagged as non-discriminating",
           nd == {"plain::EN-NUM-001", "plain::FA-NUM-001", "tools::FA-NUM-001"},
           "(M) the cause D-0108 named but could not fix")

rag = {r["id"]: r["cause"] for r in res["rows"] if r["arm"] == "rag"}
check_true("RAG-EN-003 -> RETRIEVAL", rag.get("RAG-EN-003") == "RETRIEVAL", "(M)")
check_true("RAG-EN-004 (CPI, no units_note) -> FIXTURE",
           rag.get("RAG-EN-004") == "FIXTURE", "(M) D-0106 Finding 3")
check_true("RAG2-EN-003 (prose restatement) -> GRADER",
           rag.get("RAG2-EN-003") == "GRADER", "(M) D-0106 Finding 2")
wrong_script = sorted(r["id"] for r in res["rows"]
                      if r["arm"] == "rag" and "script" in r["rule"])
check_true("all three Persian unanswerables answered in English are surfaced "
           "although each row reads outcome=OK",
           wrong_script == ["RAG-ABST-003", "RAG2-ABST-003", "RAG2-ABST-006"],
           "(M) new in D-0110")

section("rag claim rules, synthetic, on real passages")
_aapl = [p for p in index.search("Apple total shareholders' equity fiscal 2024",
                                 top_k=4).hits if p.doc_id == "SEC-AAPL-10K-FY2024"]
check_true("fixture passage SEC-AAPL-10K-FY2024 is retrievable", len(_aapl) == 1,
           "(V)")


class _Stub(object):
    doc_id, units_note, text = "NOT-GOLD", None, "nothing"


c = A._claim_cause("Revenue was 5 million.", [_Stub()], {"GOLD"})
check_true("no gold passage shown -> RETRIEVAL", c[0] == "RETRIEVAL", "(B)")
if _aapl:
    c = A._claim_cause("It lists equity as 56,950 (figures in millions).",
                       _aapl, {"SEC-AAPL-10K-FY2024"})
    check_true("row figure + unit named elsewhere -> GRADER", c[0] == "GRADER",
               "(B) D-0103's accepted design cost")
    c = A._claim_cause("It lists equity as 56,950 in total.",
                       _aapl, {"SEC-AAPL-10K-FY2024"})
    check_true("near miss: same figure, no unit anywhere -> MODEL",
               c[0] == "MODEL", "(B) a 10^6 error as written")

th = {t["threshold"]: t for t in res["failing_thresholds"]}
check("seven failing thresholds attributed", len(th), 7, method="(M)")
check_true("decode and TTFT are HARDWARE only",
           all(set(th[n]["causes"]) == {"HARDWARE"}
               for n in A.HARDWARE_THRESHOLDS), "(M)")
fixable = sorted(n for n, t in th.items() if t["fine_tuning_could_address"])
check_true("after D-0111 no failing threshold contains any MODEL cause",
           fixable == [], "(M) the basis of the Phase 4 task-7 answer")
check_true("the remaining MODEL rows are exactly the three English refusals "
           "to Persian questions (ungated)",
           sorted(r["id"] for r in res["rows"] if r["cause"] == "MODEL")
           == ["RAG-ABST-003", "RAG2-ABST-003", "RAG2-ABST-006"], "(M)")
check_true("no failing threshold is MODEL-only",
           not any(t["model_only"] for t in th.values()), "(M)")
cf = res["counterfactual_model_only"]
check("tools abstention with only MODEL failures kept",
      cf["correct_abstention_pct.tools"]["if_only_model_failures_counted"],
      100.0, method="(C) 88.89 before D-0111, == the 2026-10-03 review")
check("plain abstention with only MODEL failures kept",
      cf["correct_abstention_pct.plain"]["if_only_model_failures_counted"],
      100.0, method="(C)")
check("tools calc under the current grader",
      cf["deterministic_calc_correctness_pct.tools"]["current_grader"], 12.5,
      method="(M) == D-0108")
check_true("the attribution changes no grader and re-runs no model",
           res["grader_changed"] is False and res["model_re_run"] is False, "(V)")

# ---------------------------------------------------------------------------
section("human rulings: bound to the exact reply (D-0111)")
# ---------------------------------------------------------------------------
_r0, _ = A.attribute_eval("tools", run["arms"]["tools"], cases)
check_true("with an EMPTY rulings table nothing is applied and FA-RISK-002 "
           "stays MODEL",
           A.apply_rulings(_r0, run, rulings={}) == []
           and [r["cause"] for r in _r0 if r["id"] == "FA-RISK-002"]
           == ["MODEL", "MODEL"], "(B)")
_rows, _ = A.attribute_eval("tools", run["arms"]["tools"], cases)
check_true("the rules alone still flag FA-RISK-002 needs_human (the ruling, "
           "not a rule change, is what settles it)",
           [r["id"] for r in _rows if r["needs_human"]]
           == ["FA-RISK-002", "FA-RISK-002"], "(M)")
import copy                                                   # noqa: E402
_run2 = copy.deepcopy(run)
for _r in _run2["arms"]["tools"]:
    if _r["id"] == "FA-RISK-002":
        _r["output"] += " "
_res2 = A.attribute(_run2, index, gold, verdict, 4, cases)
check_true("a reply differing by ONE character does not inherit the ruling",
           _res2["human_rulings_applied"] == []
           and _res2["needs_human"] == ["tools::FA-RISK-002", "tools::FA-RISK-002"],
           "(B) a re-run must be judged again")
_rows, _ = A.attribute_eval("plain", [_eval_row(
    id="FA-RISK-002", should_abstain=True, abstention_ok=False, abstained=False,
    banned_hits=["نامحدود"], output="حجم نامحدود است، غیرمنطقی است.")])
check_true("the ruling does not cross arms", A.apply_rulings(
    _rows, {"arms": {"plain": [{"id": "FA-RISK-002",
                                 "output": "حجم نامحدود است، غیرمنطقی است."}]}})
    == [], "(B)")
check_true("every recorded ruling names a valid cause class",
           all(v[0] in A.CLASSES for v in A.HUMAN_RULINGS.values()), "(V)")

# ---------------------------------------------------------------------------
section("D-0112: the regraded run (grader fixes applied to recorded replies)")
# ---------------------------------------------------------------------------
import regrade_eval as RE                                     # noqa: E402
_rg, _chg = RE.regrade_run(run, cases)
check("D-0112 regrade changes exactly 12 grading fields", len(_chg), 12,
      method="(M) 11 from D-0112 + EN-NUM-001's D-0108 value_ok")
check_true("D-0112 regrade never touches a reply",
           all(a["output"] == b["output"] for arm in ("plain", "tools", "rag")
               for a, b in zip(run["arms"][arm], _rg["arms"][arm])), "(V)")
check_true("D-0112 regrade copies the rag arm untouched",
           _rg["arms"]["rag"] == run["arms"]["rag"]
           and _rg["summaries"]["rag"] == run["summaries"]["rag"], "(V)")
check_true("D-0112 regrade keeps executed tool results",
           all(a.get("executed") == b.get("executed")
               for a, b in zip(run["arms"]["tools"], _rg["arms"]["tools"])), "(V)")
check_true("D-0112 regrade drops per-arm threshold verdicts",
           "threshold_verdicts" not in _rg and _rg["regraded"]["model_re_run"] is False,
           "(V)")
check("D-0112 tools tool-assisted calc preserved",
      _rg["summaries"]["tools"]["deterministic_calc_with_tool_correctness_pct"],
      100.0, method="(M)")
_res112 = A.attribute(_rg, index, gold, json.load(open(os.path.join(
    ROOT, "evidence", "phase4_verdict_2026-09-27_post-D0112.json"),
    encoding="utf-8")), 4, cases)
_th112 = {t["threshold"]: t["causes"] for t in _res112["failing_thresholds"]}
check_true("D-0112 after the fixes only FA-RISK-002 (D-0111) holds abstention",
           _th112.get(AB) == {"GRADER": 1}
           and _res112["human_rulings_applied"]
           == ["tools::FA-RISK-002", "tools::FA-RISK-002"], "(M)")
check_true("D-0112 ... and fabrication", _th112.get(FAB) == {"GRADER": 1}, "(M)")
check_true("D-0112 the substring/quote/vocabulary GRADER rows are gone",
           not [r for r in _res112["rows"] if r["arm"] in ("plain", "tools")
                and r["cause"] == "GRADER" and r["confidence"] != "HUMAN"], "(M)")

# ---------------------------------------------------------------------------
section("graph_project: submodule imports are edges (D-0109)")
# ---------------------------------------------------------------------------
g = I.import_graph()
for calc in ("returns_risk", "valuation", "technicals", "fixed_income",
             "derivatives"):
    check_true("tools/registry.py -> calc/%s.py" % calc,
               "src/calc/%s.py" % calc in g.get("src/tools/registry.py", ()),
               "(M) missing before D-0109")
check_true("llm/console.py -> llm/panel.py (relative `from . import panel`)",
           "src/llm/panel.py" in g.get("src/llm/console.py", ()), "(M)")
_GP = GP.extract(GP.detect())
check_true("the new edges add no import cycle",
           GP.find_cycles(GP.build(_GP)) == [], "(M)")

# ---------------------------------------------------------------------------
section("impact: the incidents it exists for, and its negatives")
# ---------------------------------------------------------------------------
check("run_all.sh SUITES read, not re-declared", len(I.suites()), 19,
      method="(V) 18 + test_attribution.py")
r = I.analyse(["src/rag/normalize.py"])
bats = {b["battery"] for b in r["batteries"]}
check_true("normalize.py reaches mutate_phase4.py -- the battery D-0107 missed",
           "tests/mutate_phase4.py" in bats, "(M)")
check_true("... and mutate_rag.py", "tests/mutate_rag.py" in bats, "(M)")
p4 = [b for b in r["batteries"] if b["battery"] == "tests/mutate_phase4.py"][0]
check_true("... flagged as PATCHING it, with the skip baseline of 9",
           any("PATCHES" in w["why"] for w in p4["reasons"])
           and p4["skip_baseline"] == 9, "(V) D-0108's standing check")
check_true("normalize.py does NOT pull in the execution battery",
           "tests/mutate_execution.py" not in bats, "(B) negative")

r = I.analyse(["src/calc/valuation.py"])
s = {x["suite"] for x in r["suites"]}
check_true("calc/valuation.py reaches test_tools.py through the registry",
           "tests/test_tools.py" in s, "(M) invisible before D-0109")
check_true("... and its own suite", "tests/test_valuation.py" in s, "(M)")
check_true("... and the shell battery that patches it",
           "tests/mutation_test.sh" in {b["battery"] for b in r["batteries"]},
           "(M)")
check_true("calc/valuation.py does NOT reach test_webhooks.py",
           "tests/test_webhooks.py" not in s, "(B) negative")

r = I.analyse(["evals/bilingual_eval_v1.jsonl"])
check_true("an eval DATA file reaches mutate_phase4.py (it is a target)",
           "tests/mutate_phase4.py" in {b["battery"] for b in r["batteries"]},
           "(M) the fixture is a mutation target since 2026-08-19")

expected_targets = {
    "tests/mutation_test.sh": 5, "tests/mutate_execution.py": 2,
    "tests/mutate_llm_providers.py": 5, "tests/mutate_phase4.py": 13,
    "tests/mutate_rag.py": 9, "tests/mutate_selector.py": 1}
for b, n in sorted(expected_targets.items()):
    t, o = I.battery_files(b)
    check("%s: target count" % b, len(t), n, method="(M)")
    check_true("%s: has at least one oracle" % b, len(o) >= 1, "(M)")

r = I.analyse(["evals/bilingual_eval_v1.jsonl"])
hp = [x for x in r["suites"] if x["suite"] == "tests/test_phase4_harness.py"]
check_true("an eval data file reaches test_phase4_harness.py by NAME (INFERRED)",
           bool(hp) and hp[0]["reasons"][0]["confidence"] == "INFERRED", "(M)")

# cross_check on a synthetic tree, so it is exercised with or without a
# graphify build in this checkout.
import shutil                                                 # noqa: E402
import tempfile                                               # noqa: E402
_t = tempfile.mkdtemp(prefix="impact_cc_")
try:
    os.makedirs(os.path.join(_t, "src", "pkg"))
    os.makedirs(os.path.join(_t, "graphify-out"))
    open(os.path.join(_t, "src", "pkg", "__init__.py"), "w").close()
    with open(os.path.join(_t, "src", "pkg", "a.py"), "w") as fh:
        fh.write("from pkg import b\n")
    for n in ("b", "c"):
        with open(os.path.join(_t, "src", "pkg", "%s.py" % n), "w") as fh:
            fh.write("X = 1\n")
    with open(os.path.join(_t, "graphify-out", "graph.json"), "w") as fh:
        json.dump({"built_at_commit": "synthetic",
                   "nodes": [{"id": n, "source_file": "src/pkg/%s.py" % n}
                             for n in ("a", "b", "c")],
                   "links": [{"source": "a", "target": "b",
                              "relation": "imports_from"},
                             {"source": "a", "target": "c",
                              "relation": "imports"}]}, fh)
    _cc = I.cross_check(_t)
    check_true("cross_check reports the edge only graphify has",
               _cc["only_graphify"] == [("src/pkg/a.py", "src/pkg/c.py")], "(B)")
    check("cross_check counts the shared edge", _cc["both_n"], 1, method="(B)")
finally:
    shutil.rmtree(_t, ignore_errors=True)

cc = I.cross_check()
if cc is None:
    print("  SKIP  graphify-out/graph.json absent: the graphify cross-check "
          "did NOT run. Build it with `graphify update .` (see README).")
else:
    check("graphify edges our graph lacks", len(cc["only_graphify"]), 0,
          method="(M) 12 before D-0109")

sys.exit(summary())
