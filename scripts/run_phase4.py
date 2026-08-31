#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_phase4.py -- Phase 4 measurement harness. RUN THIS ON THE i5-12400.

    python scripts\\run_phase4.py --model C:\\models\\Qwen3-4B-Instruct-2507-Q4_K_M.gguf

WHY THIS EXISTS AND scripts/run_baseline.py DOES NOT SUFFICE
------------------------------------------------------------
run_baseline.py was written in Phase 2, has never been executed, and an audit
on 2026-08-15 MEASURED nine defects in it. Three matter enough to name:

  1. It grades peak RSS against 12.0 GiB. The APPROVED ceiling is 6.0 GiB.
     It would have printed PASS at twice the limit the user approved.
  2. It never reads expected_value, expected_tool or tolerance, although 8, 10
     and 8 of the 21 eval cases carry them. It graded no correctness at all.
  3. It prints Persian prompts. MEASURED: Persian cannot be encoded in cp1252
     or cp437, which is what a default Windows console uses, so it crashes
     partway through -- after the model has already been loaded and run.

WHAT THIS HARNESS MEASURES (Phase 4's seven tasks)
--------------------------------------------------
  task 1  three arms: plain / +tools / +RAG, over the same prompts
  task 2  retrieval hit rate against evals/rag_gold_v1.jsonl
  task 3  citation correctness via src/rag/citations.verify_claim
  task 4  unsupported-claim rate from the same citation pass
  task 5  latency (TTFT at 2K, decode tok/s) and peak RSS
  task 6  MODEL_FAILURE vs RETRIEVAL_FAILURE, kept apart per case
  task 7  inputs for the fine-tuning decision -- NOT the decision itself

WHAT IT DOES NOT DO, ON PURPOSE
--------------------------------
  - It does not grade Persian fluency or rubric compliance. Those need a human
    reader (R10). Those fields are written as null and reported PENDING_HUMAN.
    A harness that scored them itself would be certifying quality it never
    inspected.
  - It registers NO execution tool and cannot place an order. The tool registry
    contains 84 calculators and zero brokers; the harness asserts this at
    startup and refuses to run if it ever stops being true.
  - It decides nothing. It writes numbers. Phase 4's task 7 decision is taken
    by the user, after reading them.

PREREQUISITES on the target machine
-----------------------------------
    pip install llama-cpp-python psutil
    plus one GGUF file. See docs/guides/phase-4-windows-setup-fa.md.

OUTPUT
------
One JSON file (default evals/results/phase4_run.json). Send that file back.
It is the project's first on-target measurement; every number in it is
labelled MEASURED, COMPUTED or UNKNOWN.
"""

import argparse
import json
import os
import platform
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, _HERE)

import phase4_lib as L  # noqa: E402

# Make the console safe BEFORE anything Persian can reach it.
CONSOLE_UTF8 = L.make_console_safe()


def p(text=""):
    """Print a line that cannot crash the run on a cp1252 console."""
    print(L.safe(text))


def rel(path):
    """Resolve a repo-relative path against the repo root, not the cwd."""
    if os.path.isabs(path):
        return path
    return os.path.join(_ROOT, path)


# ---------------------------------------------------------------------------
# The completion-token budget: ONE constant, two consumers.
#
# 2048, raised from 768 on the user's approval 2026-08-20.
#
# MEASURED on the first real run (768): 25 of 52 calls hit the ceiling, and 20
# of those 25 had thinking_truncated=True -- the reasoning was still OPEN when
# the budget ran out, so the answer was never emitted and the case graded wrong
# for a reason that has nothing to do with the model. Reasoning length at the
# ceiling ranged 1495-3263 characters.
#
# What this does NOT claim: that 2048 is enough. This run gives NO evidence of
# where those 20 reasoning traces would have closed, because every one of them
# was cut off. 2048 may still be short. It is not a fix, it is a larger
# measurement.
#
# The cost is time and the time was measured, not guessed. Fitting
# seconds = 0.018928*prompt_tokens + 0.232341*completion_tokens to the 52 real
# calls reproduces the observed 6115 s total to within 0.8%, and gives
# 4.30 tok/s decode against 4.47 measured independently. On that model the full
# run goes from 1.70 h (measured, at 768) to 3.75 h worst case.
#
# WHY A CONSTANT AND NOT TWO LITERALS, MEASURED 2026-08-20: ModelRunner and the
# argparse default each carried their own 2048. The mutation battery lowered
# ModelRunner's back to 768 and the change SURVIVED the entire suite, because
# main() and every test pass max_tokens explicitly -- so the wrapper's default
# was never read by anything asserted on, while still being the value any
# future caller that omits the argument would silently receive. Two copies of
# a number that must agree is a drift waiting to happen; one constant makes the
# disagreement impossible rather than merely detectable.
DEFAULT_MAX_TOKENS = 2048

# ---------------------------------------------------------------------------
# CHAT TEMPLATE.
#
# WHY THIS EXISTS AT ALL. Until 2026-08-31 this harness called the model as a
# RAW TEXT COMPLETION -- `llm(prompt)` with a prompt shaped
# "SYSTEM...\n\nQuestion: ...\nAnswer:". Qwen3 is an instruction-tuned chat
# model. It was never fine-tuned on that shape, so it was being asked to
# CONTINUE a document rather than to ANSWER a turn.
#
# MEASURED consequence, from the 2026-08-30 run (evidence/phase4_merged.json):
# four cases returned completion_tokens=0 with raw_output="" -- the model
# emitted its end-of-turn token as the FIRST token. The giveaway is the
# timing, which is prefill-only with zero decode steps:
#
#   rag::RAG-EN-005     430 prompt tok / 10.355 s -> 41.53 tok/s
#   rag::RAG-FA-002     202 prompt tok /  4.862 s -> 41.55 tok/s
#   rag::RAG-ABST-002   315 prompt tok /  7.509 s -> 41.95 tok/s
#   tools::FA-ABST-001  525 prompt tok / 13.763 s -> 38.15 tok/s
#
# Four independent cases agreeing to within 1% is not four bad answers, it is
# one systematic defect. No value of --max-tokens can repair a case that never
# emitted a token, which is why raising the budget was NOT the fix.
#
# WHY THE TEMPLATE IS SPELT OUT HERE rather than read from a file. The project
# already had the real Qwen3 template on disk (/tmp/qwen3_tokcfg.json, rendered
# by tests/test_tools.py:301) and it went unused by the harness for two weeks --
# a resource in /tmp that the run does not depend on is a resource the run does
# not get. This constant is stdlib-only, needs no jinja2 at run time, and
# cannot go missing on the user's Windows machine.
#
# VERIFIED 2026-08-31: rendering via jinja2 from the tokenizer_config
# chat_template in /tmp and rendering via chatml_prompt() below produce
# BYTE-IDENTICAL output on four cases including a Persian question and a
# multi-line system prompt. test_phase4_harness.py asserts that equivalence
# whenever the tokenizer config is present, so a future divergence is a test
# failure rather than a silent regression.
#
# WHAT THAT VERIFICATION IS AND IS NOT, CORRECTED 2026-08-31 (D-0087). The file
# it checks against, /tmp/qwen3_tokcfg.json, is Qwen3-4B-Instruct-2507's
# tokenizer_config -- NOT the shipped Qwen3.5-4B's. So the equivalence above is
# real but narrower than it was labelled: it says chatml_prompt() matches
# Qwen3-4B-Instruct-2507's template.
#
# Against Qwen3.5-4B's OWN template, fetched and rendered directly:
#   chatml_prompt(...)                      == its add_generation_prompt render
#                                              MINUS a trailing '<think>\n'
#                                              -> NOT byte-identical
#   chatml_prompt(...) + FORCED_CLOSED_THINK == its enable_thinking=false render
#                                              -> BYTE-IDENTICAL, VERIFIED
#
# In other words the ChatML envelope is the same in both models and that part of
# the verification carries over, but this model's default rendering opens a
# reasoning block for the model, and ours does not. The pre-closed prefill below
# is the officially-rendered alternative, exactly.
IM_START = "<|im_start|>"
IM_END = "<|im_end|>"


def chatml_prompt(system, user):
    """
    Render one system + one user turn in Qwen3's ChatML format.

    Ends with the assistant header and NO trailing content: that is what tells
    an instruction-tuned model it is its turn to speak.
    """
    if not isinstance(system, str) or not isinstance(user, str):
        raise TypeError("chatml_prompt expects str, got %s/%s"
                        % (type(system).__name__, type(user).__name__))
    return (IM_START + "system\n" + system + IM_END + "\n"
            + IM_START + "user\n" + user + IM_END + "\n"
            + IM_START + "assistant\n")


# ---------------------------------------------------------------------------
# FORCING THE REASONING BLOCK CLOSED.
#
# WHY THIS EXISTS. MEASURED 2026-08-31 on the user's i5-12400, three rag cases,
# three budgets: at 512, 2048 and 3072 tokens the model produced NO visible
# answer on any of them. Every generation spent its whole budget inside an
# unterminated <think> block, emitting 6,094/7,908/7,532 characters of reasoning
# at 2048 and 10,647/11,184/11,940 at 3072. The reasoning scales with whatever
# budget it is given (~3.5 chars per token) and never closes its tag, so raising
# --max-tokens is not a route to an answer. See D-0085.
#
# The model card documents that Qwen3.5's /think and /nothink soft switches are
# NOT supported (recorded at phase4_lib.py:212).
#
# CORRECTION, 2026-08-31 (D-0087). An earlier version of this comment said the
# shipped chat_template "contains no `enable_thinking` flag", VERIFIED against
# /tmp/qwen3_tokcfg.json. That file is Qwen3-4B-Instruct-2507's config, NOT this
# model's -- its vocabulary is 151,936 while Qwen3.5-4B's text vocabulary is
# 248,320. Qwen/Qwen3.5-4B's OWN tokenizer_config, fetched and read directly,
# DOES have the flag, and its generation branch is:
#
#     {%- if add_generation_prompt %}
#         {{- '<|im_start|>assistant\n' }}
#         {%- if enable_thinking is defined and enable_thinking is false %}
#             {{- '<think>\n\n</think>\n\n' }}
#         {%- else %}
#             {{- '<think>\n' }}
#         {%- endif %}
#     {%- endif %}
#
# So the claim "no flag exists" was WRONG, and it was wrong in a way that turns
# out to VINDICATE this constant rather than undermine it: the official
# enable_thinking=false rendering is byte-for-byte
# '<|im_start|>assistant\n<think>\n\n</think>\n\n', which is exactly
# chatml_prompt(...) + FORCED_CLOSED_THINK. VERIFIED byte-identical 2026-08-31
# by rendering the real template with jinja2. The prefill below is not a
# workaround for a missing switch; it IS the switch, spelled out.
#
# A consequence worth stating plainly, because it changes what to expect: this
# model's DEFAULT rendering appends '<think>\n' after the assistant header. The
# harness's chatml_prompt() does not, which is why the model was free to open
# its own block and never close it (D-0085).
#
# What IS available is prefilling the assistant turn. Appending an already-closed
# empty reasoning block after the assistant header puts the model at a position
# where, as far as it can tell, it has already finished deliberating -- so the
# next token it produces is the first token of the answer. This is the standard
# technique for Qwen-family reasoning models and needs no library support.
#
# WHY THE TOKENS MATTER, AND WHY THE CALLER MUST CHECK. `<think>` and `</think>`
# have DEDICATED IDS in this tokenizer. In Qwen3.5-4B they are 248068 and
# 248069 -- VERIFIED 2026-08-31 in Qwen/Qwen3.5-4B's own added_tokens_decoder,
# and MEASURED on the user's machine, where the prefill tokenized to exactly
# [248068, 271, 248069, 271] (271 = "\n\n").
#
# THE NUMBERS ARE RECORDED HERE FOR PROVENANCE AND NOTHING ELSE. No code may
# compare against them. An earlier version of this comment gave 151667/151668,
# copied from a config file that described a different model, and
# diagnose_forced_answer.py hardcoded those numbers into a gate -- which then
# refused a perfectly correct prefill on first contact with the real model. The
# gate now DISCOVERS the ids from the loaded model and round-trips them. See
# D-0087.
#
# Precision, because an earlier version of this comment overstated it: those
# entries carry "special": false. They are dedicated ADDED tokens, not special
# tokens; <|im_start|> and <|im_end|> are the special ones and are listed in
# additional_special_tokens, while <think> sits in the same class as
# <tool_call>. This is true of Qwen3.5-4B as well -- re-checked against its own
# config, not inherited. The distinction does not change the design -- what
# matters is that each is ONE id, not a spelling.
#
# If llama-cpp tokenizes this prefix as literal text (several ordinary tokens
# spelling "<think>") rather than as those two ids, the model does not see a
# closed reasoning block at all and the experiment is INVALID -- while still
# producing plausible-looking output. That failure is silent, so it must be
# tested for rather than assumed; scripts/diagnose_forced_answer.py verifies
# the ids before it accepts any result.
THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"

# The exact continuation appended after the assistant header. The blank line
# inside the block and the blank line after it mirror what the model emits
# itself when it closes a block normally ("<think>\n...\n</think>\n\n"), so the
# prefill is a position the model has been trained to continue from rather than
# a novel string.
FORCED_CLOSED_THINK = THINK_OPEN + "\n\n" + THINK_CLOSE + "\n\n"


def chatml_prompt_no_think(system, user):
    """
    Render one system + one user turn, with the reasoning block PRE-CLOSED.

    Identical to chatml_prompt() up to and including the assistant header, then
    an empty closed <think> block. The model's next token is therefore the first
    token of its visible answer.

    NOTE ON GRADING. A reply produced this way has no <think> tag left to strip,
    because the tag is in the PROMPT and llama-cpp is called with echo=False.
    strip_thinking() will see a bare answer and return it unchanged with
    had_thinking=False -- which is correct, but means `had_thinking` must not be
    read as "this model does not think" for prompts built by this function.
    """
    return chatml_prompt(system, user) + FORCED_CLOSED_THINK


# ---------------------------------------------------------------------------
# SAMPLING.
#
# WHY THESE ARE SET EXPLICITLY. llama-cpp-python's defaults are
# temperature=0.8, top_p=0.95, top_k=40, and seed=LLAMA_DEFAULT_SEED
# (0xFFFFFFFF, i.e. RANDOM) -- VERIFIED 2026-08-31 against the library's own
# API reference and llama.h. The harness set NONE of them, so every number this
# project has ever recorded came from a temperature-0.8 sample with a random
# seed: re-running the same case could not be expected to reproduce it, and no
# two arms were strictly comparable.
#
# An evaluation harness whose results cannot be reproduced is not measuring the
# model, it is sampling a distribution once and calling the draw a fact. Greedy
# decoding with a fixed seed makes a re-run mean something.
#
# `stop` includes the end-of-turn token because in raw-completion mode a chat
# model that finishes its turn will happily begin inventing the NEXT turn.
GREEDY_TEMPERATURE = 0.0
DEFAULT_SEED = 20260831
STOP_TOKENS = (IM_END, IM_START + "user")


# ---------------------------------------------------------------------------
# Model wrapper.
#
# Every call to the model goes through here, so the fake used by the test suite
# has exactly one surface to imitate. That is what makes this harness testable
# without a 2.5 GiB download.
# ---------------------------------------------------------------------------

class ModelRunner(object):
    """Thin wrapper over llama_cpp.Llama that records timing per call."""

    def __init__(self, llm, max_tokens=DEFAULT_MAX_TOKENS,
                 temperature=GREEDY_TEMPERATURE, seed=DEFAULT_SEED):
        self.llm = llm
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.seed = seed
        self.calls = 0
        self.truncated_thinking = 0
        self.thinking_replies = 0
        # WHY THIS IS DETECTED RATHER THAN ASSUMED: the test suite's FakeLlama
        # has a fixed signature (prompt, max_tokens, echo). Passing sampling
        # kwargs to it unconditionally would raise TypeError and take the whole
        # suite down; silently swallowing that TypeError would be worse, because
        # a real llama-cpp build that rejected a kwarg would then be scored as
        # a model failure. So the capability is probed ONCE, here, and recorded.
        self.sampling_supported = self._probe_sampling(llm)

    @staticmethod
    def _probe_sampling(llm):
        """True if the callable accepts temperature/seed keyword arguments."""
        try:
            import inspect
            target = llm.__call__ if hasattr(llm, "__call__") else llm
            sig = inspect.signature(target)
        except (TypeError, ValueError):
            # A C-implemented callable with no introspectable signature: assume
            # the real library, which does accept these.
            return True
        params = sig.parameters
        if any(p.kind == inspect.Parameter.VAR_KEYWORD
               for p in params.values()):
            return True
        return "temperature" in params

    def generate(self, prompt, max_tokens=None):
        """
        Returns (answer, metrics). Metrics are MEASURED, never estimated.

        The FIRST return value is the VISIBLE answer, with any <think> block
        removed. That is deliberate: every grader in this harness consumes this
        function's output, so separating reasoning here means no call site can
        forget to do it. MEASURED 2026-08-17 on the unmodified graders: a reply
        whose reasoning said "I cannot provide investment advice" and whose
        answer said "Buy 500 shares of AAPL right now" was scored as a clean
        refusal. Doing the split at each call site instead would leave that
        defect one forgotten line away from returning.

        The raw text is preserved in metrics["raw_output"] so a human grader
        can still read what the model actually emitted.

        `ttft_s` is measured by asking for ONE token and timing it. Streaming
        would be a truer measure, but it is not available uniformly across
        llama-cpp-python versions, and a metric that works on the user's actual
        build beats a better one that raises AttributeError on it.
        """
        self.calls += 1
        n = max_tokens or self.max_tokens
        kw = {"max_tokens": n, "echo": False}
        if self.sampling_supported:
            # Greedy, seeded, and stopped at the end-of-turn token. See the
            # SAMPLING block above for why none of these may be left to the
            # library's defaults.
            kw["temperature"] = self.temperature
            kw["seed"] = self.seed
            kw["stop"] = list(STOP_TOKENS)
        t0 = time.time()
        out = self.llm(prompt, **kw)
        elapsed = time.time() - t0
        try:
            text = out["choices"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("model returned an unrecognised payload: %r"
                               % (type(out).__name__,))
        usage = out.get("usage", {}) or {}
        ctok = usage.get("completion_tokens", 0)
        ptok = usage.get("prompt_tokens", 0)

        split = L.strip_thinking(text)
        if split["had_thinking"]:
            self.thinking_replies += 1
        if split["truncated"]:
            self.truncated_thinking += 1

        return split["answer"], {
            "seconds": round(elapsed, 3),
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
            "decode_tps": (round(ctok / elapsed, 2)
                           if elapsed > 0 and ctok else None),
            "had_thinking": split["had_thinking"],
            "thinking_truncated": split["truncated"],
            "reasoning_chars": len(split["reasoning"]),
            # Kept so a human can audit the split, and so a truncated reply is
            # not silently indistinguishable from an empty one.
            "raw_output": text,
        }


class RemoteRunner(object):
    """
    A remote API provider wearing ModelRunner's interface.

    WHY A SEPARATE CLASS AND NOT A FLAG INSIDE ModelRunner: the two have
    genuinely different failure modes. ModelRunner cannot fail to authenticate,
    cannot be rate limited and cannot cost money; RemoteRunner cannot run out of
    RAM and has no load time. Folding both into one class would mean every
    branch carrying an `if self.remote`, and the local path -- the one the user
    insisted must remain -- would be the one at risk from a change made for the
    remote path.

    What IS shared is the return contract, exactly: (answer, metrics) with the
    <think> block already removed by the same L.strip_thinking. Every grader in
    this harness consumes that contract, so a provider swap cannot change how
    anything is scored. That is the property that makes local-versus-API results
    comparable at all.
    """

    def __init__(self, provider, model_id, max_tokens=DEFAULT_MAX_TOKENS,
                 base_url=None, allow_paid=False, timeout=None):
        from llm import clients as LC
        self._c = LC
        self.provider = provider
        self.model_id = model_id
        self.base_url = base_url
        self.allow_paid = bool(allow_paid)
        self.timeout = timeout or LC.DEFAULT_TIMEOUT_S
        self.max_tokens = max_tokens
        self.calls = 0
        self.truncated_thinking = 0
        self.thinking_replies = 0
        # Counted so the run report can state how much of the user's quota the
        # run consumed. A retry is a request the provider counted even though
        # the harness only asked once, and a free-tier user needs that number.
        self.http_attempts = 0
        self.tokens_in = 0
        self.tokens_out = 0
        # Validate the credential and the endpoint NOW, before any arm starts.
        # MEASURED cost of not doing this: the local 52-case run takes hours, so
        # discovering a bad key at case 1 of arm 3 wastes everything before it.
        from llm.providers import get_api_key, resolve_base_url
        # Resolve first, gate second: the gate exempts a loopback endpoint, and
        # it can only recognise one from the resolved url.
        self.endpoint = resolve_base_url(provider, base_url)
        self.gate = self._c.spend_gate(provider, allow_paid=self.allow_paid,
                                       base_url=self.endpoint)
        get_api_key(provider)
        if not str(model_id or "").strip():
            raise ValueError(
                "no --model-id for %s. There is no default: the model id "
                "decides both the answer and the price. Hint: %s"
                % (provider, self._c.MODEL_HINTS.get(provider, "see the docs")))

    def generate(self, prompt, max_tokens=None):
        self.calls += 1
        n = max_tokens or self.max_tokens
        t0 = time.time()
        res = self._c.chat(self.provider, prompt, n,
                           model_id=self.model_id,
                           base_url=self.base_url,
                           timeout=self.timeout,
                           allow_paid=self.allow_paid)
        elapsed = time.time() - t0
        text = res["text"]
        self.http_attempts += res.get("attempts", 1)
        self.tokens_in += res.get("prompt_tokens", 0)
        self.tokens_out += res.get("completion_tokens", 0)

        # The SAME splitter as the local path. A remote thinking model that
        # spends its whole budget reasoning produces the identical failure --
        # MEASURED locally in 9 of 52 cases -- and it must be counted the same
        # way, not hidden behind a different code path.
        split = L.strip_thinking(text)
        if split["had_thinking"]:
            self.thinking_replies += 1
        if split["truncated"]:
            self.truncated_thinking += 1

        return split["answer"], {
            "seconds": round(elapsed, 3),
            "prompt_tokens": res.get("prompt_tokens", 0),
            "completion_tokens": res.get("completion_tokens", 0),
            "decode_tps": res.get("decode_tps"),
            "had_thinking": split["had_thinking"],
            "thinking_truncated": split["truncated"],
            "reasoning_chars": len(split["reasoning"]),
            "raw_output": text,
            # Remote-only facts. Present so a merged or compared report can
            # never mistake an API run for a local one.
            "provider": self.provider,
            "model_id": self.model_id,
            "http_attempts": res.get("attempts", 1),
            "finish_reason": res.get("finish_reason"),
        }


def peak_rss_gib(proc):
    """
    Peak RSS in GiB, preferring a TRUE peak over a point sample.

    On Windows psutil exposes peak_wset, the high-water mark the OS itself
    recorded. memory_info().rss is only whatever happened to be resident at the
    instant we asked -- it can miss the peak entirely, and reporting it as
    "peak" against a 6.0 GiB approved ceiling would be a false pass.
    """
    if proc is None:
        return None, "UNKNOWN"
    mi = proc.memory_info()
    peak = getattr(mi, "peak_wset", None)
    if peak:
        return round(peak / 1024.0 ** 3, 3), "MEASURED_PEAK"
    return round(mi.rss / 1024.0 ** 3, 3), "MEASURED_POINT_SAMPLE"


# ---------------------------------------------------------------------------
# Prompt construction for the three arms.
# ---------------------------------------------------------------------------

SYSTEM_BASE = (
    "You are a bilingual Persian-English financial analyst. Answer in the "
    "language of the question. If you do not have the information needed, say "
    "so plainly instead of guessing. Never invent a figure."
)

SYSTEM_TOOLS = SYSTEM_BASE + (
    "\n\nYou may call a calculation tool. To do so emit exactly:\n"
    "<tool_call>{\"name\": \"<tool>\", \"arguments\": {...}}</tool_call>\n"
    "Use a tool for any arithmetic rather than computing it yourself.\n"
    "Available tools:\n"
)

SYSTEM_RAG = SYSTEM_BASE + (
    "\n\nAnswer ONLY from the evidence passages provided below. If the "
    "evidence does not contain the answer, say that you do not have it. Do "
    "not use anything you remember about these companies."
)


# The three builders below all end by handing their system text and their user
# text to chatml_prompt. The literal "Question: " prefix is KEPT inside the
# user turn: the scripted model in the test suite locates the question with
# rsplit("Question:", 1) so that it branches on the question rather than on the
# evidence, and removing the marker would silently break that -- the fake would
# start matching text that came from the retrieved passages, which is the exact
# defect its own docstring records having been caught once already.

def build_plain_prompt(question):
    return chatml_prompt(SYSTEM_BASE, "Question: %s" % question)


def build_tools_prompt(question, schemas):
    lines = []
    for s in schemas:
        fn = s.get("function", s)
        req = ", ".join(fn.get("parameters", {}).get("required", []))
        lines.append("- %s(%s): %s" % (fn.get("name"), req,
                                       fn.get("description", "")))
    return chatml_prompt(SYSTEM_TOOLS + "\n".join(lines),
                         "Question: %s" % question)


def build_rag_prompt(question, passages):
    ev = []
    for i, ps in enumerate(passages, 1):
        ev.append("[%d] (%s) %s" % (i, ps.provenance.citation(), ps.text))
    return chatml_prompt(
        SYSTEM_RAG,
        "Evidence:\n%s\n\nQuestion: %s"
        % ("\n".join(ev) if ev else "(no evidence retrieved)", question))


# ---------------------------------------------------------------------------
# Corpus loading.
# ---------------------------------------------------------------------------

def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_index(corpus_rows):
    """Index the fixture corpus using the project's real RAG code."""
    from rag.documents import Provenance, Passage
    from rag.retrieval import PassageIndex
    from rag.sources import get_source

    idx = PassageIndex()
    for r in corpus_rows:
        src = get_source(r["source_key"])
        prov = Provenance(source=src.key, trust_level=src.trust_level,
                          filed=r.get("filed"), accession=r.get("accession"),
                          url=src.base_url, licence=src.licence)
        idx.add(Passage(text=r["text"], provenance=prov,
                        section_path=r.get("section_path", ()),
                        entity=r.get("entity"), entity_id=r.get("entity_id"),
                        period_start=r.get("period_start"),
                        period_end=r.get("period_end"),
                        lang=r.get("lang"), doc_id=r["doc_id"],
                        chunk_index=r.get("chunk_index", 0),
                        units_note=r.get("units_note")))
    return idx


def assert_no_execution_capability():
    """
    Refuse to run if the tool registry has grown anything that trades.

    SS: live submission stays disabled and unreachable. The harness is the one
    place in this project that will feed model-chosen tool names into
    call_tool, so it verifies the registry before doing so rather than trusting
    that a Phase 2 assertion still holds.
    """
    from tools.registry import tool_names
    banned = ("order", "submit", "buy", "sell", "execute", "trade", "broker",
              "place", "cancel", "withdraw", "transfer")
    found = [t for t in tool_names()
             if any(b in t.lower() for b in banned)]
    if found:
        raise RuntimeError(
            "REFUSING TO RUN: the tool registry exposes what look like "
            "execution tools: %s. Phase 4 evaluates analysis only." % found)
    return len(tool_names())


# ---------------------------------------------------------------------------
# The three arms.
# ---------------------------------------------------------------------------

def run_arm_plain(runner, cases, schemas_by_name):
    out = []
    for c in cases:
        text, m = runner.generate(build_plain_prompt(c["prompt"]))
        g = L.grade_case(c, text, schemas_by_name)
        g["arm"] = "plain"
        # The QUESTION is written to the file, not just the answer. Every case
        # carries human_grade=None and persian_fluency_regression is PENDING
        # until a person reads this file -- and a person cannot grade an answer
        # without seeing what was asked. MEASURED 2026-08-15: the file was
        # previously unreadable for grading for exactly this reason.
        g["question"] = c["prompt"]
        g["output"] = text
        g["metrics"] = m
        out.append(g)
        p("  %-14s %-20s %5.1fs %s" % (
            c["id"], c["category"], m["seconds"], _flagline(g)))
    return out


def total_fabrications(summaries):
    """
    Sum `fabricated_financial_data_count` over EVERY arm that ran.

    Returns None when NOTHING was checked, and an int otherwise.

    DEFECT FOUND 2026-08-20: the approved ceiling
    fabricated_financial_data_count_max is 0, and main() was feeding it only
    the RAG arm's count. MEASURED on the first real run: EN-MIX-001 in the
    TOOLS arm emitted 23 invented Apple prices on a case whose rubric demanded
    refusal, and the reported total stayed at 1 -- the RAG arm's own case. A
    ceiling of zero blind to two of three arms is not a ceiling.

    None is NOT treated as zero. A fabrication that was never looked for must
    not be reported as an absence of fabrication: "checked, found none" and
    "not checked" are different facts, and only the first is evidence.

    WHY THIS IS A FUNCTION AND NOT FOUR INLINE LINES, MEASURED 2026-08-20:
    inline in main(), the None-handling was UNREACHABLE. Both summarize_eval
    and summarize_rag always emit an int for that key, so `_fab_counts` could
    only ever be a list of ints or empty, and the mutation battery proved it:
    seeding "None is counted as a zero" and "an unrun arm's absent count is
    treated as zero" produced NO observable difference through main() at all.
    A rule no code path can exercise is exactly the shape of the three defects
    found earlier today -- a requirement that comes out clean by not looking.
    Extracting it makes the rule directly testable with a None in hand, before
    a future summarizer starts emitting one.
    """
    counts = [s.get("fabricated_financial_data_count")
              for s in (summaries or {}).values()]
    known = [c for c in counts if c is not None]
    if not known:
        return None
    return sum(known)


def run_arm_tools(runner, cases, schemas_by_name):
    from tools.selector import schemas_for
    from tools.registry import call_tool
    out = []
    for c in cases:
        schemas = schemas_for(c["prompt"])
        text, m = runner.generate(build_tools_prompt(c["prompt"], schemas))
        g = L.grade_case(c, text, schemas_by_name)
        g["arm"] = "tools"
        g["question"] = c["prompt"]
        g["output"] = text
        g["metrics"] = m
        g["schemas_offered"] = len(schemas)

        # Execute whatever the model actually asked for, and record what came
        # back. This is what turns "the model emitted a tool call" into "the
        # tool produced the right number" -- Phase 4 task 1's real question.
        # The SAME cap the grader applied. Executing calls the grade discarded
        # would let tool_value_ok be decided by a call outside the cap, so the
        # capped run would still be scored on uncapped behaviour.
        _calls = L.parse_tool_calls(text)[0]
        if L.TOOL_CALL_CAP is not None:
            _calls = _calls[:L.TOOL_CALL_CAP]
        executed = []
        for call in _calls:
            res = call_tool(call["name"], call["arguments"])
            executed.append({"name": call["name"],
                             "arguments": call["arguments"],
                             "ok": res.get("ok"),
                             "value": res.get("value"),
                             "error": res.get("error")})
        g["executed"] = executed

        # If a tool produced the right value, the ANSWER is right even when the
        # model's prose has not yet restated it. Recording that separately
        # keeps tool-routing success distinct from prose quality.
        if c.get("expected_value") is not None:
            tol = c.get("tolerance")
            g["tool_value_ok"] = any(
                e["ok"] and e["value"] is not None
                and abs(float(e["value"]) - float(c["expected_value"]))
                <= (0.0 if tol is None else abs(float(tol)))
                for e in executed)
        else:
            g["tool_value_ok"] = None
        out.append(g)
        p("  %-14s %-20s %5.1fs %s" % (
            c["id"], c["category"], m["seconds"], _flagline(g)))
    return out


def run_arm_rag(runner, gold_rows, index, top_k):
    from rag.citations import verify_claim
    out = []
    for gold in gold_rows:
        res = index.search(gold["query"], top_k=top_k)
        passages = list(res.hits)
        text, m = runner.generate(build_rag_prompt(gold["query"], passages))

        # Verify the answer's numbers against the evidence ACTUALLY shown to
        # the model -- not against the gold passage. Checking against evidence
        # the model never saw would measure the gold set, not the model.
        # Verify SENTENCE BY SENTENCE, with years masked.
        #
        # This used to pass the whole answer as a single claim. verify_claim
        # returns early on the first number it cannot locate, and the first
        # number in a financial answer is almost always a year -- so all three
        # graded cases on 2026-08-18 were decided by "2023 does not appear in
        # the evidence", which is true of every filing and means nothing. See
        # phase4_lib.split_claims for the measured evidence.
        citations = []
        claims = L.split_claims(text)
        if text.strip() and not L.is_abstention(text) and claims:
            per_claim = []
            for claim in claims:
                per_passage = []
                for ps in passages:
                    c = verify_claim(claim, ps)
                    per_passage.append({"status": c.status,
                                        "doc_id": ps.doc_id,
                                        "detail": c.detail[:160]})
                # One SUPPORTED passage is enough to ground ONE claim.
                cstat = "SUPPORTED" if any(
                    x["status"] == "SUPPORTED" for x in per_passage) else (
                    "CONTRADICTED" if any(
                        x["status"] == "CONTRADICTED" for x in per_passage)
                    else "UNSUPPORTED")
                per_claim.append({"claim": claim[:200],
                                  "status": cstat,
                                  "per_passage": per_passage})
            # A CONTRADICTED claim anywhere is the worst outcome and decides
            # the answer: one fabricated figure is not redeemed by three sound
            # ones sitting beside it.
            if any(x["status"] == "CONTRADICTED" for x in per_claim):
                best = "CONTRADICTED"
            elif all(x["status"] == "SUPPORTED" for x in per_claim):
                best = "SUPPORTED"
            elif any(x["status"] == "SUPPORTED" for x in per_claim):
                best = "PARTIALLY_SUPPORTED"
            else:
                best = "UNSUPPORTED"
            citations = [{"status": best,
                          "n_passages_checked": len(passages),
                          "n_claims_checked": len(per_claim),
                          "per_claim": per_claim}]

        g = L.grade_rag_case(gold, text, [h.doc_id for h in passages],
                             citations)
        g["arm"] = "rag"
        g["question"] = gold["query"]
        g["output"] = text
        g["metrics"] = m
        out.append(g)
        p("  %-14s %-18s %5.1fs retrieval=%s outcome=%s" % (
            gold["id"], gold["lang"], m["seconds"],
            g["retrieval_ok"], g["outcome"]))
    return out


def _flagline(g):
    bits = []
    if g.get("value_ok") is True:
        bits.append("value=OK")
    elif g.get("value_ok") is False:
        bits.append("value=WRONG")
    if g.get("tool_ok") is True:
        bits.append("tool=OK")
    elif g.get("tool_ok") is False:
        bits.append("tool=MISS")
    if g.get("abstention_ok") is True:
        bits.append("abstain=OK")
    elif g.get("abstention_ok") is False:
        bits.append("abstain=FAIL")
    if g.get("banned_hits"):
        bits.append("BANNED:%d" % len(g["banned_hits"]))
    if g.get("empty_output"):
        bits.append("EMPTY")
    return " ".join(bits)


# ---------------------------------------------------------------------------
# Latency measurement (task 5).
# ---------------------------------------------------------------------------

def build_ttft_prompt(ctx_target, token_counter=None):
    """
    A prompt of approximately `ctx_target` tokens, MEASURED not guessed.

    DEFECT FOUND IN THE FIRST REAL RUN 2026-08-18, MEASURED: this used to be
    `filler * (ctx_target // 12)` on the assumption of ~12 characters, later
    ~14 tokens, per repetition. Against the real Qwen3.5 tokenizer a 2048
    target produced 4433 prompt tokens -- a 2.16x overshoot -- and the run
    still recorded ttft_measured_at_2k: true, because that flag was a ONE-SIDED
    check (`ptok >= target * 0.8`) with a floor and no ceiling. So the reported
    118.68 s was not the quantity the approved threshold names, and nothing in
    the harness said so.

    The repetition count is now derived by actually TOKENIZING the filler when
    a counter is available. `token_counter` takes text and returns a token
    count; when it is None we fall back to the character heuristic AND the
    caller reports the fallback, because an estimate must never be labelled a
    measurement.

    Returns (prompt, how) where `how` is "tokenized" or "estimated".
    """
    filler = ("A price-to-earnings ratio divides price by earnings per share. "
              "It is a valuation multiple, not a measure of quality. ")
    tail = "\n\nQuestion: What is a P/E ratio?\nAnswer:"

    if token_counter is None:
        # No tokenizer: keep the old heuristic but SAY it is a heuristic.
        return (filler * (ctx_target // 12)) + tail, "estimated"

    per = token_counter(filler)
    tail_tokens = token_counter(tail)
    if not per or per <= 0:
        return (filler * (ctx_target // 12)) + tail, "estimated"
    reps = int(max(1, (ctx_target - tail_tokens) // per))
    return (filler * reps) + tail, "tokenized"


def report_latency_block(lat):
    """
    Print the latency lines AND every caveat attached to them.

    EXTRACTED from main() 2026-08-18 so it can be asserted directly. It was
    inline, and mutation testing showed why that mattered: replacing either
    warning's condition with `if False:` -- silencing the harness -- passed the
    whole suite. These two warnings are the only mechanism by which the user
    learns that a printed number does not measure the quantity its threshold
    names. Untested, they were decoration.
    """
    p("TTFT @ %d prompt tokens : %.2f s  [MEASURED]"
      % (lat["ttft_prompt_tokens"], lat["ttft_seconds"]))
    p("decode tok/s            : %s  [MEASURED]"
      % lat["decode_tokens_per_sec"])
    if lat["ttft_prompt_built_by"] != "tokenized":
        p("WARN: the TTFT prompt length was ESTIMATED from characters, not")
        p("      tokenized. Treat ttft_prompt_tokens as the authority.")
    if lat["ttft_measured_at_2k"] is False:
        lo, hi = lat["ttft_prompt_tokens_window"]
        direction = ("OVER" if lat["ttft_prompt_tokens"] > hi else "UNDER")
        p("WARN: the TTFT prompt came out at %d tokens, %s the %d-%d window"
          % (lat["ttft_prompt_tokens"], direction, lo, hi))
        p("      the %d-token threshold refers to. This number therefore does"
          % lat["ttft_prompt_tokens_target"])
        p("      NOT measure the quantity the threshold names.")
        p("      Reported, not silently accepted.")


def _token_counter_for(llm):
    """
    A callable returning the token count of a string, or None if unavailable.

    llama-cpp-python exposes .tokenize(bytes). Older or differently-built
    wheels may not, and a harness that crashes on the user's actual build is
    worse than one that falls back and labels the fallback.
    """
    tok = getattr(llm, "tokenize", None)
    if tok is None:
        return None

    def count(text):
        try:
            return len(tok(text.encode("utf-8")))
        except Exception:
            return None
    return count


def measure_latency(runner, ctx_target=2048):
    """
    TTFT at ~2K prompt tokens, and sustained decode tok/s.

    The approved threshold is time_to_first_token_2k_sec_max = 3.0, so the
    prompt has to actually be about 2K tokens. Measuring TTFT on a short prompt
    and reporting it against a 2K threshold would be a fabricated pass -- and
    measuring it on a 4433-token prompt and reporting it as 2K is the same lie
    in the opposite direction, which is exactly what happened on 2026-08-18.
    """
    prompt, how = build_ttft_prompt(
        ctx_target, _token_counter_for(getattr(runner, "llm", None)))

    # A one-token generation on a thinking model necessarily leaves <think>
    # unterminated, which would inflate the truncated-thinking counter with two
    # measurements that are not eval cases at all. Snapshot the counters and
    # restore them: speed probes must not contaminate a correctness statistic.
    _tt, _th = runner.truncated_thinking, runner.thinking_replies

    _t, m1 = runner.generate(prompt, max_tokens=1)
    ttft = m1["seconds"]
    ptok = m1["prompt_tokens"]

    _t2, m2 = runner.generate("Explain what a price-to-earnings ratio "
                              "measures, in detail.", max_tokens=128)

    runner.truncated_thinking, runner.thinking_replies = _tt, _th
    return {
        "ttft_seconds": round(ttft, 3),
        "ttft_prompt_tokens": ptok,
        "ttft_prompt_tokens_target": ctx_target,
        "ttft_prompt_built_by": how,
        # TWO-SIDED. The old form was `ptok >= ctx_target * 0.8`: a floor with
        # no ceiling, so 4433 tokens against a 2048 target reported True. A
        # window is the only honest form -- a measurement taken at twice the
        # named size is not a measurement at that size.
        "ttft_measured_at_2k": (
            (ctx_target * 0.8) <= ptok <= (ctx_target * 1.25)
            if ptok else None),
        "ttft_prompt_tokens_window": [round(ctx_target * 0.8),
                                      round(ctx_target * 1.25)],
        "decode_tokens_per_sec": m2["decode_tps"],
        "decode_completion_tokens": m2["completion_tokens"],
        "label": "MEASURED",
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Phase 4 measurement harness (run on the target machine)")
    # --model stays REQUIRED for the local provider and becomes optional only
    # for a remote one, checked after parsing. Making it optional outright
    # would let a typo in --provider start a run with no model at all.
    ap.add_argument("--model", default=None, help="path to the GGUF file "
                                                 "(required for --provider local)")
    # THE DEFAULT IS local, DELIBERATELY AND PERMANENTLY.
    #
    # The user's instruction was explicit: "مدل محلی حتماً باید باقی بماند و
    # فقط api به آن اضافه گردد" -- the local model must remain and the API is
    # only added to it. So every existing command line keeps working unchanged
    # and keeps measuring the local model; using an API requires asking for one
    # by name. A default that silently went to the network would also send
    # financial prompts off the machine without the user choosing to.
    ap.add_argument("--provider", default="local",
                    help="local (default) or a remote API provider. "
                         "Run scripts/panel.py to see them all.")
    ap.add_argument("--model-id", default=None,
                    help="the remote model id. No default: the id decides both "
                         "the answer and the price.")
    ap.add_argument("--base-url", default=None,
                    help="override the endpoint; required for --provider custom")
    ap.add_argument("--allow-paid", action="store_true",
                    help="permit a provider that is paid, or whose free tier is "
                         "UNKNOWN. Off by default: your recorded constraint is "
                         "to spend nothing.")
    ap.add_argument("--timeout", type=float, default=None,
                    help="per-request seconds for a remote provider")
    ap.add_argument("--ctx", type=int, default=16384)
    ap.add_argument("--threads", type=int, default=6,
                    help="i5-12400 has 6 physical P-cores; hyperthreads "
                         "usually hurt memory-bound decode")
    ap.add_argument("--evals", default="evals/bilingual_eval_v1.jsonl")
    ap.add_argument("--corpus", default="evals/rag_corpus_v1.jsonl")
    ap.add_argument("--gold", default="evals/rag_gold_v1.jsonl")
    ap.add_argument("--state", default="PROJECT_STATE.json")
    # The budget, its measurement and its cost are documented at
    # DEFAULT_MAX_TOKENS. Read from the constant so this default and
    # ModelRunner's cannot disagree.
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--top-k", type=int, default=4)
    ap.add_argument("--out", default="evals/results/phase4_run.json")
    ap.add_argument("--arms", default="plain,tools,rag",
                    help="comma-separated subset, for resuming a run")
    a = ap.parse_args(argv)

    # ---- provider selection -------------------------------------------
    # Everything here runs BEFORE the model is loaded and before any case is
    # graded, because the cheapest place to refuse is the first one.
    try:
        from llm.providers import get_provider
        prov_spec = get_provider(a.provider)
    except Exception as exc:
        p("ERROR: %s" % exc)
        return 2
    remote = prov_spec["wire"] != "local"

    if remote:
        if a.model:
            p("ERROR: --model is a local GGUF path and --provider %s is a "
              "remote API. Refusing to run: one of the two was a mistake, and "
              "guessing which would either waste hours or send your prompts "
              "somewhere you did not intend." % a.provider)
            return 2
        try:
            from llm import clients as LC
            runner = RemoteRunner(a.provider, a.model_id,
                                  max_tokens=a.max_tokens,
                                  base_url=a.base_url,
                                  allow_paid=a.allow_paid,
                                  timeout=a.timeout)
        except (LookupError, ValueError, OSError) as exc:
            # ProviderError subclasses Exception directly, so it is caught by
            # name below rather than by this tuple.
            p("ERROR: %s" % exc)
            return 2
        except Exception as exc:
            # DEFECT FOUND BY MEASUREMENT 2026-08-27: this used to be a bare
            # `except Exception` printing "ERROR: %s". A missing `import re` in
            # clients.py therefore surfaced as `ERROR: name 're' is not
            # defined` -- formatted exactly like a deliberate refusal, in the
            # same place a refusal appears. A bug wearing a refusal's clothes is
            # worse than a traceback, because the user reads it as "the tool
            # decided not to" and goes looking for the wrong cause. Programming
            # errors are now separated from refusals and named as bugs.
            from llm.providers import ProviderError as _PE
            if isinstance(exc, _PE):
                p("ERROR: %s" % exc)
                return 2
            p("INTERNAL ERROR (%s): %s" % (type(exc).__name__, exc))
            p("       This is a bug in the harness, not a refusal and not a")
            p("       problem with your key or your provider. Nothing was sent.")
            return 3
    else:
        if not a.model:
            p("ERROR: --model is required for --provider local.")
            return 2
        if a.model_id or a.base_url:
            p("ERROR: --model-id and --base-url apply to a remote provider. "
              "--provider is 'local', so they would be silently ignored.")
            return 2
        if not os.path.isfile(a.model):
            p("ERROR: model file not found: %s" % a.model)
            return 2

    try:
        from llama_cpp import Llama
    except ImportError:
        if not remote:
            p("ERROR: llama-cpp-python is not installed.")
            p("       pip install llama-cpp-python")
            return 2
        Llama = None   # a remote run needs no local runtime at all
    try:
        import psutil
    except ImportError:
        psutil = None
        p("WARN: psutil missing; peak RSS will be reported as UNKNOWN, not as")
        p("      a pass. Install it with: pip install psutil")

    n_tools = assert_no_execution_capability()
    thresholds = L.load_thresholds(rel(a.state))

    proc = psutil.Process() if psutil else None
    model_size_gib = (round(os.path.getsize(a.model) / 1024.0 ** 3, 3)
                      if not remote else None)

    p("=" * 78)
    p("PHASE 4 -- RAG AND TOOL-ENABLED EVALUATION (MEASURED ON TARGET)")
    p("=" * 78)
    p("host        : %s %s" % (platform.system(), platform.release()))
    p("cpu         : %s" % (platform.processor() or "unreported by OS"))
    p("python      : %s" % platform.python_version())
    p("console utf8: %s" % CONSOLE_UTF8)
    p("provider    : %s  [%s]" % (a.provider, prov_spec["label"]))

    if remote:
        # A remote run has no GGUF, so there is no sha256 to tie the numbers to
        # specific weights. That is a REAL loss of provenance and it is stated
        # plainly rather than left for the reader to notice: a provider can
        # change what a model id points at without telling anyone, so two runs
        # of the same id are not guaranteed to be the same model.
        p("model id    : %s" % a.model_id)
        # The RESOLVED endpoint, not the flag. resolve_base_url already
        # validated and normalised it, and printing the resolved value is what
        # tells the user where their prompts are actually going.
        p("endpoint    : %s" % runner.endpoint)
        p("provenance  : NO sha256. A remote model id is not a pinned")
        p("              revision; the provider may change what it serves.")
        p("              Local runs remain the reproducible reference.")
        p("cost        : %s" % prov_spec.get("cost", "UNKNOWN"))
        # DEFECT FOUND BY MEASUREMENT 2026-08-27: this line used to fire on
        # `free_tier is not True` alone, so a `custom` provider pointed at
        # http://localhost:8080/v1 printed "--allow-paid was given; this run may
        # be BILLED" when --allow-paid had NOT been given and nothing could be
        # billed. That is a false statement in the run header -- the precise
        # failure mode this project treats as most serious, and it was produced
        # by reading a registry field instead of the gate's actual decision. It
        # now reports what the gate decided.
        gate = getattr(runner, "gate", {}) or {}
        if gate.get("local_endpoint"):
            p("              endpoint is on THIS machine: nothing can be")
            p("              billed, so --allow-paid was not required.")
        elif gate.get("billable"):
            p("              --allow-paid was given; this run may be BILLED.")
        else:
            p("              provider documents a free tier; no --allow-paid")
            p("              needed. The QUOTA is still UNKNOWN to this project.")
        model_identity = {"sha256": None, "label": "REMOTE_API",
                          "thinking_by_default": None,
                          "note": "remote provider; no local file to hash"}
        load_s = 0.0
    else:
        p("model       : %s" % os.path.basename(a.model))
        p("size        : %.3f GiB" % model_size_gib)
        # Hash BEFORE loading. It costs seconds on a GiB-sized file and it is
        # the only thing that ties the numbers below to specific weights.
        # Printed too, because the user should see what they are about to
        # measure.
        model_identity = L.identify_model(a.model)
        p("sha256      : %s" % model_identity["sha256"])
        p("identity    : %s" % model_identity["label"])
        if model_identity.get("is_pinned_revision") is False:
            p("              NOTE: %s" % model_identity["note"])
        elif model_identity["label"] == "UNKNOWN":
            p("              NOTE: %s" % model_identity["note"])

    # State the reasoning-mode expectation UP FRONT. If the model thinks and the
    # budget is small, the run can burn an hour and produce no gradable answers
    # at all; the reader deserves to know before that happens, not after.
    tbd = model_identity.get("thinking_by_default")
    if tbd is True:
        p("thinking    : YES, by default -- graded after <think> is removed")
        if a.max_tokens < 512:
            p("              WARNING: --max-tokens %d is low for a thinking"
              % a.max_tokens)
            p("              model. Answers may never be reached. 2048 advised")
            p("              (MEASURED at 768: 20 of 52 answers were lost")
            p("              inside an unfinished <think> block).")
    elif tbd is False:
        p("thinking    : no")
    else:
        p("thinking    : UNKNOWN for this %s (handled either way)"
          % ("provider" if remote else "file"))
    if remote:
        p("max_tokens  : %d   top_k: %d" % (a.max_tokens, a.top_k))
        p("              ctx and threads do not apply to a remote provider")
    else:
        p("ctx         : %d   threads: %d   top_k: %d"
          % (a.ctx, a.threads, a.top_k))
        p("max_tokens  : %d" % a.max_tokens)
    p("tools       : %d registered, 0 of them can execute a trade" % n_tools)
    p("")

    if not remote:
        t0 = time.time()
        llm = Llama(model_path=a.model, n_ctx=a.ctx, n_threads=a.threads,
                    verbose=False)
        load_s = round(time.time() - t0, 2)
        p("load time   : %.1f s  [MEASURED]" % load_s)
        runner = ModelRunner(llm, max_tokens=a.max_tokens)
    from tools.registry import tool_schemas
    schemas_by_name = {}
    for s in tool_schemas():
        fn = s.get("function", s)
        schemas_by_name[fn["name"]] = fn

    arms = [x.strip() for x in a.arms.split(",") if x.strip()]
    report = {"arms": {}, "summaries": {}}

    # ---- task 5: latency ------------------------------------------------
    p("")
    p("-" * 78)
    p("LATENCY AND MEMORY  (task 5)")
    p("-" * 78)
    lat = measure_latency(runner)
    report_latency_block(lat)
    if remote:
        # The latency numbers above are real, but they measure the PROVIDER's
        # hardware plus the user's internet link -- not this machine. Grading
        # them against thresholds that were approved for a local 4B model on an
        # i5-12400 would be comparing two different questions and calling the
        # answer a pass. Said here, next to the numbers, rather than only in a
        # footnote nobody reads.
        p("")
        p("NOTE: these are REMOTE latencies. They measure the provider's")
        p("      hardware and your network, not this CPU. The approved speed")
        p("      thresholds describe the LOCAL model, so a remote pass is not")
        p("      evidence that the local model improved.")
        p("      Peak RSS below measures this process only: for a remote run")
        p("      it is the Python harness, NOT any model, and it is labelled")
        p("      so in the output file.")

    cases = load_jsonl(rel(a.evals))
    gold_rows = load_jsonl(rel(a.gold))
    corpus = load_jsonl(rel(a.corpus))
    index = build_index(corpus)

    if "plain" in arms:
        p("")
        p("-" * 78)
        p("ARM 1/3  PLAIN BASELINE  (no tools, no evidence)  [%d cases]"
          % len(cases))
        p("-" * 78)
        report["arms"]["plain"] = run_arm_plain(runner, cases, schemas_by_name)
        report["summaries"]["plain"] = L.summarize_eval(
            report["arms"]["plain"])

    if "tools" in arms:
        p("")
        p("-" * 78)
        p("ARM 2/3  TOOLS ENABLED  [%d cases]" % len(cases))
        p("-" * 78)
        report["arms"]["tools"] = run_arm_tools(runner, cases, schemas_by_name)
        report["summaries"]["tools"] = L.summarize_eval(
            report["arms"]["tools"])

    if "rag" in arms:
        p("")
        p("-" * 78)
        p("ARM 3/3  RAG  [%d gold cases over %d passages]"
          % (len(gold_rows), len(corpus)))
        p("-" * 78)
        report["arms"]["rag"] = run_arm_rag(runner, gold_rows, index, a.top_k)
        report["summaries"]["rag"] = L.summarize_rag(report["arms"]["rag"])

    peak, peak_label = peak_rss_gib(proc)
    if remote and peak_label != "UNKNOWN":
        # A remote run loads no weights, so this figure is the harness's own
        # footprint -- typically a few hundred MiB. Against a 6.0 GiB ceiling it
        # would PASS effortlessly and that pass would be meaningless. Relabelled
        # so the verdict cannot be read as evidence about any model.
        peak_label = peak_label + "_HARNESS_ONLY_NO_MODEL_LOADED"

    # ---- threshold verdicts ---------------------------------------------
    ev = report["summaries"].get("tools") or report["summaries"].get("plain") or {}
    rg = report["summaries"].get("rag") or {}

    # Summed over EVERY arm that ran, not read off the RAG arm, and None when
    # nothing was checked. Rationale and the measurement behind it are in
    # total_fabrications()'s docstring, where they can be tested.
    fabrications = total_fabrications(report["summaries"])

    measured = {
        "model_file_size_gib_max": model_size_gib,
        # THE FOUR HARDWARE THRESHOLDS DO NOT APPLY TO A REMOTE PROVIDER.
        #
        # All four were approved as statements about a 4B GGUF on the user's
        # i5-12400. On a remote run, size has no local file, peak RSS is the
        # harness alone, and decode/TTFT measure a datacentre plus an internet
        # link. Feeding those numbers in would produce three effortless PASSes
        # on the two hardware limits and the size limit -- and a PASS that
        # answers a different question is worse than a PENDING, because it
        # reports progress that did not happen. MEASURED locally: these same
        # four are where the local model actually FAILS (3.62-4.38 tok/s against
        # a minimum of 8, 48.6-49.9 s TTFT against a maximum of 3.0), so letting
        # an API launder them into PASSes would erase the project's most
        # important finding.
        "peak_rss_8k_gib_max": None if remote else peak,
        "generation_tokens_per_sec_min":
            None if remote else lat["decode_tokens_per_sec"],
        "time_to_first_token_2k_sec_max":
            None if remote else lat["ttft_seconds"],
        "deterministic_calc_correctness_pct_min":
            ev.get("deterministic_calc_correctness_pct"),
        "unsupported_claim_rate_pct_max": rg.get("unsupported_claim_rate_pct"),
        "citation_correctness_pct_min": rg.get("citation_correctness_pct"),
        "correct_abstention_pct_min": ev.get("correct_abstention_pct"),
        "fabricated_financial_data_count_max": fabrications,
        # Persian fluency regression needs a human reader and a prior
        # measurement to regress against. Neither exists yet -> PENDING.
        "persian_fluency_regression_pct_max": None,
        "tool_call_schema_validity_pct_min":
            ev.get("tool_call_schema_validity_pct"),
        # No order was placeable: the registry has no execution tool. Zero here
        # is MEASURED, not assumed -- assert_no_execution_capability() ran.
        "paper_live_confusion_count_max": 0,
    }
    verdicts = [L.grade_threshold(k, measured.get(k), v)
                for k, v in sorted(thresholds.items())]

    p("")
    p("=" * 78)
    p("APPROVED THRESHOLDS  (limits read from PROJECT_STATE.json)")
    p("=" * 78)
    for v in verdicts:
        p("  %-8s %-42s limit %-8s measured %s"
          % (v["verdict"], v["threshold"], v["limit"],
             "n/a" if v["measured"] is None else v["measured"]))
    n_fail = len([v for v in verdicts if v["verdict"] == "FAIL"])
    n_pend = len([v for v in verdicts if v["verdict"] == "PENDING"])
    p("")
    p("  %d PASS, %d FAIL, %d PENDING (of %d)"
      % (len(verdicts) - n_fail - n_pend, n_fail, n_pend, len(verdicts)))

    # ---- reasoning-mode accounting ---------------------------------------
    # A thinking model that runs out of budget mid-reasoning produces no answer
    # at all. Without this block those cases would read as wrong answers, and
    # the reader would tune the model when the fix is --max-tokens. Printed
    # unconditionally: "0 of N" is information, and a counter that only appears
    # when it fires teaches the reader that its absence means nothing.
    p("")
    p("REASONING MODE  (thinking)")
    p("  replies containing <think>      : %d of %d"
      % (runner.thinking_replies, runner.calls))
    p("  answers LOST to truncation      : %d" % runner.truncated_thinking)
    if runner.truncated_thinking:
        p("  WARNING: those cases produced NO answer -- the token budget ran")
        p("  out inside the reasoning block. They are graded as failures but")
        p("  the fault is the budget, not the model. Re-run with a larger")
        p("  --max-tokens (currently %d) before drawing any conclusion about"
          % a.max_tokens)
        p("  answer quality.")

    if "rag" in arms:
        p("")
        p("MODEL vs RETRIEVAL FAILURES  (task 6)")
        for k, n in sorted(rg.get("outcomes", {}).items()):
            p("  %-20s %d" % (k, n))

    # ---- cases that were graded for NOTHING -------------------------------
    # AUDIT FINDING 2026-08-20. A case whose category is unrecognised, or whose
    # must_abstain override is neither true nor false, leaves the abstention
    # denominator without a word. MEASURED: one mistyped category among two
    # real cases left correct_abstention_pct reading 50.0 while n_cases said 3.
    # A percentage over a denominator that can shrink in silence is not a
    # measurement, and that silence is exactly how EN-MIX-001 survived a
    # 1.7-hour run. Printed for every arm that ran, including when it is zero.
    p("")
    p("UNGRADED CASES  (must be 0)")
    for _arm in ("plain", "tools"):
        _s = report["summaries"].get(_arm)
        if not _s:
            continue
        p("  %-6s not graded for abstention : %d of %d"
          % (_arm, _s.get("abstention_ungraded_n", 0), _s.get("n_cases", 0)))
        for _w in (_s.get("grading_warnings") or []):
            p("    WARNING  %s: %s" % (_w.get("id"), _w.get("warning")))

    p("")
    p("Persian fluency and rubric compliance are NOT graded here. Every case")
    p("carries human_grade=null and must be read by a person before Phase 4")
    p("can be called complete.")

    # ---- persist ---------------------------------------------------------
    out_path = rel(a.out)
    L.ensure_parent_dir(out_path)
    payload = {
        # THE LABEL DISTINGUISHES WHAT WAS ACTUALLY MEASURED.
        #
        # "MEASURED" has meant one specific thing throughout this project: the
        # local model, on the user's own CPU, with a sha256 tying the numbers to
        # specific weights. A remote run measures answer quality but measures
        # NOTHING about this machine, and it has no weight hash at all. Writing
        # "MEASURED" on it would let a future reader -- or a future merge, or a
        # future me -- treat an API run as satisfying the local hardware
        # thresholds. The label is the only thing standing between those two
        # very different files, so it says which one this is.
        "label": "MEASURED_REMOTE_API" if remote else "MEASURED",
        "measures_local_hardware": not remote,
        "phase": 4,
        "route": ("A (user's own machine, remote provider)" if remote
                  else "A (user's own machine)"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "host": {"system": platform.system(),
                 "release": platform.release(),
                 "processor": platform.processor() or None,
                 "python": platform.python_version(),
                 "console_utf8": CONSOLE_UTF8},
        # WHICH engine produced these numbers. This block is FIRST among the
        # model facts because it changes how every number below must be read:
        # a remote run's latency measures somebody else's datacentre and its
        # peak RSS measures nothing at all. A file that recorded speed without
        # recording where it came from would invite exactly the false
        # comparison this project exists to avoid.
        "provider": {
            "name": a.provider,
            "wire": prov_spec["wire"],
            "remote": remote,
            "label": prov_spec["label"],
            "model_id": a.model_id if remote else None,
            "endpoint": getattr(runner, "endpoint", None) if remote else None,
            # From the GATE's decision, not from the registry field. MEASURED
            # 2026-08-27: reading `free_tier is not True` recorded
            # billable_run=True for a run against http://127.0.0.1:8399/v1,
            # where nothing could possibly be billed. The same wrong inference
            # had already been fixed in the console header; leaving it in the
            # payload would have shipped the false claim into the archived file,
            # which outlives the console output.
            "billable_run": bool(getattr(runner, "gate", {}).get("billable")) if remote else False,
            "local_endpoint": bool(getattr(runner, "gate", {}).get("local_endpoint")) if remote else None,
            "allow_paid_given": bool(a.allow_paid),
            "http_attempts": getattr(runner, "http_attempts", None) if remote else None,
            "remote_tokens_in": getattr(runner, "tokens_in", None) if remote else None,
            "remote_tokens_out": getattr(runner, "tokens_out", None) if remote else None,
            # NOT a quota. No provider's limits are recorded as fact anywhere in
            # this project, because published figures contradict each other.
            "quota_recorded": None,
        },
        "model": {"file": os.path.basename(a.model) if a.model else None,
                  "size_gib": model_size_gib,
                  "ctx": a.ctx if not remote else None,
                  "threads": a.threads if not remote else None,
                  "load_seconds": load_s,
                  "max_tokens": a.max_tokens,
                  # HOW THE TOKENS WERE CHOSEN, recorded because the run of
                  # 2026-08-30 did not record it and therefore could not be
                  # reproduced. Until 2026-08-31 the harness passed no sampling
                  # arguments at all, inheriting llama-cpp's temperature=0.8,
                  # top_p=0.95, top_k=40 and a RANDOM seed -- so every figure
                  # that run produced was one draw from a distribution, and
                  # `phase4_merged.json` has no field that says so. A results
                  # file that cannot tell a reader whether a re-run should
                  # reproduce it is not evidence.
                  "sampling": {
                      "temperature": getattr(runner, "temperature", None),
                      "seed": getattr(runner, "seed", None),
                      "stop": list(STOP_TOKENS),
                      "greedy": (getattr(runner, "temperature", None) == 0.0),
                      "applied": getattr(runner, "sampling_supported", None),
                  },
                  # WHICH prompt shape produced these numbers. Raw-completion
                  # and ChatML results are NOT comparable: see the CHAT
                  # TEMPLATE block for the four zero-token cases that the raw
                  # shape produced.
                  "prompt_format": "chatml",
                  # The tool-call cap is written into the payload so a capped
                  # run can never be mistaken for an uncapped one. It changes
                  # the tool_calls_attempted denominator, and a metric whose
                  # denominator moved silently is not comparable to itself.
                  "tool_call_cap": L.TOOL_CALL_CAP,
                  "thinking_replies": runner.thinking_replies,
                  "answers_lost_to_thinking_truncation":
                      runner.truncated_thinking,
                  # WHICH weights produced these numbers, by content hash.
                  # The GGUF the user can actually download is the original
                  # Qwen3-4B, NOT the pinned Qwen3-4B-Instruct-2507 (which
                  # publishes no GGUF). Speed and RAM transfer between them;
                  # Persian fluency and instruction-following do not. Recording
                  # only a basename would let a filename someone typed stand in
                  # for provenance.
                  "identity": model_identity},
        "tool_registry_size": n_tools,
        "latency": lat,
        "peak_rss_gib": peak,
        "peak_rss_label": peak_label,
        "thresholds_approved": thresholds,
        "threshold_verdicts": verdicts,
        "summaries": report["summaries"],
        "arms": report["arms"],
        "human_grading": {
            "status": "PENDING",
            "note": "Persian fluency, rubric compliance and unsupported-claim "
                    "judgement require a human reader (R10). No field in this "
                    "file records a human grade.",
        },
        "generated_by": "scripts/run_phase4.py",
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    p("")
    p("Wrote %s" % out_path)
    if remote:
        # Two runs have now been measured locally, so "first" was already stale;
        # for a remote run it would also be wrong in kind, not just in count.
        p("Send that file back. NOTE: label is MEASURED_REMOTE_API -- it")
        p("measures the provider's answers, NOT this machine's speed or RAM.")
        p("The four hardware thresholds are PENDING in it by design.")
    else:
        p("Send that file back. It measures the LOCAL model on this machine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
