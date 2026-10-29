#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mutation battery for D-0142: user-defined providers, the settings store, the no-redirect
opener and list_models (src/llm), and the CoinGecko / Alpha Vantage markets / SEC facts
clients plus the new DataHub methods. Each mutant weakens ONE guard; the oracle suites
(test_provider_manager, test_market_data, test_llm_providers) must fail.

Same contract as mutate_datahub.py: one file mutated at a time, restored in `finally`,
an anchor that does not occur exactly once is a SKIP (and a SKIP fails the battery),
and the final line reports whether the tree is restored and the oracles are green.
After an interrupted run: `git status` before trusting anything (R23)."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ORACLES = [os.path.join(HERE, t) for t in ("test_provider_manager.py", "test_market_data.py",
                                            "test_llm_providers.py")]
PROV = "src/llm/providers.py"
SET = "src/llm/settings.py"
CLI = "src/llm/clients.py"
CG = "src/market/coingecko.py"
AVM = "src/market/av_markets.py"
SEC = "src/rag/sec_facts.py"
HUB = "src/rag/datahub.py"

MUTATIONS = [
    # -- providers: user-defined entries -----------------------------------------------------
    (PROV, "plaintext http to a remote host accepted",
     '    if u.startswith("http://") and not _LOOPBACK_URL_RE.match(u):\n        return (',
     '    if False:\n        return ('),
    (PROV, "endpoint without a scheme accepted",
     '    if not (u.startswith("https://") or u.startswith("http://")):\n        return "endpoint %r is not an http(s) URL"',
     '    if False:\n        return "endpoint %r is not an http(s) URL"'),
    (PROV, "endpoint with quotes/spaces accepted",
     r'''    if len(u) > 300 or any(c in u for c in " \t\r\n\"'<>\\"):''',
     "    if len(u) > 300:"),
    (PROV, "https URL without a host accepted",
     '    if u.startswith("https://") and not re.match(r"^https://[A-Za-z0-9.\\-\\[\\]:]+(/|$)", u):',
     '    if False:'),
    (PROV, "loopback regex unanchored (localhost.evil.com counts as local)",
     '_LOOPBACK_URL_RE = re.compile(r"^http://(localhost|127\\.0\\.0\\.1|\\[::1\\])(:\\d+)?(/|$)")',
     '_LOOPBACK_URL_RE = re.compile(r"^http://(localhost|127\\.0\\.0\\.1|\\[::1\\])")'),
    (PROV, "user entry may shadow a built-in provider",
     "    if name in PROVIDERS:\n        raise ProviderError(\"%r is a built-in provider",
     "    if False:\n        raise ProviderError(\"%r is a built-in provider"),
    (PROV, "invalid provider name accepted",
     "    if not isinstance(name, str) or not _USER_NAME_RE.match(name):",
     "    if not isinstance(name, str):"),
    (PROV, "unknown wire dialect accepted",
     "    if wire not in USER_WIRES:\n        raise ProviderError(\"provider %r: dialect",
     "    if False:\n        raise ProviderError(\"provider %r: dialect"),
    (PROV, "remote endpoint without a key variable accepted",
     "    if env is None and not is_loopback_url(url):",
     "    if False:"),
    (PROV, "malformed key variable name accepted",
     "        if not _ENV_NAME_RE.match(env):",
     "        if False:"),
    (PROV, "a data-source key may be sent to a model endpoint",
     "        if env in RESERVED_ENV_KEYS:",
     "        if False:"),
    (PROV, "user provider marked free (bypasses the spend gate)",
     '            "free_tier": None, "user_defined": True,',
     '            "free_tier": True, "user_defined": True,'),
    (PROV, "register is not all-or-nothing",
     "    clean = {}\n    for name, spec in dict(specs or {}).items():\n        clean[name] = validate_user_provider(name, spec)\n    _USER_PROVIDERS.clear()",
     "    clean = {}\n    _USER_PROVIDERS.clear()\n    for name, spec in dict(specs or {}).items():\n        clean[name] = validate_user_provider(name, spec)\n        _USER_PROVIDERS[name] = clean[name]"),
    (PROV, "user provider resolved before the built-in",
     "    spec = PROVIDERS.get(key) or _USER_PROVIDERS.get(key)",
     "    spec = _USER_PROVIDERS.get(key) or PROVIDERS.get(key)"),
    # -- settings store ----------------------------------------------------------------------
    (SET, "unsupported settings version accepted",
     '    if d.get("version", VERSION) != VERSION:', "    if False:"),
    (SET, "override for a user-defined/unknown provider accepted",
     '        if name not in P.PROVIDERS or name == "local":', '        if name == "local":'),
    (SET, "override base URL not validated",
     '            why = P.endpoint_problem(ov["base_url"])\n            if why:',
     '            why = P.endpoint_problem(ov["base_url"])\n            if False:'),
    (SET, "unknown engine accepted",
     "    if engine not in ENGINES:", "    if False:"),
    (SET, "non-boolean allow_paid accepted",
     "    if not isinstance(allow_paid, bool):", "    if False:"),
    (SET, "online engine without a provider accepted",
     '    if engine == "remote" and prov is None:', "    if False:"),
    (SET, "'local' accepted as the remote provider",
     '        if prov == "local" or (prov not in P.PROVIDERS and prov not in clean_custom):',
     '        if prov not in P.PROVIDERS and prov not in clean_custom:'),
    (SET, "settings saved without validation",
     "    clean = validate(data)\n    d = os.path.dirname", "    clean = data\n    d = os.path.dirname"),
    (SET, "settings file world-readable",
     "            os.chmod(tmp, 0o600)", "            os.chmod(tmp, 0o644)"),
    (SET, "override no longer wins over the built-in base URL",
     '    base = ov.get("base_url") or spec.get("base_url")', '    base = spec.get("base_url") or ov.get("base_url")'),
    (SET, "key value (not presence) reported",
     '"key_set": bool(env and str(os.environ.get(env, "")).strip()),',
     '"key_set": (env and str(os.environ.get(env, "")).strip()) or False,'),
    # -- clients: redirect refusal and list_models -------------------------------------------
    (CLI, "redirects followed again (key re-sent to the new host)",
     "_OPENER = urllib.request.build_opener(_NoRedirect)", "_OPENER = urllib.request.build_opener()"),
    (CLI, "list_models allowed for 'local'",
     '    if spec["wire"] == "local":\n        raise ProviderError("provider \'local\' has no network endpoint to test")',
     '    if False:\n        raise ProviderError("provider \'local\' has no network endpoint to test")'),
    (CLI, "anthropic list sent without anthropic-version",
     '        headers["anthropic-version"] = "2023-06-01"\n        if key:\n            headers["x-api-key"] = key',
     '        if key:\n            headers["x-api-key"] = key'),
    (CLI, "a redirect answer reported as success",
     "    if not 200 <= status < 300:\n        if 300 <= status < 400:",
     "    if not 200 <= status < 400:\n        if 300 <= status < 400:"),
    (CLI, "google 'models/' prefix kept",
     '            if wire == "google" and mid.startswith("models/"):', "            if False:"),
    (CLI, "model ids not redacted",
     "            ids.append(redact(mid, key)[:128])", "            ids.append(mid[:128])"),
    (CLI, "a non-list body accepted as an empty model list",
     "    if not isinstance(rows, list):\n        raise RemoteCallError(",
     "    if not isinstance(rows, list):\n        rows = []\n    if False:\n        raise RemoteCallError("),
    # -- CoinGecko -----------------------------------------------------------------------------
    (CG, "boolean accepted as a number",
     "    if isinstance(value, bool) or not isinstance(value, (int, float)):\n        raise CoinGeckoError",
     "    if not isinstance(value, (int, float)):\n        raise CoinGeckoError"),
    (CG, "NaN/inf accepted", "    if not math.isfinite(v):\n        raise CoinGeckoError", "    if False:\n        raise CoinGeckoError"),
    (CG, "negative price accepted", "    if v < 0 and not allow_negative:", "    if False:"),
    (CG, "per_page above the documented 250", "not 1 <= per_page <= 250:", "not 1 <= per_page <= 2500:"),
    (CG, "chart history beyond 365 days", "not 1 <= days <= 365:", "not 1 <= days <= 3650:"),
    (CG, "malformed coin id sent", "    if not _ID_RE.match(cid):", "    if False:"),
    (CG, "malformed demo key sent", "    if not _KEY_RE.match(k):", "    if False:"),
    (CG, "429 reported as a generic error",
     "        if exc.code == 429:", "        if False:"),
    (CG, "error body ({'status':...}) parsed as markets",
     '    if isinstance(payload, dict) and "status" in payload:\n        raise CoinGeckoError',
     '    if False:\n        raise CoinGeckoError'),
    (CG, "unpriced coin shown with price 0", "        if price is None or price == 0:", "        if price is None:"),
    (CG, "empty market list accepted",
     '    if not out:\n        raise CoinGeckoError("CoinGecko returned no priced coins")',
     '    if False:\n        raise CoinGeckoError("CoinGecko returned no priced coins")'),
    (CG, "single-day chart accepted", "    if len(by_day) < 2:", "    if len(by_day) < 1:"),
    # -- Alpha Vantage markets -------------------------------------------------------------------
    (AVM, "premium function permitted", "    if function not in FUNCTIONS:", "    if False:"),
    (AVM, "same-currency pair accepted", "    if a == b:", "    if False:"),
    (AVM, "malformed currency accepted", "    if not (_CCY.match(a) and _CCY.match(b)):", "    if False:"),
    (AVM, "inconsistent OHLC bar accepted",
     '        if not r["low"] <= min(r["open"], r["close"]) <= max(r["open"], r["close"]) <= r["high"]:',
     "        if False:"),
    (AVM, "inconsistent quote accepted",
     '    if abs((out["price"] - out["prev_close"]) - out["change"]) > max(0.011, 1e-6 * out["price"]):',
     "    if False:"),
    (AVM, "quote without a trading day accepted", "    if not _DATE.match(day):", "    if False:"),
    (AVM, "HTTP-200 error body in search not refused",
     "    for k in AV.ERROR_KEYS:\n        if k in payload:", "    for k in AV.ERROR_KEYS:\n        if False:"),
    (AVM, "budget not spent",
     '    (budget if budget is not None else AV.BUDGET).spend(', '    (lambda *a: None)('),
    (AVM, "licence gate skipped", "    assert_provider_usable(AV.PROVIDER_KEY)               # licence gate",
     "    pass               # licence gate"),
    (AVM, "search keywords unchecked", "    if not _KEYWORDS.match(k):", "    if False:"),
    # -- SEC facts -----------------------------------------------------------------------------
    (SEC, "request without a contact e-mail", "    if not _EMAIL.match(e):", "    if False:"),
    (SEC, "quarterly (10-Q) figures counted as annual",
     '            if not isinstance(r, dict) or r.get("form") != "10-K" or r.get("fp") != "FY":',
     '            if not isinstance(r, dict):'),
    (SEC, "non-annual flow span accepted", "                if span is None or not 350 <= span <= 380:",
     "                if span is None:"),
    (SEC, "an older filing wins over the latest", '            if prev is None or filed > prev["filed"]:',
     "            if prev is None:"),
    (SEC, "boolean fact value accepted",
     "            if not isinstance(end, str) or isinstance(v, bool) or not isinstance(v, (int, float)) \\",
     "            if not isinstance(end, str) or not isinstance(v, (int, float)) \\"),
    (SEC, "company with no annual figures accepted",
     '    if not any(m["points"] for m in metrics):', "    if False:"),
    (SEC, "bad CIK accepted",
     "    if isinstance(cik, bool) or not isinstance(cik, int) or not 0 < cik < 10 ** 10:\n        raise SecError(\"CIK",
     "    if False:\n        raise SecError(\"CIK"),
    (SEC, "redirects followed by the SEC client",
     "_OPENER = urllib.request.build_opener(_NoRedirect)", "_OPENER = urllib.request.build_opener()"),
    # -- DataHub ---------------------------------------------------------------------------------
    (HUB, "a bug disguised as 'data unavailable'",
     "        except (RuntimeError, ValueError, OSError) as exc:\n            raise DataError(str(exc))\n\n    def crypto(",
     "        except Exception as exc:\n            raise DataError(str(exc))\n\n    def crypto("),
    (HUB, "unoffered quote currency accepted", "        if vs not in _cg.VS_CURRENCIES:\n            raise DataError",
     "        if False:\n            raise DataError"),
    (HUB, "CoinGecko attribution dropped from the crypto table",
     '        return {"vs": vs, "rows": rows, "label": "RETRIEVED (CoinGecko, aggregated across exchanges; indicative)",\n                "notices": required_notices(["coingecko"]),',
     '        return {"vs": vs, "rows": rows, "label": "RETRIEVED (CoinGecko, aggregated across exchanges; indicative)",\n                "notices": [],'),
    (HUB, "FX change computed upside down",
     '        chg = (last["close"] / prev["close"] - 1.0) * 100.0 if prev else None',
     '        chg = (prev["close"] / last["close"] - 1.0) * 100.0 if prev else None'),
    (HUB, "unknown ticker silently skipped",
     "        if hit is None:\n            raise DataError", "        if False:\n            raise DataError"),
    (HUB, "malformed ticker sent to SEC", "        if not _sec._TICKER.match(t):", "        if False:"),
]


def oracle():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    for k in ("FRED_API_KEY", "ALPHAVANTAGE_API_KEY", "COINGECKO_DEMO_API_KEY", "SEC_CONTACT_EMAIL"):
        env.pop(k, None)
    for t in ORACLES:
        try:
            p = subprocess.run([sys.executable, t], cwd=ROOT, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        except subprocess.TimeoutExpired:
            return False
        if p.returncode != 0:
            return False
    return True


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
