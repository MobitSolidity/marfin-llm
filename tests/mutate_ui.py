# -*- coding: utf-8 -*-
"""Mutation battery for D-0140 (scripts/ui.py, execution/live_readiness.py): each mutant weakens one guard; test_ui must fail."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ORACLE = os.path.join(HERE, "test_ui.py")
UI = "scripts/ui.py"
LR = "src/execution/live_readiness.py"
ASK = "scripts/ask.py"

MUTATIONS = [
    (UI, "non-loopback Host accepted", "        if hostname not in LOOPBACK_HOSTS:", "        if False:"),
    (UI, "CSRF token not checked", '        if method == "POST" and not secrets.compare_digest(str(form.get("csrf", "")), self.csrf):',
     '        if False:'),
    (UI, "PUT/DELETE allowed", '        if method not in ("GET", "POST"):', '        if False:'),
    (UI, "typed confirmation phrase skipped", '                if (f.get("phrase") or "").strip() != COMMIT_PHRASE:', '                if False:'),
    (UI, "commit made as LLM instead of HUMAN", '"ui-" + (f.get("preview_id") or ""), "HUMAN",', '"ui-" + (f.get("preview_id") or ""), "LLM",'),
    (UI, "kill switch disengaged by AUTOMATION", '                eng.kill.disengage("HUMAN", f.get("phrase") or ""',
     '                eng.kill.disengage("AUTOMATION", f.get("phrase") or ""'),
    (UI, "quote not labelled USER_SUPPLIED", '"USER_SUPPLIED (typed in the UI)"', '"UI"'),
    (UI, "commit form offered on a REFUSE preview", '                if pv["verdict"] == "PASS":\n                    keep', '                if True:\n                    keep'),
    (UI, "macro series not checked against the catalogue", "                if series not in MACRO.SERIES:", "                if False:"),
    (UI, "calculator result not escaped", "% (pretty, esc(r[\"value\"]), esc(r.get(\"units\") or \"\")",
     "% (pretty, r[\"value\"], esc(r.get(\"units\") or \"\")"),   # D-0141: re-anchored (redesign)
    (UI, "refusal message not escaped", "esc(r[\"error\"]), esc(r.get(\"message\")))", "esc(r[\"error\"]), r.get(\"message\"))"),
    (UI, "maintenance message not escaped", "            esc(x[\"subject\"]), esc(x[\"message\"]))", "            esc(x[\"subject\"]), x[\"message\"])"),
    (UI, "audit chain not verified", "        ok, n, problem = PP.AuditLog.verify(log)", "        ok, n, problem = True, 0, \"\""),
    (UI, "oversized body read", "                if n > MAX_BODY:", "                if False:"),
    (UI, "--host 0.0.0.0 accepted", "    if a.host != HOST:", "    if False:"),
    (UI, "--model and --server both accepted", "    if a.model and a.server:", "    if False:"),
    (UI, "missing model file not refused", "    if a.model and not os.path.isfile(a.model):", "    if False:"),
    (UI, "main ignores a refusal", "    if why:\n        print(", "    if False:\n        print("),
    # D-0142 re-anchor: the engine check now comes first, so the guard is an elif.
    (UI, "empty question sent to the model", "            elif not question:", "            elif False:"),
    (UI, "bad number crashes instead of refusing", "    except Exception:                                   # noqa: BLE001 -- converted, not swallowed",
     "    except ZeroDivisionError:"),
    (UI, "blank calc field sent as empty string", '        if raw == "":\n            continue', '        if False:\n            continue'),
    (UI, "CSP header dropped", "CSP = (\"default-src 'none'; style-src 'self'; script-src 'self'; img-src 'self' data:; \"",
     "CSP = (\"\""),   # D-0141: re-anchored (strict CSP constant)
    (UI, "form token missing from forms", "        return '<input type=\"hidden\" name=\"csrf\" value=\"%s\">' % esc(self.csrf)", "        return ''"),
    (UI, "internal error shown as a normal page", '"خطای داخلی", \'<div class="err">INTERNAL ERROR (%s): %s<br>\'', '"خطای داخلی", \'<div class="err">%s %s<br>\''),
    (ASK, "turn_html stops escaping evidence", "                     % (i, _h.escape(e[\"text\"]), _h.escape(e[\"citation\"])",
     "                     % (i, e[\"text\"], _h.escape(e[\"citation\"])"),
    (LR, "looser-than-paper limit accepted", "        if k in L and k in P and L[k] > P[k]:", "        if False:"),
    (LR, "instrument off the paper allowlist accepted", "    if extra:\n        p.append", "    if False:\n        p.append"),
    (LR, "per-order confirmation weakening accepted", '    if live.get("per_order_confirmation") != "ALWAYS" and not live.get("automation_policy"):', "    if False:"),
    (LR, "PAPER- account allowed live", "        if not isinstance(a, str) or not a.startswith(PP.LIVE_ACCOUNT_PREFIX):", "        if False:"),
    (LR, "environment not checked", '    if live.get("environment") != "LIVE":', "    if False:"),
    (LR, "short-selling escalation accepted", '    if L.get("allow_short") and not P.get("allow_short"):', "    if False:"),
    (LR, "unapproved limits count as explicit", '("explicit risk limits", live.get("human_approved") is True and not problems,',
     '("explicit risk limits", not problems,'),
    (LR, "ready ignores SS.6.1", "    ready = all(p[\"met\"] for p in prereq) and not unmet", "    ready = all(p[\"met\"] for p in prereq[:2])"),
    (LR, "broker counted without verification", '("verified broker live environment", bm["n_verified"] > 0,', '("verified broker live environment", True,'),
    (LR, "drill: LLM disengage not attempted", '    for who in ("LLM", "AUTOMATION", "WEBHOOK"):', '    for who in ("AUTOMATION", "WEBHOOK"):'),
    (LR, "drill: wrong phrase not tested", '        eng.kill.disengage("HUMAN", "yes", "drill", now)', '        eng.kill.disengage("HUMAN", PP.KillSwitch.PHRASE, "drill", now)'),
    # D-0140: the first form replaced only the verdict clause; the kill_switch clause
    # still failed the step, so it was EQUIVALENT. This drops the whole condition.
    (LR, "drill: refused preview not checked",
     '    step("preview refused while engaged", pv["verdict"] == "REFUSE"\n         and pv["risk_checks"]["kill_switch"]["status"] == "FAIL" and pv["confirmation_token"] is None)',
     '    step("preview refused while engaged", True)'),
    (LR, "drill temp dir left behind", "    if own:\n        shutil.rmtree(tmp, ignore_errors=True)", "    if False:\n        shutil.rmtree(tmp, ignore_errors=True)"),
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
