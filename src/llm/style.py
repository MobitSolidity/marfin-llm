# -*- coding: utf-8 -*-
"""
Answer-style controls from the user's Persian review (D-0123, 2026-10-17).

The user read all 24 changed Persian replies of the Phase 7 run and named
three defects that the automatic graders did not see:

1. LaTeX in formulas. "Formulas contain extra words like \\frac ... formulas
   must be simple, only the mathematical combination and the numbers."
   MEASURED in the recorded runs: 8/74 replies on each quant carry LaTeX (a
   first count of 13/14 wrongly included dollar amounts such as "$50 and $60");
   the commands are \\text (41), \\frac (29), \\sigma (8), \\times (6),
   \\approx (5), \\left/\\right (5 each).
2. Mixed language. "Answer in the language of the prompt; only key terms in
   both languages." MEASURED: one Persian reply (Q4 plain/FA-CALC-002) switched
   to whole English sentences.
3. Incomplete answers. MEASURED: every reply the user called incomplete had
   used the full 512-token budget (7 rows on Q5_K_M, 6 on Q4_K_M). They were
   cut off, not finished.

Each defect gets a PROMPT rule (what the model is asked to do) and a
DETERMINISTIC check (what is measured afterwards). LaTeX also gets a
deterministic REWRITE, because a 4B model does not reliably follow a style
rule and the user should never see `\\frac{150}{8.40}`.
All of it is opt-in in run_phase4 (--style), so recorded runs reproduce.
"""
import re

#: Appended to the system prompt by --style. One sentence per defect.
#: D-0124: the example used to be "P/E = 150 / 8.40 = 17.86" -- the exact answer
#: of eval rows EN/FA-CALC-001 (MEASURED: the Phase 8 run reproduced it
#: verbatim). The example is now a number pair that appears in no eval file
#: (pinned in tests/test_phase8.py), so the rule teaches a format, not an answer.
STYLE_RULES = (
    " Write formulas in plain text with ordinary symbols, for example "
    "Ratio = 240 / 12 = 20, never LaTeX such as \\frac or \\text."
    " Write the whole answer in the language of the question: an English question "
    "gets an English answer and a Persian question a Persian answer; a key technical "
    "term may be repeated once in the other language in parentheses, nothing more."
    " Be concise: give the answer first, then at most a few short lines of "
    "explanation, so the reply is complete."
)

#: D-0124. Appended to the TOOLS arm only, after STYLE_RULES. MEASURED on the
#: 2026-10-18 run: with "give the answer first" the model answered directly
#: instead of calling the calculator -- tool calls where a tool was expected
#: fell from 8/10 (Phase 7) to 2/10 in-process and 0/10 through Ollama. The
#: style rules are about the FINAL answer; this says so explicitly.
STYLE_TOOLS_NOTE = (
    " These style rules apply to your final answer only. When arithmetic is "
    "needed, first emit the tool call and wait for its result; do not compute "
    "the number yourself."
)

# --------------------------------------------------------------------------
# 1. LaTeX -> plain text
# --------------------------------------------------------------------------
_SYMBOLS = {
    r"\times": "×", r"\cdot": "·", r"\approx": "≈", r"\neq": "≠", r"\ne": "≠",
    r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥", r"\pm": "±",
    r"\div": "÷", r"\infty": "∞", r"\sigma": "σ", r"\mu": "μ", r"\beta": "β",
    r"\alpha": "α", r"\Delta": "Δ", r"\delta": "δ", r"\rho": "ρ", r"\sum": "Σ",
    r"\%": "%", r"\$": "$", r"\,": " ", r"\;": " ", r"\!": "", r"\quad": " ",
}
_BRACED = r"\{((?:[^{}]|\{[^{}]*\})*)\}"          # one nesting level is enough
_FRAC = re.compile(r"\\[dt]?frac\s*" + _BRACED + r"\s*" + _BRACED)
_SQRT = re.compile(r"\\sqrt\s*(?:\[([^\]]*)\])?\s*" + _BRACED)
_TEXT = re.compile(r"\\(?:text|mathrm|textbf|mathbf|operatorname)\s*" + _BRACED)
_SUPER = re.compile(r"\^\s*" + _BRACED)
_SUB = re.compile(r"_\s*" + _BRACED)
_LEFTRIGHT = re.compile(r"\\(?:left|right|big|Big|bigg|Bigg)\s*")
_DISPLAY = re.compile(r"\$\$(.+?)\$\$", re.S)
_INLINE_PAREN = re.compile(r"\\\((.+?)\\\)", re.S)
_DISPLAY_BRACKET = re.compile(r"\\\[(.+?)\\\]", re.S)
# Inline $...$ only when the inside looks like maths: a dollar AMOUNT such as
# "$50 and $60" must survive. Requires a backslash command, ^, _ or = inside.
_INLINE = re.compile(r"\$([^$\n]*?(?:\\[A-Za-z]+|[\^_=])[^$\n]*?)\$")
_CMD = re.compile(r"\\[A-Za-z]+")


