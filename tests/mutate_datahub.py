# -*- coding: utf-8 -*-
"""Mutation battery for D-0141 (ECB / World Bank / BIS-per-area clients, rag/datahub.py,
tools/catalog_fa.py): each mutant weakens one guard; test_datahub must fail."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ORACLE = os.path.join(HERE, "test_datahub.py")
ECB = "src/rag/ecb_stats.py"
WB = "src/rag/worldbank.py"
BIS = "src/rag/bis_stats.py"
HUB = "src/rag/datahub.py"
CAT = "src/tools/catalog_fa.py"

MUTATIONS = [
    # -- ECB ------------------------------------------------------------------------------
    (ECB, "EUR accepted as its own row", '        if c == "EUR":\n            raise', '        if False:\n            raise'),
    (ECB, "malformed currency code accepted", '        if not _CCY.match(c or ""):', "        if False:"),
    (ECB, "empty currency list accepted", "    if not cs or len(cs) > 60:", "    if len(cs) > 60:"),
    (ECB, "last_n range unchecked", "    if not isinstance(last_n, int) or not 1 <= last_n <= 1000:\n        raise EcbError",
     "    if False:\n        raise EcbError"),
    (ECB, "CSV shape unchecked", "    if not rows or any(k not in rows[0] for k in need):\n        raise EcbError",
     "    if not rows:\n        raise EcbError"),
    (ECB, "non-EUR denominator accepted", '        if (r.get("CURRENCY_DENOM") or "").strip() != "EUR":', "        if False:"),
    (ECB, "missing value becomes 0", '        if v in ("", "NaN", "NA"):\n            continue                                   # missing: skipped, never 0',
     '        if v in ("", "NaN", "NA"):\n            v = "0"'),
    (ECB, "zero/negative rate accepted", "        if not val > 0:", "        if False:"),
    (ECB, "monthly period accepted", "        if not _CCY.match(ccy) or not _DATE.match(d):", "        if not _CCY.match(ccy):"),
    # -- World Bank -------------------------------------------------------------------------
    (WB, "ISO-2 country code accepted", '        if not _ISO3.match(c or ""):', "        if False:"),
    (WB, "malformed indicator accepted", '    if not _IND.match(indicator or ""):', "    if False:"),
    (WB, "more than 30 countries accepted", "    if not cs or len(cs) > 30:", "    if not cs:"),
    (WB, "HTTP-200 error message not recognised",
     '    if isinstance(payload, list) and payload and isinstance(payload[0], dict) and "message" in payload[0]:',
     "    if False:"),
    (WB, "row for another indicator accepted", '        if (r.get("indicator") or {}).get("id") != indicator:', "        if False:"),
    (WB, "null year becomes 0", "        if v is None:\n            continue", "        if v is None:\n            v = 0"),
    (WB, "string value accepted", "        if isinstance(v, bool) or not isinstance(v, (int, float)):", "        if isinstance(v, bool):"),
    (WB, "missing unit accepted", '    if not unit:\n        raise WorldBankError', '    if False:\n        raise WorldBankError'),
    # -- BIS per area ----------------------------------------------------------------------
    (BIS, "per-area: non-daily frequency accepted",
     '        if not re.match(r"^[A-Z0-9]{2,3}$", area) or freq != "D":', '        if not re.match(r"^[A-Z0-9]{2,3}$", area):'),
    (BIS, "per-area: malformed area accepted",
     '        if not re.match(r"^[A-Z0-9]{2,3}$", area) or freq != "D":', '        if freq != "D":'),
    (BIS, "per-area: every row gets the requested key, not its own area",
     '        key = "%s.%s" % (freq, area)', '        key = "D."'),
    (BIS, "per-area: missing unit accepted",
     '    if not unit:\n        raise BisStatsError("a unit is required: a bare BIS number has no meaning (SS.5.2)")\n    rows = list(csv.DictReader(io.StringIO(text or "")))\n    need',
     '    rows = list(csv.DictReader(io.StringIO(text or "")))\n    need'),
    # -- DataHub ---------------------------------------------------------------------------
    (HUB, "cross rate from different days", "            same_day = usd is not None and usd.period_end == f.period_end",
     "            same_day = usd is not None"),
    (HUB, "conversion across different days", "        if da and db and da != db:", "        if False:"),
    (HUB, "NaN amount accepted", "isinstance(amount, bool) or amount != amount \\", "isinstance(amount, bool) or False \\"),
    (HUB, "boolean amount accepted", "        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or",
     "        if not isinstance(amount, (int, float)) or"),
    (HUB, "unknown currency converted", "            if c not in per:\n                raise", "            if False:\n                raise"),
    (HUB, "conversion direction inverted", "        rate = b / a                                   # units of `to` per 1 `frm`",
     "        rate = a / b"),
    (HUB, "older fix kept over the newest", "            if c not in latest or f.period_end > latest[c].period_end:",
     "            if c not in latest:"),
    (HUB, "discontinued policy-rate series not flagged",
     "            stale = newest is not None and (newest - f.period_end).days > STALE_DAYS", "            stale = False"),
    (HUB, "policy rates not sorted highest first", '        rows.sort(key=lambda r: (r["stale"], -r["rate"]))',
     '        rows.sort(key=lambda r: (r["stale"], r["rate"]))'),
    (HUB, "FRED series outside the catalogue fetched", "        if series not in FRED_MARKET:\n            raise",
     "        if False:\n            raise"),
    (HUB, "copyrighted S&P 500 added to the FRED catalogue", '    "DGS2": ("Percent",',
     '    "SP500": ("Index", "S&P 500", "x"),\n    "DGS2": ("Percent",'),
    (HUB, "a failing FRED card silently dropped",
     '                out.append({"series": s, "title_fa": FRED_MARKET[s][1], "unit": FRED_MARKET[s][0],',
     '                continue\n                out.append({"series": s, "title_fa": FRED_MARKET[s][1], "unit": FRED_MARKET[s][0],'),
    (HUB, "unknown World Bank indicator fetched", "        if indicator not in WB_INDICATORS:\n            raise",
     "        if False:\n            raise"),
    (HUB, "unknown country silently dropped", "        if not iso2 or len(iso2) != len(list(countries)):", "        if not iso2:"),
    (HUB, "empty stock symbol sent", "        if not sym:\n            raise", "        if False:\n            raise"),
    (HUB, "provider refusal crashes the page", "        except Exception as exc:                          # MarketDataError / AlphaVantageError",
     "        except KeyError as exc:"),
    (HUB, "cache never expires", "        if hit is not None and now - hit[0] < self.ttl:", "        if hit is not None:"),
    (HUB, "cache bypassed", "        if hit is not None and now - hit[0] < self.ttl:\n            return hit[1]",
     "        if False:\n            return hit[1]"),
    (HUB, "transient error not retried", "                if attempt == 0 and _transient(exc):", "                if False:"),
    (HUB, "format error retried like a timeout", "                if attempt == 0 and _transient(exc):",
     "                if attempt == 0:"),
    (HUB, "client error escapes as a crash", "            except _ERRORS as exc:\n                if attempt",
     "            except KeyError as exc:\n                if attempt"),
    # -- catalogue -----------------------------------------------------------------------
    (CAT, "duplicate catalogue entry accepted", "    if name in TOOLS:\n        raise", "    if False:\n        raise"),
    (CAT, "a worked example that does not run", '"years": 5})\n_t("annualized_return"', '"years": 0})\n_t("annualized_return"'),
    (CAT, "a tool missing from the catalogue", '_t("breakeven", "options",', '_x = ("breakeven", "options",'),
    (CAT, "an enum value without a Persian label", '"call": "خرید (call)", ', ""),
    (CAT, "a category left empty", '_t("dv01", "bonds",', '_t("dv01", "options",'),
]


def oracle():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("FRED_API_KEY", None)
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
