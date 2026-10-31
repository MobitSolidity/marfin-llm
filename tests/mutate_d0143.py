#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mutation battery for D-0143: the about route, the crypto token lookup (crypto_resolve, the new
CoinGecko endpoints, the DataHub budget), refresh controls, /monitor, /learn and the tour, and the
responsive/accessibility rules. Each mutant weakens ONE guard; the oracle suites must fail.

Same contract as mutate_d0142.py: one file mutated at a time, restored in `finally`, an anchor that
does not occur exactly once is a SKIP (and a SKIP fails the battery), and the final line reports
whether the tree is restored and the oracles are green. test_d0143 runs first, so most mutants are
killed in about a second. After an interrupted run: `git status` before trusting anything (R23)."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ORACLES = [os.path.join(HERE, t) for t in ("test_d0143.py", "test_ui.py", "test_ask.py")]
ASK = "scripts/ask.py"
UI = "scripts/ui.py"
CSS = "scripts/ui_assets/app.css"
JS = "scripts/ui_assets/app.js"
CR = "src/market/crypto_resolve.py"
CG = "src/market/coingecko.py"
HUB = "src/rag/datahub.py"

MUTATIONS = [
    # -- (8) the about route ------------------------------------------------------------------
    (ASK, "about route no longer checked first",
     "        if is_about(question):                   # D-0143: before every other route",
     "        if False:"),
    (ASK, "long questions treated as self-introductions",
     "    if not t or len(t) > 60:\n        return False", "    if not t:\n        return False"),
    (ASK, "tool count hard-coded instead of read from the registry",
     '"n_tools": len(tool_schemas()),', '"n_tools": 85,'),
    (ASK, "pages= ignored (content no longer follows NAV)",
     '"pages": tuple(pages) if pages is not None else _ui_pages(),', '"pages": _ui_pages(),'),
    (UI, "no-model UI refuses the about / crypto questions",
     "            elif self.assistant is None and (ASK.is_about(question) or ASK.crypto_query(question)):",
     "            elif False:"),
    # -- (4) crypto route ---------------------------------------------------------------------
    (ASK, "crypto route runs without a DataHub (silent network use)",
     "        if self.hub is not None:                 # D-0143: before tools (an address is full of digits)",
     "        if True:"),
    (ASK, "crypto route taken for long questions",
     "    if len(raw) > 120:\n        return None", "    if False:\n        return None"),
    (ASK, "crypto keyword route takes any number of words",
     '    return " ".join(words) if 1 <= len(words) <= 3 else None', '    return " ".join(words) if words else None'),
    (ASK, "CoinGecko attribution dropped from crypto answers",
     '"sec_edgar_submissions", "coingecko"):', '"sec_edgar_submissions"):'),
    # -- (4) resolver -------------------------------------------------------------------------
    (CR, "two exact name matches -> silent pick of the first",
     "    if len(exact) == 1:", "    if len(exact) >= 1:"),
    (CR, "two coins with one symbol -> silent pick",
     "    if not exact and len(sym) == 1:", "    if not exact and len(sym) >= 1:"),
    (CR, "Tron checksum not verified",
     "    if len(raw) != 25 or raw[0] != 0x41:", "    if len(raw) != 25:\n        return True\n    if raw[0] != 0x41:"),
    (CR, "Solana length (32 bytes) not enforced",
     "        if raw is not None and len(raw) == 32 and len(t) >= 32:",
     "        if raw is not None and len(t) >= 32:"),
    (CR, "later chains spent after a hit",
     '                out["checked"] += [(p[2], "not_checked") for p in chains[i + 1:]]\n'
     '                out["status"], out["coin"] = "resolved", dict(coin, found_on=label)\n                return out',
     '                out["status"], out["coin"] = "resolved", dict(coin, found_on=label)\n                continue'),
    (CR, "search listing without detail reported as resolved",
     "        if coin is None:                      # listed by /search, then 404 on detail: say so",
     "        if False:"),
    (CR, "a 429 reported as a generic error",
     '        out["status"] = "rate_limited" if "429" in msg else "error"', '        out["status"] = "error"'),
    (CR, "candidates no longer ranked by market cap",
     '    return [c for _i, c in sorted(enumerate(coins), key=lambda ic: (ic[1].get("rank") is None,',
     '    return [c for _i, c in sorted(enumerate(coins), key=lambda ic: (False,'),
    # -- (4) CoinGecko client -----------------------------------------------------------------
    (CG, "HTTP 404 treated as a failure, not 'not on this chain'",
     "        if exc.code == 404:\n            raise CoinNotFound", "        if exc.code == 4040:\n            raise CoinNotFound"),
    (CG, "unknown platform reaches the URL",
     '    if p is None:\n        raise CoinGeckoError("platform %r is not one of %s"',
     '    if False:\n        raise CoinGeckoError("platform %r is not one of %s"'),
    (CG, "EVM address no longer lower-cased", "        a = a.lower()\n        ok = bool(_EVM_RE.match(a))",
     "        ok = bool(_EVM_RE.match(a.lower()))"),
    (CG, "search length unchecked", "    if not 1 <= len(q) <= 64:", "    if not q:"),
    (CG, "a zero price shown as 0", '        "price": price if price else None,', '        "price": price,'),
    (CG, "'coin not found' body parsed as data",
     '        if str(payload.get("error") or "").lower() == "coin not found":', "        if False:"),
    (CG, "search sent before the registry gate",
     "    check_access(SOURCE_KEY)\n    return parse_search(", "    return parse_search("),
    (CG, "contract lookup sent before the registry gate",
     "    check_access(SOURCE_KEY)\n    return parse_coin((http_get or _http_get)(contract_url(",
     "    return parse_coin((http_get or _http_get)(contract_url("),
    # -- (4) DataHub budget -------------------------------------------------------------------
    (HUB, "CoinGecko budget not enforced", '        if not b["left"]:\n            raise RateBudget',
     '        if False:\n            raise RateBudget'),
    (HUB, "CoinGecko calls not counted", "        self._cg_times.append(self.clock())", "        pass"),
    (HUB, "Demo-key limit used without a key",
     '        return CG_PER_MIN_DEMO if str(os.environ.get("COINGECKO_DEMO_API_KEY", "")).strip() else CG_PER_MIN_KEYLESS',
     "        return CG_PER_MIN_DEMO"),
    (HUB, "'not found' answers no longer cached as such",
     "            except _cg.CoinNotFound:\n                return _NOT_FOUND", "            except _cg.CoinNotFound:\n                raise"),
    # -- (6) refresh --------------------------------------------------------------------------
    (HUB, "CoinGecko minimum interval below 60 s", 'MIN_REFRESH_S = {"coingecko": 60, "alpha_vantage": 300}',
     'MIN_REFRESH_S = {"coingecko": 5, "alpha_vantage": 300}'),
    (HUB, "minimum interval not enforced", '            elif st["next_in_s"]:', "            elif False:"),
    (HUB, "Alpha Vantage refresh without confirmation", "            elif src in CONFIRM_SOURCES and not confirm:",
     "            elif False:"),
    (HUB, "failed refresh blanks the data instead of keeping it stale",
     "                if old is None:\n                    raise\n                self._mark_stale(key, exc)\n                return old[1]",
     "                raise"),
    (HUB, "stale mark never cleared after a successful retry", "        self._stale.pop(key, None)", "        pass"),
    (HUB, "refresh re-fetches every source, not the tab's own",
     "    def _keys_of(self, source):\n        return [k for k in self._cache if KEY_SOURCE.get(k[0]) == source]",
     "    def _keys_of(self, source):\n        return list(self._cache)"),
    (UI, "unknown tab mapped instead of refused", '        if tab not in self.TAB_SOURCES:\n            return self.page("/refresh"',
     '        if False:\n            return self.page("/refresh"'),
    (UI, "GET triggers a refresh", '        if method != "POST":\n            return self.page("/refresh"',
     '        if False:\n            return self.page("/refresh"'),
    (UI, "'back' keys not whitelisted",
     'for k, v in urllib.parse.parse_qs(str(f.get("back") or "")[:1000]).items() if k in self.BACK_KEYS}',
     'for k, v in urllib.parse.parse_qs(str(f.get("back") or "")[:1000]).items()}'),
    (UI, "confirmation box ignored", '        results = self.hub.refresh(self.TAB_SOURCES[tab], confirm=f.get("confirm") == "yes")',
     "        results = self.hub.refresh(self.TAB_SOURCES[tab], confirm=True)"),
    (CSS, "refresh button below the 44 px target", ".refresh-btn{min-width:var(--tap);min-height:var(--tap)}",
     ".refresh-btn{min-width:32px;min-height:32px}"),
    # -- (5) /monitor -------------------------------------------------------------------------
    (UI, "MACD drawn from too little history",
     '    except (ValueError, TypeError):\n        out.append(unknown("MACD(12,26,9)", 34))',
     '    except (ValueError, TypeError):\n        facts.append(("MACD", "0"))'),
    (UI, "an unoffered window accepted", "        if days not in self.MONITOR_DAYS:\n            days = 90",
     "        if days < 1:\n            days = 90"),
    (UI, "summary numbers not checked against the facts",
     '        extra = [n for n in ASK.L.extract_numbers(ASK.L.fold_digits(g["text"]))',
     '        extra = [n for n in []'),
    # -- (7) /learn and the tour --------------------------------------------------------------
    (UI, "chain count typed instead of read",
     '            "chains": len(_cg.PLATFORMS), "tabs": len(App.MARKET_TABS), "pages": len(NAV),',
     '            "chains": 7, "tabs": len(App.MARKET_TABS), "pages": 13,'),
    (UI, "a page without a /learn entry is silently blank",
     '        return "برای این صفحه هنوز توضیحی نوشته نشده است." if which == 1 else ""', '        return ""'),
    (UI, "tour visible without JS (overlay on every page)",
     """    return ('<aside class="tour is-hidden" id="tour" data-tour role="dialog\"""",
     """    return ('<aside class="tour" id="tour" data-tour role="dialog\""""),
    (JS, "tour re-shown after it was skipped",
     '      else if (steps.length && tget("andarz-tour-done") !== "1") { showTour(cur); }',
     "      else if (steps.length) { showTour(cur); }"),
    (JS, "tour storage access outside try/catch",
     "  function tset(k, v) { try { window.localStorage.setItem(k, v); } catch (e) { /* blocked: the tour just restarts */ } }",
     "  function tset(k, v) { window.localStorage.setItem(k, v); }"),
    # -- (1)(2)(3) rebrand, responsive, palette -----------------------------------------------
    (JS, "old theme key no longer honoured",
     'window.localStorage.getItem("andarz-theme") || window.localStorage.getItem("marfin-theme")',
     'window.localStorage.getItem("andarz-theme")'),
    (CSS, "touch target token shrunk", "--tap:44px", "--tap:32px"),
    (UI, "bare tables no longer wrapped in scrolling regions", "    return _BARE_TABLE.sub(",
     "    return doc or _BARE_TABLE.sub("),
    (UI, "change shown by colour alone (no arrow)", '"\\u25b2 " if v > 0 else ("\\u25bc " if v < 0 else ""),', '"", '),
    (UI, "a missing change shown as a value", """            return '<span class="muted">\\u2014</span>'\n        # D-0143: never colour alone""",
     """            v = 0.0\n        # D-0143: never colour alone"""),
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
