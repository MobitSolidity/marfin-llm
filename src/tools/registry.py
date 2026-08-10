"""
Tool registry and dispatcher (master prompt SS.5.3, SS.7).

This is the boundary between the model and the deterministic engine. The model
emits a tool call; this module validates and executes it. The model never
computes, and never sees a result without provenance.

SECURITY POSTURE (SS.11):
  - Whitelist only. An unknown tool name is refused, never eval'd.
  - Arguments are type-checked and coerced through the Persian-aware parser
    before reaching any calculation.
  - Tools are PURE: no network, no filesystem, no state mutation. Nothing here
    can place an order. Execution capability lives behind separate, gated
    modules that do not exist yet.
  - A tool raising an exception returns a structured error. The model must
    surface that error, not invent a number to replace it.
"""

from typing import Any, Dict, Callable
import inspect

from calc import returns_risk as rr
from calc.persian_num import parse_number

# Whitelist: tool name -> (callable, JSON schema for the model).
_REGISTRY: Dict[str, Dict[str, Any]] = {}


def register(name: str, fn: Callable, description: str,
             params: Dict[str, Any], required):
    _REGISTRY[name] = {
        "fn": fn,
        "schema": {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": params,
                    "required": list(required),
                },
            },
        },
    }


NUM = {"type": "number"}
ARR = {"type": "array", "items": {"type": "number"}}
FREQ = {"type": "string", "enum": ["daily", "weekly", "monthly",
                                   "quarterly", "annual"]}

register("simple_return", rr.simple_return,
         "Simple percentage return between two values.",
         {"start": NUM, "end": NUM}, ["start", "end"])

register("log_return", rr.log_return,
         "Natural-log return between two strictly positive prices.",
         {"start": NUM, "end": NUM}, ["start", "end"])

register("cagr", rr.cagr,
         "Compound annual growth rate. Use for multi-year growth, NOT a "
         "simple average.",
         {"start": NUM, "end": NUM, "years": NUM}, ["start", "end", "years"])

register("annualized_return", rr.annualized_return,
         "Geometrically annualize a series of periodic returns.",
         {"returns": ARR, "freq": FREQ}, ["returns"])

register("annualized_volatility", rr.annualized_volatility,
         "Annualized standard deviation of periodic returns.",
         {"returns": ARR, "freq": FREQ}, ["returns"])

register("sharpe_ratio", rr.sharpe_ratio,
         "Sharpe ratio. risk_free_rate is the ANNUAL rate and is "
         "de-annualized internally.",
         {"returns": ARR, "risk_free_rate": NUM, "freq": FREQ}, ["returns"])

register("sortino_ratio", rr.sortino_ratio,
         "Sortino ratio; penalizes downside deviation only.",
         {"returns": ARR, "risk_free_rate": NUM, "freq": FREQ,
          "target": NUM}, ["returns"])

register("max_drawdown", rr.max_drawdown,
         "Largest peak-to-trough decline. Takes an EQUITY CURVE, not returns.",
         {"equity": ARR}, ["equity"])

register("calmar_ratio", rr.calmar_ratio,
         "Annualized return divided by absolute maximum drawdown.",
         {"returns": ARR, "equity": ARR, "freq": FREQ}, ["returns", "equity"])

register("beta", rr.beta,
         "Beta of an asset's returns against market returns.",
         {"asset": ARR, "market": ARR}, ["asset", "market"])

register("alpha", rr.alpha,
         "Jensen's alpha, annualized.",
         {"asset": ARR, "market": ARR, "risk_free_rate": NUM, "freq": FREQ},
         ["asset", "market"])

register("correlation", rr.correlation,
         "Pearson correlation between two return series.",
         {"a": ARR, "b": ARR}, ["a", "b"])

register("covariance", rr.covariance,
         "Sample covariance between two return series.",
         {"a": ARR, "b": ARR}, ["a", "b"])

register("tracking_error", rr.tracking_error,
         "Annualized standard deviation of active returns vs a benchmark.",
         {"asset": ARR, "benchmark": ARR, "freq": FREQ},
         ["asset", "benchmark"])

register("information_ratio", rr.information_ratio,
         "Annualized active return divided by tracking error.",
         {"asset": ARR, "benchmark": ARR, "freq": FREQ},
         ["asset", "benchmark"])