def _atom(s):
    s = s.strip()
    return s if re.fullmatch(r"[\w.,٫٬\u0600-\u06ff ]+", s) and " " not in s else "(%s)" % s


def _math_to_plain(m):
    """Rewrite ONE math span. Iterates because \\frac nests."""
    for _ in range(6):
        before = m
        m = _TEXT.sub(lambda x: x.group(1), m)
        m = _FRAC.sub(lambda x: "%s / %s" % (_atom(x.group(1)), _atom(x.group(2))), m)
        m = _SQRT.sub(lambda x: ("root%s(%s)" % (x.group(1), x.group(2)) if x.group(1)
                                 else "√(%s)" % x.group(2)), m)
        m = _SUPER.sub(lambda x: "^" + _atom(x.group(1)), m)
        m = _SUB.sub(lambda x: "_" + _atom(x.group(1)), m)
        if m == before:
            break
    m = _LEFTRIGHT.sub("", m)
    for k in sorted(_SYMBOLS, key=len, reverse=True):
        m = m.replace(k, _SYMBOLS[k])
    m = _CMD.sub("", m)                       # any command still left is noise
    m = m.replace("{", "").replace("}", "")
    return re.sub(r"[ \t]{2,}", " ", m).strip()


def plain_math(text):
    """
    Replace every LaTeX math span with plain text. Numbers are never altered:
    only commands, braces and delimiters are removed or replaced by the
    ordinary symbol they stand for. Returns (new_text, n_spans_rewritten).
    """
    if not text:
        return text, 0
    n = [0]

    def rw(mt):
        n[0] += 1
        return _math_to_plain(mt.group(1))

    out = _DISPLAY.sub(rw, text)
    out = _DISPLAY_BRACKET.sub(rw, out)
    out = _INLINE_PAREN.sub(rw, out)
    out = _INLINE.sub(rw, out)
    # A reply cut off by the token budget can end inside an UNCLOSED $$ span
    # (MEASURED: Q4_K_M plain/FA-CALC-002). Rewrite that tail too.
    i = out.find("$$")
    if i != -1 and out.count("$$") == 1:
        n[0] += 1
        out = out[:i] + _math_to_plain(out[i + 2:])
    return out, n[0]


def has_latex(text):
    """True if the text still contains a LaTeX command or math delimiter."""
    return bool(re.search(r"\\(?:[dt]?frac|text|times|approx|sigma|left|right|sqrt|cdot)\b"
                          r"|\$\$|\\\(|\\\[", text or ""))


# --------------------------------------------------------------------------
# 2. Language mixing in a Persian reply
# --------------------------------------------------------------------------
_MASK = re.compile(r"\$\$.*?\$\$|\$[^$\n]*\$|`[^`]*`|\([^()]*\)|<tool_call>.*?</tool_call>", re.S)
#: Four or more consecutive Latin WORDS (outside maths, code and parentheses)
#: is a sentence in the other language, not a key term. MEASURED on all 54
#: recorded Persian replies of the Phase 7 run: exactly one reply matches, the
#: one the user's review describes.
_LATIN_RUN = re.compile(r"(?:\b[A-Za-z][A-Za-z'\-]*\b[ ,:;.]*){4,}")


def latin_runs(text):
    """English sentences inside a reply that should be Persian."""
    t = _MASK.sub(" ", text or "")
    return [m.group(0).strip() for m in _LATIN_RUN.finditer(t)]


# --------------------------------------------------------------------------
# 3. Truncation at the token budget
# --------------------------------------------------------------------------
def hit_budget(completion_tokens, max_tokens):
    """
    True if generation stopped because the budget ran out (an incomplete
    answer), False if the model stopped on its own, None if unknown.
    """
    if not completion_tokens or not max_tokens:
        return None
    return int(completion_tokens) >= int(max_tokens)
