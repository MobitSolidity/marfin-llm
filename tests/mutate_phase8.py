# -*- coding: utf-8 -*-
"""
Mutation battery for Phase 8 (D-0123): src/llm/style.py, src/llm/thinking.py,
src/llm/local_server.py and their wiring in run_phase4 / merge / compare.
Each mutation weakens ONE check that tests/test_phase8.py claims to pin.
Committed tree only; restore by rewrite.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ORACLE = os.path.join(HERE, "test_phase8.py")

ST = "src/llm/style.py"
TH = "src/llm/thinking.py"
LS = "src/llm/local_server.py"
RUN = "scripts/run_phase4.py"
MG = "scripts/merge_phase4.py"
CQ = "scripts/compare_quants.py"

MUTATIONS = [
    (ST, "\\frac left in place",
     '        m = _FRAC.sub(lambda x: "%s / %s" % (_atom(x.group(1)), _atom(x.group(2))), m)',
     "        pass"),
    (ST, "\\text left in place",
     "        m = _TEXT.sub(lambda x: x.group(1), m)", "        pass"),
    (ST, "symbols not mapped",
     "        m = m.replace(k, _SYMBOLS[k])", "        pass"),
    (ST, "leftover commands kept",
     '    m = _CMD.sub("", m)                       # any command still left is noise',
     "    pass"),
    (ST, "dollar amounts eaten as maths",
     'r"\\$([^$\\n]*?(?:\\\\[A-Za-z]+|[\\^_=])[^$\\n]*?)\\$"',
     'r"\\$([^$\\n]*?)\\$"'),
    (ST, "unclosed $$ tail ignored",
     '    if i != -1 and out.count("$$") == 1:', "    if False:"),
    (ST, "display maths not rewritten",
     "    out = _DISPLAY.sub(rw, text)", "    out = text"),
    (ST, "latin run threshold lowered to 3",
     "[ ,:;.]*){4,}", "[ ,:;.]*){3,}"),
    (ST, "parentheses not masked for latin runs",
     "|`[^`]*`|\\([^()]*\\)|", "|`[^`]*`|"),
    (ST, "budget hit off by one",
     "    return int(completion_tokens) >= int(max_tokens)",
     "    return int(completion_tokens) > int(max_tokens)"),
    (ST, "style rule drops the LaTeX ban",
     "never LaTeX such as", "avoid if possible LaTeX such as"),
    (TH, "off prefix no longer the recorded prefill",
     'CLOSED_PREFILL = THINK_OPEN + "\\n\\n" + THINK_CLOSE + "\\n\\n"',
     'CLOSED_PREFILL = THINK_OPEN + "\\n" + THINK_CLOSE + "\\n"'),
    (TH, "unknown mode falls back silently",
     '    raise ValueError("unknown thinking mode %r (allowed: %s)" % (mode, ", ".join(MODES)))',
     "    return CLOSED_PREFILL"),
    (TH, "tool availability ignored by router",
     "    if tool_available or has_evidence:", "    if has_evidence:"),
    (TH, "evidence ignored by router",
     "    if tool_available or has_evidence:", "    if tool_available:"),
    (TH, "unknown category thinks",
     '    return ROUTE.get(category, "off")', '    return ROUTE.get(category, "budgeted")'),
    (TH, "never force-closes (D-0085 returns)",
     "        p2 = p1 + t1 + FORCE_CLOSE", "        p2 = p1 + t1"),
    (TH, "self-close mis-detected as forced",
     "        forced = False", "        forced = True"),
    (TH, "partial answer after self-close dropped",
     '    answer = (rest + t2).lstrip("\\n")', '    answer = t2.lstrip("\\n")'),
    (TH, "answer call reuses the think budget",
     "    t2, n2 = complete(p2, answer_budget)", "    t2, n2 = complete(p2, think_budget)"),
    (TH, "zero budgets accepted",
     "    if think_budget < 1 or answer_budget < 1:", "    if False:"),
    (LS, "Ollama raw flag dropped (server applies its template)",
     '"raw": True, "stream": False', '"raw": False, "stream": False'),
    (LS, "LM Studio routed to the chat endpoint",
     '    return base + "/v1/completions", {', '    return base + "/v1/chat/completions", {'),
    (LS, "non-loopback accepted",
     '    if not _LOOPBACK.match(base + "/"):', "    if False:"),
    (LS, "unknown backend accepted",
     "    if backend not in BACKENDS:", "    if False:"),
    (LS, "seed not sent to Ollama",
     '"seed": int(seed),\n                "num_predict"', '"num_predict"'),
    (LS, "Ollama tok/s from wall clock",
     '"decode_tps": round(n_out / (ev_ns / 1e9), 2) if ev_ns and n_out else None,',
     '"decode_tps": round(n_out / elapsed, 2) if elapsed and n_out else None,'),
    (LS, "missing response read as empty",
     '        if "response" not in js:', "        if False:"),
    (LS, "thinking not stripped on the server path",
     "        split = L.strip_thinking(text)\n        if split",
     '        split = {"answer": text, "had_thinking": False, "truncated": False,'
     ' "reasoning": ""}\n        if split'),
    (RUN, "style rules never added",
     "    if not style:\n        return system\n", "    return system\n"),
    (RUN, "style rules added by default",
     "def build_plain_prompt(question, refusal_language=False, style=False):",
     "def build_plain_prompt(question, refusal_language=False, style=True):"),
    (RUN, "style record reads the first turn",
     '    m = m.get("second_turn") or m', "    m = m"),
    (RUN, "style rewrite skipped (record only)",
     "    new, n = ST.plain_math(text)", "    new, n = text, 0"),
    (MG, "merge ignores the runtime",
     '            (d.get("server") or {}).get("backend"),', "            None,"),
    (CQ, "runtime change read as repeatability",
     "    if same and rt_b != rt_c:", "    if False:"),
    (CQ, "weights and runtime both differ, accepted",
     "    elif rt_b != rt_c:", "    elif False:"),
    ("scripts/compare_style.py", "style rewrite credited as model compliance",
     '    return m.get("raw_output") if m.get("raw_output") is not None else (r.get("output") or "")',
     '    return r.get("output") or ""'),
    ("scripts/compare_style.py", "runtime change accepted",
     '    if (before.get("server") or {}).get("backend") != (after.get("server") or {}).get("backend"):',
     "    if False:"),
    ("scripts/compare_style.py", "other prompt options may differ",
     "    if pb != pa:", "    if False:"),
    ("scripts/compare_style.py", "regressions and improvements swapped",
     "(regs if gb and not ga else imps).append(e)", "(imps if gb and not ga else regs).append(e)"),
    ("deploy/ollama/Modelfile", "Modelfile think block not pre-closed",
     "<|im_start|>assistant\n<think>\n\n</think>\n\n\"\"\"", "<|im_start|>assistant\n\"\"\""),
    ("deploy/ollama/Modelfile", "Modelfile sampling not greedy",
     "PARAMETER temperature 0\n", "PARAMETER temperature 0.8\n"),
    # ---- D-0124 (fixes from the 2026-10-18 Phase 8 run) ----
    (ST, "style example is an eval answer again",
     '"Ratio = 240 / 12 = 20, never LaTeX', '"P/E = 150 / 8.40 = 17.86, never LaTeX'),
    (ST, "language rule loses the explicit directions",
     '"gets an English answer and a Persian question a Persian answer; a key technical "',
     '"a key technical "'),
    (RUN, "tool note never added",
     '    return system + ST.STYLE_RULES + (ST.STYLE_TOOLS_NOTE if tools else "")',
     "    return system + ST.STYLE_RULES"),
    (RUN, "tool note added to every arm",
     '    return system + ST.STYLE_RULES + (ST.STYLE_TOOLS_NOTE if tools else "")',
     "    return system + ST.STYLE_RULES + ST.STYLE_TOOLS_NOTE"),
    (RUN, "tools arm not flagged as tools",
     "refusal_language), style, tools=True),", "refusal_language), style),"),
    (LS, "Ollama repeat_penalty left to the server default",
     '                "repeat_penalty": REPEAT_PENALTY}', "                }"),
    (LS, "LM Studio repeat_penalty left to the server default",
     '                                      "repeat_penalty": REPEAT_PENALTY,\n', ""),
    (LS, "repeat_penalty pinned to the server default 1.1",
     "REPEAT_PENALTY = 1.0", "REPEAT_PENALTY = 1.1"),
    (LS, "server token counter missing",
     '        return m["prompt_tokens"] or None', "        return None"),
    (RUN, "server TTFT probe not made unique (KV-cache hit)",
     "        prompt = \"[ttft probe %d]\\n\" % time.time_ns() + prompt", "        pass"),
    (RUN, "server token counter not used for the TTFT prompt",
     '               or getattr(runner, "count_tokens", None))', "               or None)"),
    (MG, "merge drops the server block",
     '        **({"server": docs[0][1]["server"]} if docs[0][1].get("server") else {}),', ""),
    ("scripts/grade_merged.py", "harness-only RSS graded as the model's",
     '                and "HARNESS_ONLY" in str(run.get("peak_rss_label") or "")):',
     "                and False):"),
    ("deploy/ollama/Modelfile", "Modelfile repeat_penalty not pinned",
     "PARAMETER repeat_penalty 1.0\n", ""),
    # ---- D-0125 display layer ----
    ("scripts/apply_display_layer.py", "display layer does not rewrite",
     "            shown, n = ST.plain_math(text)", "            shown, n = text, 0"),
    ("scripts/apply_display_layer.py", "model text not preserved",
     '            r["output_model"] = text\n', ""),
    ("scripts/apply_display_layer.py", "styled run not refused",
     "        raise ValueError(\"this run's prompts already carried", "        print(\"this run's prompts already carried"),
    ("scripts/apply_display_layer.py", "prose grades not recomputed",
     "                if k in g and r.get(k) != g[k]:", "                if False:"),
    ("scripts/apply_display_layer.py", "input mutated in place",
     "    new = copy.deepcopy(run)", "    new = run"),
]


def oracle():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run([sys.executable, ORACLE], cwd=ROOT, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
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
