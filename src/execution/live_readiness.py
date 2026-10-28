"""
Phase 11 (live-trading enablement): the readiness gate and its deliverables (D-0140).

WHAT THE OWNER ASKED FOR
------------------------
On 2026-10-26 the owner explicitly asked to start Phase 11. SYSTEM_PROMPT.md section 24 lists
8 prerequisites and 9 deliverables, and adds: "Passing this phase enables only the approved
scope. It does not grant unlimited autonomous trading authority."

WHAT THIS MODULE IS
-------------------
It is a *report*, not a switch. It reads the facts that already exist in code
(execution.mode.LIVE_PREREQUISITES, execution.brokers, configs/live-policy.json,
configs/risk-policy.json) and answers one question: may live trading be activated?
Today the answer is NO. The reasons are named, and they come from the repository,
not from prose.

It cannot enable anything. Live orders stay gated by execution.mode.live_trading_enabled(),
which needs all 12 SS.6.1 prerequisites. No function here writes to the execution
config. A test asserts that the module source contains no write call.

The kill-switch drill is a real run. It uses a PAPER engine in a temporary directory:
engage, check that a preview is refused, check that LLM and AUTOMATION cannot
disengage, check that a wrong phrase is refused, disengage as HUMAN, verify the audit
chain. Its result is MEASURED, but for PAPER only. A drill against a live adapter needs
a verified adapter, and none exists.

Imports only execution.* (the SS.5.6 separation that brokers.py documents).
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import tempfile
from typing import Any, Dict, List, Optional

from execution import brokers as BR
from execution import mode as M
from execution import paper as PP

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIVE_POLICY = os.path.join(_ROOT, "configs", "live-policy.json")
PAPER_POLICY = os.path.join(_ROOT, "configs", "risk-policy.json")

#: Limits where a SMALLER number is stricter.
_SMALLER_IS_STRICTER = ("max_order_notional", "max_daily_notional", "max_position_qty",
                        "max_concentration_pct", "max_daily_loss", "max_orders_per_minute",
                        "price_deviation_pct", "max_quote_age_s", "preview_ttl_s", "max_leverage")

#: SYSTEM_PROMPT section 24 deliverables, in its order.
DELIVERABLES = ("live-mode activation plan", "account allowlist", "instrument limits",
                "maximum order limits", "maximum daily loss", "kill-switch test",
                "per-order confirmation policy", "monitoring dashboard", "rollback plan")


class LivePolicyError(ValueError):
    """configs/live-policy.json is malformed or looser than the paper policy."""


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def check_live_policy(live: Dict[str, Any], paper: Dict[str, Any]) -> List[str]:
    """
    Problems with a live policy, as text. An empty list means the policy is well formed. It
    does NOT mean the policy is approved: approval is human_approved, checked separately.
    """
    p: List[str] = []
    if live.get("environment") != "LIVE":
        p.append("environment must be 'LIVE', got %r" % live.get("environment"))
    lim = dict(live.get("limits") or {})
    try:
        PP.RiskLimits(lim.pop("instrument_allowlist", None), **lim)
    except Exception as exc:                                  # noqa: BLE001 -- reported
        p.append("limits do not construct a valid RiskLimits: %s" % exc)
    L, P = live.get("limits") or {}, paper.get("limits") or {}
    for k in _SMALLER_IS_STRICTER:
        if k in L and k in P and L[k] > P[k]:
            p.append("%s %g is LOOSER than the paper limit %g" % (k, L[k], P[k]))
    extra = set(L.get("instrument_allowlist") or ()) - set(P.get("instrument_allowlist") or ())
    if extra:
        p.append("instruments not on the paper allowlist: %s" % ", ".join(sorted(extra)))
    if L.get("allow_short") and not P.get("allow_short"):
        p.append("allow_short is true live but false in paper")
    if live.get("per_order_confirmation") != "ALWAYS" and not live.get("automation_policy"):
        p.append("per_order_confirmation must be ALWAYS unless a separately approved "
                 "automation policy exists (SS.6.1)")
    for a in live.get("account_allowlist") or ():
        if not isinstance(a, str) or not a.startswith(PP.LIVE_ACCOUNT_PREFIX):
            p.append("live account ids must start with %r: %r" % (PP.LIVE_ACCOUNT_PREFIX, a))
    return p


def kill_switch_drill(state_dir: Optional[str] = None, now=None, engine_factory=None) -> Dict[str, Any]:
    """
    Run the emergency drill on a throwaway PAPER engine. Every step is recorded.
    `engine_factory` exists for the test that hands the drill a DEFECTIVE engine: a drill
    that cannot fail when the engine is broken proves nothing.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    own = state_dir is None
    tmp = tempfile.mkdtemp(prefix="marfin_drill_") if own else state_dir
    steps: List[Dict[str, Any]] = []

    def step(name, ok, detail=""):
        steps.append({"step": name, "ok": bool(ok), "detail": str(detail)[:200]})

    eng = (engine_factory or PP.PaperEngine)(tmp, {"PAPER-DRILL": 100000.0}, PP.RiskLimits(("AAPL",)))
    q = PP.QuoteSnapshot("AAPL", 100.0, 100.02, 100.01, now, "OPEN", "drill (synthetic)")
    eng.kill.engage("HUMAN", "Phase 11 drill", now)
    step("engage", eng.kill.engaged())
    pv = eng.preview("PAPER-DRILL", "PAPER", "AAPL", "buy", 1, "market", "drill-1", q, now=now)
    step("preview refused while engaged", pv["verdict"] == "REFUSE"
         and pv["risk_checks"]["kill_switch"]["status"] == "FAIL" and pv["confirmation_token"] is None)
    for who in ("LLM", "AUTOMATION", "WEBHOOK"):
        try:
            eng.kill.disengage(who, PP.KillSwitch.PHRASE, "drill", now)
            step("%s cannot disengage" % who, False, "disengaged")
        except PP.PaperError as exc:
            step("%s cannot disengage" % who, eng.kill.engaged(), exc)
    try:
        eng.kill.disengage("HUMAN", "yes", "drill", now)
        step("wrong phrase refused", False, "disengaged")
    except PP.PaperError as exc:
        step("wrong phrase refused", eng.kill.engaged(), exc)
    eng.kill.disengage("HUMAN", PP.KillSwitch.PHRASE, "drill complete", now)
    step("HUMAN disengages with the phrase", not eng.kill.engaged())
    pv2 = eng.preview("PAPER-DRILL", "PAPER", "AAPL", "buy", 1, "market", "drill-2", q, now=now)
    step("preview passes again", pv2["verdict"] == "PASS")
    ok, n, problem = eng.audit.verify()
    events = [r["event"] for r in eng.audit.records()]
    step("audit chain intact", ok and n == len(events), problem)
    step("every drill action audited",
         events.count("kill_switch_engaged") == 1 and events.count("kill_switch_disengaged") == 1
         and events.count("kill_switch_disengage_refused") == 3 and events.count("preview") == 2,
         ",".join(events))
    if own:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"environment": "PAPER", "label": "MEASURED (paper engine, synthetic quote)",
            "passed": all(s["ok"] for s in steps), "steps": steps, "audit_records": n,
            "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "live_drill": "NOT RUN: no verified live adapter exists"}


