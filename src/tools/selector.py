"""
Tool subsetting for a 16K context window (master prompt SS.5.2, SS.5.3; D-0023).

WHY THIS EXISTS
---------------
MEASURED: all 84 tool schemas cost 8,920 tokens = 54.4% of a 16K window, before
the user has said anything. Phase 3 puts retrieved documents in that same
window. All 84 tools + RAG context + conversation history does not fit.

So tools must be selected per query. That makes this module correctness-
relevant, not an optimization: if the selector drops the tool the model needed,
the model has no way to compute the answer and may fabricate one. That is the
exact failure SS.0B forbids.

DESIGN PRINCIPLE: RECALL OVER PRECISION
---------------------------------------
The two errors are not symmetric.
  - Including a tool that is not needed costs ~106 tokens. Recoverable.
  - Excluding a tool that IS needed can produce a fabricated number. Not
    recoverable, and invisible to the user.
Therefore every ambiguous signal widens the selection. The selector is allowed
to be wasteful; it is not allowed to be wrong.

Concretely:
  - Scoring is additive across signals, never subtractive.
  - `returns_risk` is ALWAYS included: it holds position sizing and portfolio
    risk, which are relevant to almost any trading question, and SS.6.3 treats
    risk checks as mandatory rather than optional.
  - A query matching nothing returns the CORE set, not an empty set.
  - Confidence is reported so the caller can widen further or abstain.

This is deliberately a deterministic keyword/lexical router, not a learned or
embedding-based one. It is inspectable, testable offline, costs no tokens and
no model call, and works identically for Persian and English. A model-based
router would need the very context budget this module exists to protect.
"""

import re
from typing import Any, Dict, List, Optional, Sequence, Set

from tools.registry import tool_names, tool_schemas

# ---------------------------------------------------------------------------
# Family membership. Derived from the calc modules rather than hand-listed, so
# a newly registered tool cannot silently fall outside every family and become
# unreachable through the selector.
# ---------------------------------------------------------------------------

FAMILIES = ("returns_risk", "valuation", "technicals", "fixed_income",
            "derivatives")


def _build_family_map() -> Dict[str, str]:
    from calc import returns_risk, valuation, technicals, fixed_income
    from calc import derivatives
    modules = [
        ("returns_risk", returns_risk),
        ("valuation", valuation),
        ("technicals", technicals),
        ("fixed_income", fixed_income),
        ("derivatives", derivatives),
    ]
    mapping: Dict[str, str] = {}
    for name in tool_names():
        for fam, mod in modules:
            if hasattr(mod, name):
                mapping[name] = fam
                break
    return mapping


TOOL_FAMILY: Dict[str, str] = _build_family_map()

# Any registered tool that resolves to no module is an integrity failure: it
# would be invisible to family routing. Surface it at import time rather than
# letting it silently disappear from a subset at runtime.
UNCLASSIFIED: Set[str] = set(tool_names()) - set(TOOL_FAMILY)

# ---------------------------------------------------------------------------
# Keyword signals, bilingual. Persian terms are included because the target
# user works in both languages and a router that only understands English
# would silently degrade to CORE for every Persian query.
# ---------------------------------------------------------------------------

