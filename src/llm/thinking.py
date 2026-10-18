# -*- coding: utf-8 -*-
"""
Thinking-mode control for Qwen3.5-4B, identical in every client (D-0123).

THE PROBLEM, MEASURED
---------------------
* Left to think, the model does not stop: at 512 / 2048 / 3072 tokens the
  <think> block grew with the budget (~3.5 chars per token) and never closed,
  so 3 of 3 cases produced NO visible answer at 3072 tokens (D-0085).
* So every run since D-0091 pre-closes the block ("think-off" prefill), and
  that took silence from 20/52 to 0/52.
* But the "off" switch lives in the CHAT TEMPLATE, and the two templates
  disagree (D-0121, pinned in tests/test_phase7.py):
    - HF tokenizer_config template: thinks unless enable_thinking=false
    - GGUF-embedded template:       does NOT think unless enable_thinking=true
  Ollama and LM Studio use the embedded template, so the SAME weights behave
  one way in our harness, another in the client, and a third way if a client
  ships its own template. A behaviour that depends on which program loaded the
  file is not a property you can test once and rely on.

THE PROPOSAL: "budgeted thinking", decided by the router, enforced by us
------------------------------------------------------------------------
Never let a client decide. The orchestrator sends a RAW prompt (Ollama
/api/generate raw=true, LM Studio /v1/completions, llama.cpp directly) that it
rendered itself, so the template in the GGUF is never consulted. Three modes:

  OFF      (default)  pre-closed block, exactly what every recorded run used.
  BUDGETED             open the block, let the model think for at most
                       `think_budget` tokens, then CLOSE IT OURSELVES by
                       appending "\\n</think>\\n\\n" to what it wrote and asking
                       for the answer in a second call with the remaining
                       budget. The answer is always reached; the thinking can
                       never eat the whole budget (the D-0085 failure).
  (no ON)              unbounded thinking is not offered: D-0085 shows it
                       does not terminate on these prompts.

WHEN to think is decided by a deterministic router, not by the model:
  * a TOOL can answer (CAGR, P/E, position size, fx ...): OFF. The tool is
    exact; thinking adds latency and, MEASURED, the prose arithmetic is where
    the errors are (Q5 CAGR 20 % / 10.94 %).
  * must-refuse / unsafe / injection categories: OFF. Refusals are short and
    are already 100 % with the guard (Phase 6).
  * RAG with evidence: OFF. The answer is a lookup in the shown passages.
  * open multi-step reasoning with no tool (e.g. "compare these two
    strategies"): BUDGETED.

Reasoning text is NEVER shown to the user and never graded (strip_thinking),
but it is logged, so a human can audit it.

This is a PROPOSAL with a working, tested mechanism. Whether BUDGETED improves
answers on this model is UNKNOWN until measured on the i5-12400; the Phase 8
run guide includes that measurement (a small A/B on the open-reasoning rows).
"""
THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"
#: What every recorded run appended after the assistant header (D-0091).
CLOSED_PREFILL = THINK_OPEN + "\n\n" + THINK_CLOSE + "\n\n"
#: Appended to the model's partial reasoning to force the block shut.
FORCE_CLOSE = "\n" + THINK_CLOSE + "\n\n"

MODES = ("off", "budgeted")

#: Categories of bilingual_eval_v1 (and the red-team set) and the mode the
#: router assigns. Anything unlisted is OFF: thinking must be earned.
ROUTE = {
    "calculation_routing": "off", "position_sizing": "off",
    "numerical_reasoning": "off", "abstention": "off", "unsafe_input": "off",
    "trading_safety": "off", "prompt_injection": "off", "terminology": "off",
    "language_quality": "off", "code_switching": "off",
    "multi_step_analysis": "budgeted", "strategy_comparison": "budgeted",
}


def route(category, tool_available=False, has_evidence=False):
    """'off' or 'budgeted'. Deterministic; the model has no say."""
    if tool_available or has_evidence:
        return "off"
    return ROUTE.get(category, "off")


def assistant_prefix(mode):
    """The text placed after '<|im_start|>assistant\\n' for the first call."""
    if mode == "off":
        return CLOSED_PREFILL
    if mode == "budgeted":
        return THINK_OPEN + "\n"
    raise ValueError("unknown thinking mode %r (allowed: %s)" % (mode, ", ".join(MODES)))


def generate_budgeted(complete, base_prompt, think_budget, answer_budget):
    """
    Two-call budgeted thinking over a RAW completion function.

    `complete(prompt, max_tokens) -> (text, completion_tokens)` must not apply
    any chat template (llama.cpp, Ollama raw=true, LM Studio /v1/completions).
    `base_prompt` ends with '<|im_start|>assistant\\n'.

    Returns dict(answer, reasoning, forced_close, think_tokens, answer_tokens).
    The answer is ALWAYS attempted with `answer_budget` tokens, whatever the
    thinking did -- the D-0085 failure (no answer at all) cannot occur.
    """
    if think_budget < 1 or answer_budget < 1:
        raise ValueError("both budgets must be >= 1")
    p1 = base_prompt + assistant_prefix("budgeted")
    t1, n1 = complete(p1, think_budget)
    if THINK_CLOSE in t1:
        # The model closed the block itself. Anything after it is answer text
        # already; continue from there so the answer gets its full budget.
        reasoning, _, rest = t1.partition(THINK_CLOSE)
        p2 = p1 + reasoning + THINK_CLOSE + rest
        forced = False
    else:
        reasoning, rest = t1, ""
        p2 = p1 + t1 + FORCE_CLOSE
        forced = True
    t2, n2 = complete(p2, answer_budget)
    answer = (rest + t2).lstrip("\n")
    return {"answer": answer.strip(), "reasoning": reasoning.strip(),
            "forced_close": forced, "think_tokens": n1, "answer_tokens": n2}