register("value_at_risk", rr.value_at_risk,
         "Historical Value at Risk. Returns a negative number (a loss).",
         {"returns": ARR, "confidence": NUM}, ["returns"])

register("conditional_value_at_risk", rr.conditional_value_at_risk,
         "Expected shortfall: mean loss beyond the VaR threshold.",
         {"returns": ARR, "confidence": NUM}, ["returns"])

register("position_size", rr.position_size,
         "Units to trade so a stop-out loses exactly risk_pct of equity. "
         "risk_pct is a FRACTION (0.01 = 1%).",
         {"account_equity": NUM, "risk_pct": NUM, "entry": NUM, "stop": NUM},
         ["account_equity", "risk_pct", "entry", "stop"])

register("risk_reward", rr.risk_reward,
         "Reward-to-risk ratio for a trade setup.",
         {"entry": NUM, "stop": NUM, "target": NUM},
         ["entry", "stop", "target"])

register("portfolio_leverage", rr.portfolio_leverage,
         "Gross exposure divided by net equity.",
         {"gross_exposure": NUM, "net_equity": NUM},
         ["gross_exposure", "net_equity"])

register("concentration", rr.concentration,
         "Herfindahl concentration index of portfolio weights.",
         {"weights": ARR}, ["weights"])


def tool_schemas():
    """JSON schemas for injection into the model's chat template."""
    return [t["schema"] for t in _REGISTRY.values()]


def tool_names():
    return sorted(_REGISTRY)


def _coerce(value, spec):
    """Coerce model-supplied arguments, accepting Persian numerals."""
    t = spec.get("type")
    if t == "number":
        if isinstance(value, bool):
            raise TypeError("boolean supplied where number expected")
        if isinstance(value, (int, float)):
            return float(value)
        return parse_number(value)          # handles ۸٫۴ , ۱۰۰٬۰۰۰ etc.
    if t == "array":
        if not isinstance(value, (list, tuple)):
            raise TypeError("expected array, got %s" % type(value).__name__)
        return [_coerce(v, spec["items"]) for v in value]
    if t == "string":
        s = str(value)
        if "enum" in spec and s not in spec["enum"]:
            raise ValueError("invalid value %r; expected one of %s"
                             % (s, spec["enum"]))
        return s
    return value


def call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a whitelisted tool.

    Always returns a dict. On failure returns {"ok": False, "error": ...}
    rather than raising, so the caller can hand the error back to the model
    verbatim -- the model must report the failure, not paper over it.
    """
    if name not in _REGISTRY:
        return {"ok": False, "error": "unknown_tool",
                "message": "Tool %r is not registered. Available: %s"
                           % (name, ", ".join(tool_names()))}
    entry = _REGISTRY[name]
    props = entry["schema"]["function"]["parameters"]["properties"]
    required = entry["schema"]["function"]["parameters"]["required"]

    if not isinstance(arguments, dict):
        return {"ok": False, "error": "bad_arguments",
                "message": "arguments must be an object"}

    unknown = set(arguments) - set(props)
    if unknown:
        return {"ok": False, "error": "unknown_argument",
                "message": "Unexpected argument(s): %s" % ", ".join(sorted(unknown))}

    missing = [r for r in required if r not in arguments]
    if missing:
        return {"ok": False, "error": "missing_argument",
                "message": "Missing required argument(s): %s" % ", ".join(missing)}

    kwargs = {}
    for k, v in arguments.items():
        try:
            kwargs[k] = _coerce(v, props[k])
        except Exception as e:
            return {"ok": False, "error": "invalid_argument",
                    "message": "Argument %r: %s" % (k, e)}

    # Drop args the function does not accept (schema/impl drift guard).
    sig = inspect.signature(entry["fn"])
    kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}

    try:
        res = entry["fn"](**kwargs)
    except Exception as e:
        return {"ok": False, "error": type(e).__name__, "message": str(e),
                "guidance": "Report this refusal to the user. Do NOT substitute "
                            "an estimated value."}

    return {"ok": True, "name": res.name, "value": res.value,
            "formula": res.formula, "inputs": res.inputs,
            "units": res.units, "notes": res.notes, "label": res.label}