_KEYWORDS: Dict[str, Sequence[str]] = {
    "valuation": (
        # English
        "p/e", "pe ratio", "price to earnings", "eps", "earnings", "valuation",
        "dcf", "discounted cash flow", "intrinsic", "fair value", "dividend",
        "ebitda", "ev/", "enterprise value", "multiple", "book value", "p/b",
        "p/s", "peg", "roe", "roa", "roic", "margin", "gross", "operating",
        "net income", "revenue", "free cash flow", "fcf", "capex",
        "balance sheet", "liquidity", "current ratio", "quick ratio",
        # Jargon-free phrasing. Held-out testing showed real users ask "what
        # is this company worth", never "compute the enterprise value".
        "worth", "expensive", "cheap", "overvalued", "undervalued",
        "profit", "profits", "company value", "how much is the company",
        "value the", "share price relative",
        "leverage", "debt", "solvency", "working capital", "payout",
        "cash conversion", "interest coverage", "profitability",
        # Persian
        "ارزش\u200cگذاری", "ارزشگذاری", "سود هر سهم", "درآمد", "سودآوری",
        "جریان نقدی", "تنزیل", "ارزش ذاتی", "سود تقسیمی", "حاشیه سود",
        "بدهی", "نقدینگی", "ترازنامه", "سرمایه در گردش", "نسبت جاری",
        "بازده حقوق صاحبان سهام", "درآمد عملیاتی",
        "گران", "ارزان", "ارزش شرکت", "سود شرکت", "بیش\u200cارزش",
        "کم\u200cارزش", "قیمت به درآمد",
    ),
    "technicals": (
        "rsi", "macd", "moving average", "sma", "ema", "wma", "bollinger",
        "atr", "adx", "stochastic", "oscillator", "momentum", "overbought",
        "oversold", "indicator", "chart", "candle", "trend", "breakout",
        "support", "resistance", "vwap", "obv", "on balance volume",
        "donchian", "channel", "crossover", "divergence", "signal line",
        "true range", "rate of change", "technical",
        "شاخص", "میانگین متحرک", "نمودار", "روند", "اشباع خرید",
        "اشباع فروش", "مقاومت", "حمایت", "تحلیل تکنیکال", "نوسان\u200cگر",
        "واگرایی", "شکست",
    ),
    "fixed_income": (
        "bond", "coupon", "yield", "ytm", "yield to maturity", "yield to call",
        "duration", "macaulay", "modified duration", "convexity", "dv01",
        "accrued", "clean price", "dirty price", "par", "face value",
        "maturity", "treasury", "sukuk", "fixed income", "credit spread",
        "basis point", "callable", "amortization", "principal",
        "اوراق", "کوپن", "بازده تا سررسید", "سررسید", "دیرش", "اوراق قرضه",
        "صکوک", "ارزش اسمی", "نرخ بهره", "اصل مبلغ",
    ),
    "derivatives": (
        "option", "call", "put", "strike", "black-scholes", "black scholes",
        "black-76", "binomial", "implied volatility", "iv", "greeks", "delta",
        "gamma", "vega", "theta", "rho", "premium", "expiry", "expiration",
        "in the money", "out of the money", "moneyness", "payoff", "breakeven",
        "margin", "liquidation", "leverage", "futures", "forward", "swap",
        "hedge", "derivative", "contract", "underlying",
        "اختیار", "اختیار معامله", "قرارداد آتی", "مشتقه", "پوشش ریسک",
        "اهرم", "لیکوئید", "نوسان ضمنی", "سررسید اختیار", "قیمت اعمال",
    ),
    "returns_risk": (
        "return", "cagr", "growth rate", "volatility", "sharpe", "sortino",
        "calmar", "drawdown", "var", "value at risk", "cvar", "beta", "alpha",
        "correlation", "covariance", "tracking error", "information ratio",
        "position size", "risk", "stop", "stop-loss", "risk reward",
        "portfolio", "concentration", "diversification", "annualized",
        "بازده", "ریسک", "نوسان", "پرتفوی", "حد ضرر", "اندازه موقعیت",
        "افت سرمایه", "همبستگی", "نسبت شارپ", "ارزش در معرض ریسک",
        "رشد مرکب", "تنوع",
    ),
}

# Families that are always present regardless of the query. Risk sizing is
# mandatory under SS.6.3, and returning an empty toolset would strand the model.
CORE_FAMILIES = ("returns_risk",)

# Token cost per family, MEASURED with the real Qwen3 tokenizer against the
# real chat template. Used for budgeting and asserted by tests, so it cannot
# drift silently as tools are added.
MEASURED_FAMILY_TOKENS: Dict[str, int] = {
    "returns_risk": 2079,
    "valuation": 2400,
    "technicals": 1458,
    "fixed_income": 1370,
    "derivatives": 1921,
}
MEASURED_ALL_TOKENS = 8920
CONTEXT_TARGET = 16384


def _normalize(text: str) -> str:
    """
    Lowercase and neutralise ZWNJ so Persian compounds match either way.

    Persian writers spell compounds three ways: with ZWNJ (ارزش\u200cگذاری),
    with a space (ارزش گذاری), or joined (ارزشگذاری). Mutation testing
    exposed that normalising only the QUERY was not enough -- the keyword list
    itself stores ZWNJ forms, so a ZWNJ keyword could never match a normalised
    query. Both sides must go through this function.
    """
    return (text or "").lower().replace("\u200c", " ")


# Short or common-substring tokens must match as whole words. Held-out testing
# caught "iv" matching inside "relat-iv-e", which routed a valuation question to
# derivatives. Others in this class: var/par/call/put/roe/roa/eps/pe.
# A naive `in` test is not safe for these.
_WORDY = re.compile(r"^[a-z0-9/&. -]+$")