def readiness(live_path: str = LIVE_POLICY, paper_path: str = PAPER_POLICY,
              drill: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The Phase 11 gate. `ready` is True only if every prerequisite is met."""
    live, paper = _load(live_path), _load(paper_path)
    problems = check_live_policy(live, paper)
    bm = BR.manifest()
    unmet = list(M.unmet_live_prerequisites())
    drill = drill if drill is not None else kill_switch_drill()
    pr = [
        ("Phase 8A PASS", True, "D-0126: 14/14 tasks, 0 release blockers (paper engine)"),
        ("no critical execution blockers", True, "Phase 8A release blockers: 0"),
        ("verified broker live environment", bm["n_verified"] > 0,
         "%d broker adapters VERIFIED of %d catalogued; live-policy broker: %s"
         % (bm["n_verified"], len(bm["adapters"]), live.get("broker") or "not chosen")),
        ("independent authorised market data",
         "independent licensed market data" not in unmet, M.LIVE_PREREQUISITES[
             "independent licensed market data"][1][:160]),
        ("explicit user request", bool(live.get("requested_by_owner_on")),
         "owner request %s" % live.get("requested_by_owner_on")),
        ("explicit risk limits", live.get("human_approved") is True and not problems,
         "configs/live-policy.json human_approved=%s; %d problem(s)%s"
         % (live.get("human_approved"), len(problems),
            (": " + "; ".join(problems)) if problems else "")),
        ("audit and monitoring enabled", "audit logging" not in unmet,
         M.LIVE_PREREQUISITES["audit logging"][1]),
        ("emergency response tested", drill["passed"] and "emergency kill switch" not in unmet,
         "paper drill %s; %s" % ("PASSED" if drill["passed"] else "FAILED", drill["live_drill"])),
    ]
    prereq = [{"name": n, "met": bool(ok), "evidence": e} for n, ok, e in pr]
    deliverables = {
        "live-mode activation plan": "DRAFTED (docs/phase-reports/phase-11.md)",
        "account allowlist": ("DRAFTED, EMPTY: no live account exists" if not live.get("account_allowlist")
                              else "%d account(s)" % len(live["account_allowlist"])),
        "instrument limits": "DRAFTED: %s" % ", ".join(live["limits"]["instrument_allowlist"]),
        "maximum order limits": "DRAFTED: %g per order, %g per day" % (
            live["limits"]["max_order_notional"], live["limits"]["max_daily_notional"]),
        "maximum daily loss": "DRAFTED: %g" % live["limits"]["max_daily_loss"],
        "kill-switch test": "PAPER drill %s (MEASURED); live drill NOT RUN" % (
            "PASSED" if drill["passed"] else "FAILED"),
        "per-order confirmation policy": "DRAFTED: %s" % live.get("per_order_confirmation"),
        "monitoring dashboard": "BUILT: scripts/ui.py, Phase 11 page",
        "rollback plan": "DRAFTED (docs/phase-reports/phase-11.md#rollback)",
    }
    ready = all(p["met"] for p in prereq) and not unmet
    # D-0141: the owner suspended Phase 11 (no broker). A suspended phase is never ready,
    # whatever the other checks say, and the verdict says SUSPENDED rather than BLOCKED so
    # nobody reads "blocked" as "someone is working on unblocking it".
    suspended = str(live.get("status", "")).startswith("SUSPENDED")
    ready = ready and not suspended
    return {"phase": 11, "ready": ready, "suspended": suspended,
            "suspended_reason": live.get("suspended_reason") if suspended else None,
            "verdict": "SUSPENDED" if suspended else ("READY_FOR_OWNER_APPROVAL" if ready else "BLOCKED"),
            "live_trading_enabled": M.live_trading_enabled(),
            "prerequisites": prereq,
            "n_met": sum(p["met"] for p in prereq), "n_total": len(prereq),
            "ss61_unmet": unmet, "ss61_total": len(M.LIVE_PREREQUISITES),
            "live_policy": {"status": live.get("status"), "human_approved": live.get("human_approved"),
                            "problems": problems, "limits": live.get("limits"),
                            "broker": live.get("broker")},
            "deliverables": deliverables, "drill": drill,
            "note": "This report cannot enable live trading. It only says what is missing."}
