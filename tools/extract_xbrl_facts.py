"""Extract REAL annual XBRL facts -- keyed on the PERIOD, not on `fy`.

A TRAP CAUGHT BY MY OWN FIRST PASS, and it would have poisoned every question.
`fy` in a companyconcept response is the fiscal year of the FILING THAT
CONTAINS the fact, not the fiscal year the fact describes. MEASURED on Apple
net income:

    fy=2023  val=94,680,000,000  end=2021-09-25   <- 94,680 is FY2023's figure
                                                     but `end` says 2021

A 10-K reports three years of income statement, so one filing contributes three
facts and they all carry the same `fy`. Keying questions on `fy` would have
asked "net income in fiscal 2023" and graded against a 2021 period.

So the period END is the only trustworthy key, and the fiscal year is derived
from it. Original filings only: for one period, the earliest `filed` wins,
because a later amendment restates the same period and would give two
different correct answers to one question.
"""
import datetime as dt
import json

WANT = {
    "aapl_netincome": ("Apple Inc.", "0000320193", "Net income", "duration"),
    "aapl_assets": ("Apple Inc.", "0000320193", "Total assets", "instant"),
    "aapl_equity": ("Apple Inc.", "0000320193",
                    "Total shareholders' equity", "instant"),
    "msft_revenue": ("Microsoft Corporation", "0000789019",
                     "Total revenue", "duration"),
    "msft_netincome": ("Microsoft Corporation", "0000789019",
                       "Net income", "duration"),
    "msft_assets": ("Microsoft Corporation", "0000789019",
                    "Total assets", "instant"),
    "goog_revenue": ("Alphabet Inc.", "0001652044",
                     "Total revenues", "duration"),
    "goog_netincome": ("Alphabet Inc.", "0001652044",
                       "Net income", "duration"),
    "jnj_revenue": ("Johnson & Johnson", "0000200406",
                    "Sales to customers", "duration"),
    "jnj_netincome": ("Johnson & Johnson", "0000200406",
                      "Net earnings", "duration"),
    "wmt_revenues": ("Walmart Inc.", "0000104169",
                     "Total revenues", "duration"),
    "wmt_netincome": ("Walmart Inc.", "0000104169",
                      "Consolidated net income", "duration"),
}

out = {}
for key, (entity, cik, label, kind) in sorted(WANT.items()):
    js = json.load(open("/tmp/r20/raw/%s.json" % key, encoding="utf-8"))
    best = {}
    for u in js.get("units", {}).get("USD", []):
        if u.get("form") != "10-K" or u.get("fp") != "FY":
            continue
        end = u.get("end")
        if not end:
            continue
        if kind == "duration":
            if not u.get("start"):
                continue
            d0 = dt.date.fromisoformat(u["start"])
            d1 = dt.date.fromisoformat(end)
            if not (350 <= (d1 - d0).days <= 380):
                continue
        else:
            if u.get("start"):
                continue          # an instant fact carries no start
        prev = best.get(end)
        if prev is None or (u.get("filed") or "") < (prev.get("filed") or ""):
            best[end] = u
    out[key] = {"entity": entity, "cik": cik, "label": label, "kind": kind,
                "by_end": best}

json.dump(out, open("/tmp/r20/facts2.json", "w"), indent=1)

# Show only the recent years the questions will use, so the numbers being
# committed can be eyeballed against the filings.
for key, v in out.items():
    print("== %-16s %s -- %s (%s)" % (key, v["entity"], v["label"],
                                      v["kind"]))
    for end in sorted(v["by_end"])[-4:]:
        r = v["by_end"][end]
        print("   end=%s  val=%-16s filed=%s  acc=%s  frame_fy=%s"
              % (end, r["val"], r.get("filed"), r.get("accn"), r.get("fy")))
