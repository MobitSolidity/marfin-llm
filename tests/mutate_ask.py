# -*- coding: utf-8 -*-
"""Mutation battery for D-0135 (rag/macro.py, scripts/ask.py): each mutant weakens one guard; test_ask must fail."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ORACLE = os.path.join(HERE, "test_ask.py")
MAC = "src/rag/macro.py"
ASK = "scripts/ask.py"

MUTATIONS = [
    (MAC, "unknown series accepted", "    if s is None:\n        raise MacroError(\"series %r is not in",
     "    if False:\n        raise MacroError(\"series %r is not in"),
    (MAC, "wrong source accepted", "    if source is not None and source != s[\"source\"]:",
     "    if False:"),
    (MAC, "resampling silently allowed", "    if frequency is not None and frequency != s[\"frequency\"]:",
     "    if False:"),
    (MAC, "BIS policy-rate word no longer required", "        if need and not any(fold(t) in q for t in need):",
     "        if False:"),
    (MAC, "empty window returns [] instead of refusing", "    if not facts:\n        raise MacroError(\"no %s observation",
     "    if False:\n        raise MacroError(\"no %s observation"),
    (MAC, "window end not enforced", "            and (end is None or f.period_end <= end)]",
     "            ]"),
    (MAC, "FRED unit drift not refused", "            if got is not None and got != _FRED_UNIT[series]:",
     "            if False:"),
    (MAC, "start-after-end accepted", "    if start and end and start > end:", "    if False:"),
    (MAC, "GDP scale word dropped", "\"Billions of Dollars\", \"units_note\": \"billion\"",
     "\"Billions of Dollars\", \"units_note\": None"),
    (MAC, "CPI unit undeclared", "\"Index 1982-1984=100\", \"units_note\": \"Index 1982-1984=100\"",
     "\"Index 1982-1984=100\", \"units_note\": None"),
    (MAC, "YoY falls back to a neighbouring month", "    if not prior or prior[0].value == 0:\n        return None",
     "    if not prior:\n        prior = [facts[0]]\n    if prior[0].value == 0:\n        return None"),
    (MAC, "percent tolerance widened to 1 point", "        tol = 0.5 * 10 ** -dec + 1e-12",
     "        tol = 1.0"),
    (MAC, "percent mismatch reported as supported", "            return \"CONTRADICTED\"\n    return \"SUPPORTED\"",
     "            return \"SUPPORTED\"\n    return \"SUPPORTED\""),
    (MAC, "COMPUTED row label removed", "COMPUTED by the simple_return tool from the %s and %s rows",
     "from the %s and %s rows"),
    (ASK, "tools route without a tool-family match", "        if len(operands) >= 2 and not sel[\"fallback_used\"]:",
     "        if len(operands) >= 2:"),   # D-0136: re-anchored after the operand fix
    (ASK, "rag evidence floor dropped", "MIN_TRUST = 80", "MIN_TRUST = 0"),
    (ASK, "CONTRADICTED no longer warns", "        if out[\"check\"] == \"CONTRADICTED\":\n            out[\"warnings\"].append",
     "        if False:\n            out[\"warnings\"].append"),
    (ASK, "tool restatement not checked", "            if not any(_restates(e[\"value\"], text) for e in executed if e[\"ok\"]):",
     "            if False:"),
    (ASK, "one contradicted claim diluted", "        if \"CONTRADICTED\" in statuses:\n            return \"CONTRADICTED\"",
     "        if False:\n            return \"CONTRADICTED\""),
    (ASK, "macro percent check skipped", "            pct = MACRO.verify_percent_claim(visible, passages)",
     "            pct = None"),
    (ASK, "execution guard bypassed", "        g = guard_execution_claims(_strip_calls(text), lang=out[\"lang\"])",
     "        g = {\"text\": _strip_calls(text), \"blocked\": False}"),
    (ASK, "tool-call block shown to the reader", "        g = guard_execution_claims(_strip_calls(text), lang=out[\"lang\"])",
     "        g = guard_execution_claims(text, lang=out[\"lang\"])"),
    # D-0135: the first form of these two was EQUIVALENT (a second `if` in the
    # comprehension still filtered; `facts = []` was followed by `continue`).
    (ASK, "stale warning kept over a guard notice", "                               if w not in WARN_CONTRADICTED.values()",
     "                               if True or w not in WARN_CONTRADICTED.values()"),
    (ASK, "turn not audited", "        if self.audit is not None:\n            self.audit.write(",
     "        if False:\n            self.audit.write("),
    (ASK, "macro source failure crashes the answer instead of falling back",
     "            except (MACRO.MacroError, AccessError, RuntimeError, ValueError) as exc:",
     "            except (AccessError,) as exc:"),
    (ASK, "--model and --server both accepted", "            if a.model:\n                print(\"ERROR: give --model OR --server",
     "            if False:\n                print(\"ERROR: give --model OR --server"),
    (ASK, "missing model file not refused", "            if not os.path.isfile(a.model):",
     "            if False:"),
    (ASK, "/quit ignored", "        if q in (\"/quit\", \"/exit\", \"/q\"):", "        if q in ():"),
    (ASK, "notices not printed", "    if out[\"notices\"]:\n        lines.append(\"\")\n        lines.extend(out[\"notices\"])",
     "    if False:\n        pass"),
    (ASK, "second tool turn dropped", "            text, m2 = self.runner.generate(follow)",
     "            m2 = None"),
    # --- D-0136 ------------------------------------------------------------
    (ASK, "series-name numbers counted as operands again",
     "        operands = (_numbers_in(MACRO.strip_series_terms(question)) if self.use_macro",
     "        operands = (_numbers_in(question) if self.use_macro"),
    (MAC, "Persian '10-year bonds' term removed",
     '                  "\\u0627\\u0648\\u0631\\u0627\\u0642 \\u06f1\\u06f0 \\u0633\\u0627\\u0644\\u0647",\n', ""),
    (MAC, "generic central-bank question selects nothing",
     "        if generic and any(fold(t) in q for t in rate_words):", "        if False:"),
    (MAC, "generic central-bank selection ignores the rate word",
     "        if generic and any(fold(t) in q for t in rate_words):", "        if generic:"),
    (MAC, "generic selection added even when a bank was named",
     '    if not any(k.startswith("WS_CBPOL:") for k in out):', "    if True:"),
    (MAC, "BIS rate limit not enforced", "    if wait:\n        sleep(wait)", "    if False:\n        sleep(wait)"),
    (MAC, "named year ignored (newest rows only)", "    if not years:\n        return {}",
     "    if True:\n        return {}"),
    (MAC, "year window reaches too few observations", "    need = int((today.year - start_year + 1) * per) + per",
     "    need = per"),   # D-0138: re-anchored
    (MAC, "named-year rows not all shown", '        max_rows = 16', '        max_rows = 2'),
    (ASK, "10-series evidence not trimmed", "            rows = 1 if (len(series) > 2 and not years) else 2",
     "            rows = 2"),
    (ASK, "HTML not escaped", '    esc = _h.escape(text or "", quote=True)', '    esc = text or ""'),
    (ASK, "HTML evidence not escaped",
     "                     % (i, _h.escape(e[\"text\"]), _h.escape(e[\"citation\"]), _h.escape(e[\"trust\"])))",
     "                     % (i, e[\"text\"], _h.escape(e[\"citation\"]), _h.escape(e[\"trust\"])))"),   # D-0140: re-anchored (turn_html)
    (ASK, "Persian turn not right-to-left", '    parts.append(\'<div class="turn" dir="%s">\' % ("rtl" if rtl else "ltr"))',
     '    parts.append(\'<div class="turn" dir="%s">\' % "ltr")'),   # D-0140: re-anchored (turn_html)
    (ASK, "--html flag ignored", "    html_path = None if a.no_html else (a.html or (DEFAULT_HTML if os.name == \"nt\" else None))",
     "    html_path = None"),
    # --- D-0137 ------------------------------------------------------------
    (ASK, "percent-only lines counted as unsupported again",
     "                if not MACRO.non_percent_magnitudes(claim):\n                    continue",
     "                if False:\n                    continue"),
    (ASK, "period lengths not masked", "                claim = MACRO.mask_period_words(claim)", "                pass"),
    (MAC, "Persian 'maahe' period word dropped", '"\\u0645\\u0627\\u0647\\u0647|', '"'),
    (ASK, "Markdown lists not rendered", '        m = _BULLET.match(line)', '        m = None'),
    (ASK, "list item text not escaped", "        out.append('<li dir=\"auto\">%s</li>' % _inline(m.group(\"body\")))",
     "        out.append('<li dir=\"auto\">%s</li>' % m.group(\"body\"))"),
    # --- D-0138 ------------------------------------------------------------
    (MAC, "transient network failure not retried", "            if attempt >= RETRIES or not is_transient(exc):",
     "            if True:"),
    (MAC, "data errors retried too", "            if attempt >= RETRIES or not is_transient(exc):",
     "            if attempt >= RETRIES:"),
    # (an extended loop bound alone was EQUIVALENT: the `attempt >= RETRIES` cap still stops it)
    (MAC, "retry cap raised (keeps retrying a dead source)", "            if attempt >= RETRIES or not is_transient(exc):",
     "            if attempt >= RETRIES + 3 or not is_transient(exc):"),
    (MAC, "no back-off between attempts", "            sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])", "            pass"),
    (MAC, "TLS handshake not classed transient", '"connection aborted", "handshake",', '"connection aborted",'),
    (MAC, "non-network exception classed transient",
     "    if not isinstance(exc, (_fred.FredError, _bis.BisStatsError)):\n        return False",
     "    if False:\n        return False"),
    (MAC, "CPI year window not widened for the YoY base",
     "    start_year = first - 1 if series in _YOY_SERIES else first", "    start_year = first"),
    (MAC, "every series widened (not only the index)",
     "    start_year = first - 1 if series in _YOY_SERIES else first", "    start_year = first - 1"),
    (MAC, "named-year CPI shows no COMPUTED change", "            return _named_year_yoy_evidence(series, facts, years, lang, months)",
     "            max_rows = 16"),
    (MAC, "named month ignored", "            and (not months or f.period_end.month in months)]", "            ]"),
    (MAC, "YoY at a missing month falls back to latest", "        if not hit:\n            return None",
     "        if not hit:\n            hit = [max(facts, key=lambda f: f.period_end)]"),
    (MAC, "Persian month matched inside a word",
     '            if re.search(r"(?<![\\w\\u0600-\\u06ff])%s(?![\\w\\u0600-\\u06ff])" % re.escape(n.strip()), q):',
     '            if n.strip() in q:'),
    (ASK, "month filter never used", "        months = MACRO.months_in(question) if years else []", "        months = []"),
    (ASK, "failure reason not kept in the record", '                out.setdefault("macro_errors", []).append("%s: %s" % (key, exc))',
     "                pass"),
]


def oracle():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run([sys.executable, ORACLE], cwd=ROOT, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
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