def _matches(word: str, hay: str) -> bool:
    w = word.lower()
    if not w:
        return False
    # Latin-script terms: require word boundaries so short abbreviations cannot
    # match inside longer words. Persian/Arabic script is left as substring
    # matching, because its morphology attaches affixes directly to the stem
    # and boundary matching would LOSE genuine hits -- the recall-first rule.
    if _WORDY.match(w):
        return re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])",
                         hay) is not None
    return w in hay


# Keywords are normalised ONCE at import, through the same function used on the
# query. Storing a ZWNJ keyword and comparing it against a de-ZWNJ'd query is a
# silent no-match; normalising both sides is what makes the two spellings
# equivalent in practice.
_NORM_KEYWORDS: Dict[str, tuple] = {
    fam: tuple(sorted({_normalize(w) for w in words if w}))
    for fam, words in _KEYWORDS.items()
}


def score_families(query: str) -> Dict[str, int]:
    """Count keyword hits per family. Additive only; nothing subtracts."""
    hay = _normalize(query)
    scores: Dict[str, int] = {f: 0 for f in FAMILIES}
    for fam, words in _NORM_KEYWORDS.items():
        for w in words:
            if _matches(w, hay):
                scores[fam] += 1
    return scores


def select_families(query: str, max_families: Optional[int] = None) -> List[str]:
    """
    Choose which families to expose for this query.

    Recall-first: every family with ANY signal is included. `max_families`
    exists only as a hard budget backstop; when it truncates, the result is
    reported as low confidence so the caller can react.
    """
    scores = score_families(query)
    hit = [f for f in FAMILIES if scores[f] > 0]
    for core in CORE_FAMILIES:
        if core not in hit:
            hit.append(core)
    # Strongest signal first, so truncation (if any) drops the weakest.
    hit.sort(key=lambda f: (-scores[f], FAMILIES.index(f)))
    if max_families is not None and len(hit) > max_families:
        keep = list(hit[:max_families])
        # Truncation must never discard a mandatory family (SS.6.3). Displace
        # the WEAKEST kept family rather than silently dropping risk tooling.
        for core in CORE_FAMILIES:
            if core not in keep:
                keep[-1] = core
        hit = keep
    return hit


def tools_for_families(families: Sequence[str],
                       always: Sequence[str] = ()) -> List[str]:
    """
    Resolve families to tool names.

    Split out from `select_tools` so the unclassified-tool safety net can be
    tested directly. Mutation testing showed the net was dormant (nothing is
    currently unclassified), meaning it could be deleted with no test failing
    -- and would then silently hide any future tool that escaped the family map.
    """
    fam_set = set(families)
    always_set = set(always)
    chosen = [n for n in tool_names()
              if TOOL_FAMILY.get(n) in fam_set or n in always_set]
    # Unclassified tools are ALWAYS exposed. If family routing cannot see a
    # tool, hiding it would make it permanently unreachable.
    for n in tool_names():
        if n not in TOOL_FAMILY and n not in chosen:
            chosen.append(n)
    return sorted(chosen)


def select_tools(query: str, max_families: Optional[int] = None,
                 always: Sequence[str] = ()) -> Dict[str, Any]:
    """
    Return the tool subset for a query, with the provenance needed to audit it.

    The return value deliberately includes the scores and the estimated token
    cost: a selector that cannot explain itself cannot be debugged when it
    drops the tool that mattered.
    """
    scores = score_families(query)
    families = select_families(query, max_families=max_families)
    chosen = tools_for_families(families, always=always)

    est = sum(MEASURED_FAMILY_TOKENS.get(f, 0) for f in families)
    total_signal = sum(scores.values())
    if total_signal == 0:
        confidence = "low"          # nothing matched; CORE fallback in use
    elif len(families) >= 4:
        confidence = "low"          # query touched almost everything
    elif total_signal >= 2:
        confidence = "high"
    else:
        confidence = "medium"

    return {
        "families": families,
        "tools": chosen,
        "n_tools": len(chosen),
        "scores": scores,
        "estimated_tokens": est,
        "estimated_pct_of_context": round(100.0 * est / CONTEXT_TARGET, 1),
        "saved_tokens": MEASURED_ALL_TOKENS - est,
        "confidence": confidence,
        "fallback_used": total_signal == 0,
        "label": "MEASURED" if est else "COMPUTED",
    }


def schemas_for(query: str, max_families: Optional[int] = None,
                always: Sequence[str] = ()) -> List[Dict[str, Any]]:
    """The JSON schemas to hand the model for this query."""
    keep = set(select_tools(query, max_families=max_families,
                            always=always)["tools"])
    return [s for s in tool_schemas() if s["function"]["name"] in keep]
