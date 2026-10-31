#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ask.py -- ask Andarz (اندرز) a question, on the i5-12400 (D-0135).

    python scripts\\ask.py --model C:\\models\\Qwen3.5-4B-Q4_K_M.gguf "What is the P/E ratio for a price of 150 and EPS of 8.4?"
    python scripts\\ask.py --model C:\\models\\Qwen3.5-4B-Q4_K_M.gguf          (interactive; /quit to leave)

WHY THIS FILE EXISTS
--------------------
Every phase so far produced a MEASUREMENT harness (scripts/run_phase4.py): it
asks fixed questions and grades them. There was no way to ask your OWN
question. This is that path -- and it is deliberately NOT a new pipeline. Every
prompt it sends is built by the same run_phase4 functions that produced the
recorded, graded results (Phase 7/8C), with the recommended options of release
0.10.x always on: --second-turn --refusal-language --execution-guard
--min-trust 80 --display --continue-budget 256. A second, hand-written prompt
path would be unmeasured, and this project has shipped an unconnected fix once
already (D-0091).

WHAT IT ADDS, AND WHY EACH PIECE
--------------------------------
  route      One route per question, chosen without the model:
               about  -- "introduce yourself", «خودت را معرفی کن», "what can
                         you do": answered from the live registries (D-0143),
                         never by the model, so it cannot go stale or improvise.
               crypto -- a contract address (EVM 0x..., Solana, Tron), or a
                         short question with "crypto"/"token"/"coin"/«رمزارز»/
                         «توکن» or a Persian coin name: looked up on CoinGecko
                         (market/crypto_resolve.py, D-0143), never by the model;
                         ambiguous names list ranked candidates. Needs a DataHub
                         (the web UI passes one); "Powered by CoinGecko".
               tools  -- the question carries >= 2 numbers AND the tool
                         selector matched a family (the measured calc path:
                         100 % tool-path correctness, Phase 7).
               macro  -- the question names a catalogue macro series
                         (rag/macro.py): live FRED / BIS data as evidence.
               rag    -- retrieval at min-trust 80 returned evidence.
               plain  -- otherwise; the model must say what it does not know.
  check      After the reply, OUTSIDE the model:
               rag/macro: every figure is verified against the evidence shown
                 (rag.citations.verify_claim; macro percents by
                 macro.verify_percent_claim). CONTRADICTED -> a warning line
                 is printed ABOVE the reply. The reply is never edited.
               tools: the tool's own result is printed as its own line, and a
                 warning appears if the reply does not restate it (MEASURED
                 failure: FA-CALC-002 credited a fabricated 9.74 % to a tool
                 whose answer was 10 %).
  notices    The attribution lines the sources used require (FRED's verbatim).
  audit      Each turn is appended to a hash-chained log (the Phase 8A
             AuditLog), default %USERPROFILE%\\.marfin\\ask_audit.jsonl.
             --no-audit turns it off. It never leaves the machine.

WHAT IT NEVER DOES
------------------
- Never places, previews or simulates an order: the registry has no execution
  tool (asserted at start, as in run_phase4), and any reply claiming a trade
  happened is replaced by the execution-guard notice.
- Never sends a prompt off the machine: in-process llama.cpp, or a LOOPBACK
  Ollama / LM Studio server. Remote APIs are not offered here on purpose.
- Never stores a key. FRED's key is read from the FRED_API_KEY environment
  variable by rag/fred.py and redacted from every error.

Exit codes: 0 answered (or interactive session ended), 2 refused before
loading anything (bad arguments, missing model or runtime), 3 internal error.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, _HERE)

import phase4_lib as L                                         # noqa: E402
import run_phase4 as RP                                        # noqa: E402
from llm import style as ST                                    # noqa: E402
from rag import macro as MACRO                                 # noqa: E402
from rag.citations import verify_claim                         # noqa: E402
from rag.documents import detect_language                      # noqa: E402
from rag.sources import AccessError, required_notices, get_source  # noqa: E402
from safety.untrusted import guard_execution_claims            # noqa: E402

#: The release-0.10.x options (tools/maintain.py PROMPT_OPTIONS), fixed here.
MIN_TRUST = 80
CONTINUE_BUDGET = 256
TOP_K = 4
DEFAULT_CORPUS = os.path.join("evals", "rag_corpus_combined.jsonl")
DEFAULT_AUDIT = os.path.join(os.path.expanduser("~"), ".marfin", "ask_audit.jsonl")

ROUTES = ("about", "crypto", "tools", "macro", "rag", "plain")

WARN_CONTRADICTED = {
    "en": "WARNING: a figure in this reply does NOT match the evidence shown to the model. "
          "Trust the evidence lines below, not the reply.",
    "fa": "\u0647\u0634\u062f\u0627\u0631: \u0639\u062f\u062f\u06cc \u062f\u0631 \u0627\u06cc\u0646 "
          "\u067e\u0627\u0633\u062e \u0628\u0627 \u0634\u0648\u0627\u0647\u062f \u0646\u0634\u0627\u0646\u200c"
          "\u062f\u0627\u062f\u0647\u200c\u0634\u062f\u0647 \u0628\u0647 \u0645\u062f\u0644 \u0645\u0637\u0627"
          "\u0628\u0642\u062a \u0646\u062f\u0627\u0631\u062f. \u0628\u0647 \u062e\u0637\u0648\u0637 \u0634\u0648"
          "\u0627\u0647\u062f \u067e\u0627\u06cc\u06cc\u0646 \u0627\u0639\u062a\u0645\u0627\u062f \u06a9\u0646"
          "\u06cc\u062f\u060c \u0646\u0647 \u0628\u0647 \u067e\u0627\u0633\u062e.",
}
WARN_TOOL_NOT_RESTATED = {
    "en": "WARNING: the reply does not restate the tool's result. The tool line is the computed answer.",
    "fa": "\u0647\u0634\u062f\u0627\u0631: \u067e\u0627\u0633\u062e \u0646\u062a\u06cc\u062c\u0647\u0654 "
          "\u0627\u0628\u0632\u0627\u0631 \u0631\u0627 \u062a\u06a9\u0631\u0627\u0631 \u0646\u0645\u06cc\u200c"
          "\u06a9\u0646\u062f. \u0639\u062f\u062f \u062e\u0637 \u0627\u0628\u0632\u0627\u0631\u060c \u067e\u0627"
          "\u0633\u062e \u0645\u062d\u0627\u0633\u0628\u0647\u200c\u0634\u062f\u0647 \u0627\u0633\u062a.",
}


# ---------------------------------------------------------------------------
# D-0143: the self-introduction, decided WITHOUT the model.
#
# MEASURED on the owner's machine: asked to introduce itself, the plain route
# (SYSTEM_BASE: one sentence, no name, no feature list) let the 4B model
# improvise, and it talked about Apple -- because Apple was the UI's example
# chip and sits in the SEC/RAG data. SYSTEM_BASE is part of the recorded,
# graded runs and is NOT edited. Instead this route answers from the live
# registries at answer time: VERSION, the web UI's NAV, the tool registry, the
# catalogue's categories, the DataHub source list, the provider registry and
# the execution mode. A page, tool or source added later appears here with no
# edit, and nothing here is a number typed by hand.
# ---------------------------------------------------------------------------
_ABOUT_EN = re.compile(
    r"^(?:please |hi |hello |hey )*(?:introduce yourself|who are you|what are you|what can you do|what do you do|"
    r"what can i do here|tell me about yourself|about you|what is andarz|who is andarz|help)\b")
_ABOUT_FA = re.compile(
    r"(?:خودت(?:و| را)? معرفی کن|معرفی کن خودت|خودتو? معرفی|تو کی هستی|شما کی هستید|تو چی هستی|"
    r"چه کارهایی (?:بلدی|می ?تونی|می ?توانی|انجام می ?دهی)|چه کار(?:ی)? (?:بلدی|می ?کنی|می ?توانی)|"
    r"اندرز (?:چیست|چیه|کیست)|درباره خودت|از خودت بگو|قابلیت هایت|امکانات(?:ت| تو| برنامه)?(?: چیست| چیه)?$)")
_FA_DIGITS = str.maketrans("0123456789", "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9")
EVIDENCE_LABELS = (
    ("VERIFIED", "checked against the source itself", "با خود منبع بررسی شده"),
    ("MEASURED", "measured on a real run or a live call", "در اجرای واقعی یا تماس زنده اندازه گیری شده"),
    ("COMPUTED", "calculated by a deterministic tool from stated inputs", "با ابزار قطعی از ورودی های مشخص محاسبه شده"),
    ("ESTIMATED", "an estimate, with its basis stated", "برآورد، همراه با مبنای آن"),
    ("UNKNOWN", "not known; never replaced by a guess or a 0", "نامعلوم؛ هرگز با حدس یا صفر جایگزین نمی شود"),
)


def _norm_q(question):
    t = (question or "").strip().lower()
    t = t.replace("\u200c", " ").replace("\u064a", "\u06cc").replace("\u0643", "\u06a9").replace("\u0623", "\u0627")
    t = re.sub(r"[\u061f?!.\u060c,;:\u06d4\u00bb\u00ab\"'()]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def is_about(question):
    """True for a short self-introduction / capability question (en or fa). Never true for a long question."""
    t = _norm_q(question)
    if not t or len(t) > 60:
        return False
    return bool(_ABOUT_EN.search(t) or _ABOUT_FA.search(t))


# ---------------------------------------------------------------------------
# D-0143: crypto token lookup, decided WITHOUT the model (CoinGecko data only).
# ---------------------------------------------------------------------------
_CRYPTO_KW = re.compile(r"(?:\b(?:crypto|cryptocurrency|token|coin)\b|\u0631\u0645\u0632\s?\u0627\u0631\u0632|"
                        r"\u062a\u0648\u06a9\u0646|\u0627\u0631\u0632 \u062f\u06cc\u062c\u06cc\u062a\u0627\u0644)")
_CRYPTO_STOP = set("what whats is are the price prices of for a an me show find look up lookup about info information "
                   "crypto cryptocurrency token coin tell current today now please on coingecko search details "
                   "\u0642\u06cc\u0645\u062a \u0686\u0646\u062f \u0686\u0646\u062f\u0647 \u0686\u0642\u062f\u0631 "
                   "\u0627\u0633\u062a \u0647\u0633\u062a \u0631\u0645\u0632\u0627\u0631\u0632 \u0631\u0645\u0632 "
                   "\u0627\u0631\u0632 \u062f\u06cc\u062c\u06cc\u062a\u0627\u0644 \u062a\u0648\u06a9\u0646 "
                   "\u0627\u0637\u0644\u0627\u0639\u0627\u062a \u062f\u0631\u0628\u0627\u0631\u0647 \u0631\u0627 "
                   "\u0631\u0648 \u0628\u06af\u0648 \u0646\u0634\u0627\u0646 \u0628\u062f\u0647 \u062c\u0633\u062a\u062c\u0648\u06cc "
                   "\u0627\u0645\u0631\u0648\u0632 \u0627\u0644\u0627\u0646".split())
_ADDR_RE = re.compile(r"(0[xX][0-9a-fA-F]{40}|[1-9A-HJ-NP-Za-km-z]{32,44})")


def crypto_query(question):
    """The token text to look up, or None. Addresses first (case kept), then Persian names, then keywords."""
    from market import crypto_resolve as CR
    raw = question or ""
    if len(raw) > 120:
        return None
    for m in _ADDR_RE.finditer(CR.normalise(raw)):
        c = CR.classify(m.group(1))
        if c["kind"] in ("evm", "solana", "tron"):
            return c["value"]
    t = _norm_q(raw)
    for k in sorted(CR.ALIASES_FA, key=len, reverse=True):
        if re.search(r"(?<!\S)%s(?!\S)" % re.escape(k), t):
            return k
    if not _CRYPTO_KW.search(t):
        return None
    words = [w for w in re.findall(r"[\w.\-]+", t) if w not in _CRYPTO_STOP]
    return " ".join(words) if 1 <= len(words) <= 3 else None


def _cfmt(v, pct=False):
    if v is None:
        return "\u2014"
    if pct:
        return "%s %+.2f%%" % ("\u25b2" if v > 0 else ("\u25bc" if v < 0 else "\u25cf"), v)
    if abs(v) >= 1:
        return "{:,.2f}".format(v)
    return "%.6g" % v


def crypto_text(lang, res):
    """The lookup result as text. Every figure is CoinGecko's (RETRIEVED); a missing one is a dash."""
    fa = lang == "fa"
    st, vs = res["status"], str(res.get("vs") or "usd").upper()
    lines = []
    if res.get("alias"):
        lines.append(("\u0646\u0627\u0645 \u0641\u0627\u0631\u0633\u06cc \u00ab%s\u00bb \u0628\u0627 \u062c\u062f\u0648\u0644 \u062b\u0627\u0628\u062a "
                      "(STATIC) \u0628\u0647 \u00ab%s\u00bb \u062a\u0628\u062f\u06cc\u0644 \u0634\u062f." if fa else
                      "Persian name \u00ab%s\u00bb mapped to \u00ab%s\u00bb by the STATIC alias table.")
                     % (res["alias"]["fa"], res["alias"]["search"]))
    if st == "resolved":
        c = res["coin"]
        L = (("\u0642\u06cc\u0645\u062a", "Price"), ("\u062a\u063a\u06cc\u06cc\u0631 \u06f2\u06f4 \u0633\u0627\u0639\u062a", "24h change"),
             ("\u062a\u063a\u06cc\u06cc\u0631 \u06f7 \u0631\u0648\u0632", "7d change"), ("\u0627\u0631\u0632\u0634 \u0628\u0627\u0632\u0627\u0631", "Market cap"),
             ("\u0631\u062a\u0628\u0647", "Rank"), ("\u062d\u062c\u0645 \u06f2\u06f4 \u0633\u0627\u0639\u062a", "24h volume"),
             ("\u0628\u0627\u0644\u0627\u062a\u0631\u06cc\u0646/\u067e\u0627\u06cc\u06cc\u0646\u200c\u062a\u0631\u06cc\u0646 \u06f2\u06f4 \u0633\u0627\u0639\u062a", "24h high / low"),
             ("\u0633\u0642\u0641 \u062a\u0627\u0631\u06cc\u062e\u06cc (ATH)", "All-time high"), ("\u06a9\u0641 \u062a\u0627\u0631\u06cc\u062e\u06cc (ATL)", "All-time low"),
             ("\u0639\u0631\u0636\u0647\u0654 \u062f\u0631 \u06af\u0631\u062f\u0634 / \u06a9\u0644 / \u062d\u062f\u0627\u06a9\u062b\u0631", "Supply circulating / total / max"),
             ("\u0622\u062e\u0631\u06cc\u0646 \u0628\u0647\u200c\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc CoinGecko", "CoinGecko last updated"))
        i = 1 if not fa else 0
        vals = ("%s %s" % (_cfmt(c["price"]), vs), _cfmt(c["change_24h"], True), _cfmt(c["change_7d"], True),
                "%s %s" % (_cfmt(c["market_cap"]), vs), "#%d" % c["rank"] if c.get("rank") else "\u2014",
                "%s %s" % (_cfmt(c["volume"]), vs), "%s / %s" % (_cfmt(c["high_24h"]), _cfmt(c["low_24h"])),
                "%s (%s)" % (_cfmt(c["ath"]), c.get("ath_date") or "\u2014"),
                "%s (%s)" % (_cfmt(c["atl"]), c.get("atl_date") or "\u2014"),
                "%s / %s / %s" % (_cfmt(c["circulating_supply"]), _cfmt(c["total_supply"]), _cfmt(c["max_supply"])),
                c.get("last_updated") or "\u2014")
        lines.append("**%s (%s)** \u2014 CoinGecko id: %s%s" % (c["name"], c["symbol"], c["id"],
                     ("  \u00b7  " + ("\u06cc\u0627\u0641\u062a\u0647 \u0631\u0648\u06cc " if fa else "found on ") + c["found_on"]) if c.get("found_on") else ""))
        lines += ["- %s: %s" % (lab[i], v) for lab, v in zip(L, vals)]
        from market import coingecko as CG
        addrs = [(p[2], c["platforms"][p[1]]) for p in CG.PLATFORMS if c["platforms"].get(p[1])]
        if addrs:
            lines.append("**%s**" % ("\u0622\u062f\u0631\u0633 \u0642\u0631\u0627\u0631\u062f\u0627\u062f\u0647\u0627" if fa else "Contract addresses"))
            lines += ["- %s: %s" % a for a in addrs]
        if res.get("candidates"):
            lines.append(("\u0646\u062a\u0627\u06cc\u062c \u0645\u0634\u0627\u0628\u0647 \u062f\u06cc\u06af\u0631: " if fa else "Other matches: ")
                         + ", ".join("%s (%s)" % (x["id"], x["symbol"]) for x in res["candidates"][:5]))
    elif st == "ambiguous":
        lines.append(("\u00ab%s\u00bb \u0628\u0627 \u0686\u0646\u062f \u0631\u0645\u0632\u0627\u0631\u0632 \u062c\u0648\u0631 \u0627\u0633\u062a\u061b \u0628\u062f\u0648\u0646 \u062d\u062f\u0633 "
                      "\u06cc\u06a9\u06cc \u0627\u0646\u062a\u062e\u0627\u0628 \u0646\u0645\u06cc\u200c\u0634\u0648\u062f. \u0634\u0646\u0627\u0633\u0647 (id) \u06cc\u0627 \u0622\u062f\u0631\u0633 \u0642\u0631\u0627\u0631\u062f\u0627\u062f \u0631\u0627 \u0628\u0646\u0648\u06cc\u0633\u06cc\u062f:"
                      if fa else "\u00ab%s\u00bb matches several coins; none is picked silently. Ask again with the id or the contract address:")
                     % res["query"])
        lines += ["- %s (%s)%s" % (x["id"], x["symbol"], "  rank #%d" % x["rank"] if x.get("rank") else "  unranked")
                  for x in res["candidates"]]
    elif st == "not_found":
        lines.append(("CoinGecko \u0631\u0645\u0632\u0627\u0631\u0632\u06cc \u0628\u0631\u0627\u06cc \u00ab%s\u00bb \u0646\u062f\u0627\u0631\u062f." if fa
                      else "CoinGecko has no coin for \u00ab%s\u00bb.") % res["query"])
    elif st == "invalid":
        lines.append(("\u0648\u0631\u0648\u062f\u06cc \u0645\u0639\u062a\u0628\u0631 \u0646\u06cc\u0633\u062a: %s" if fa else "Not a valid input: %s") % res["reason"])
    else:
        lines.append(("\u062f\u0627\u062f\u0647 \u062f\u0631 \u062f\u0633\u062a\u0631\u0633 \u0646\u06cc\u0633\u062a: %s" if fa else "Data unavailable: %s") % res.get("error"))
    if res.get("checked"):
        lines.append(("\u0632\u0646\u062c\u06cc\u0631\u0647\u200c\u0647\u0627: " if fa else "Chains: ")
                     + ", ".join("%s %s" % (n, s) for n, s in res["checked"]))
    lines.append(("RETRIEVED \u0627\u0632 CoinGecko\u060c \u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 \u0686\u0646\u062f \u0635\u0631\u0627\u0641\u06cc\u061b \u0644\u062d\u0638\u0647\u200c\u0627\u06cc \u0646\u06cc\u0633\u062a \u0648 \u062a\u0648\u0635\u06cc\u0647\u0654 \u0645\u0627\u0644\u06cc \u0646\u06cc\u0633\u062a."
                  if fa else "RETRIEVED from CoinGecko, aggregated across exchanges; not real-time and not financial advice."))
    return "\n".join(lines)


def _ui_pages():
    """The web UI's NAV, read live (the content follows any page added to or removed from NAV)."""
    # No import (ui imports this module; an import here would be a cycle): the UI passes its
    # NAV as pages=, and a caller that already loaded the UI is read from sys.modules.
    ui_mod = sys.modules.get("ui")
    return tuple(getattr(ui_mod, "NAV", ()) or ())


def about_facts(pages=None):
    """Every fact the self-introduction states, each read from its registry at call time."""
    from tools.registry import tool_schemas
    from tools import catalog_fa as CATALOG
    from rag import datahub as DH
    from llm import providers as LP
    from execution import mode as MODE
    try:
        version = open(os.path.join(_ROOT, "VERSION"), encoding="utf-8").read().strip()
    except OSError:
        version = "UNKNOWN"
    keys = []
    for row in DH.SOURCES_FA:
        need = re.findall(r"[A-Z][A-Z0-9_]*_(?:API_KEY|EMAIL|KEY)", row[3])
        keys.append({"key": row[0], "name_fa": row[1], "what_fa": row[2], "access_fa": row[3], "env": need,
                     "optional": "\u0628\u062f\u0648\u0646 \u06a9\u0644\u06cc\u062f" in row[3]})
    return {
        "name": "Andarz", "name_fa": "\u0627\u0646\u062f\u0631\u0632", "version": version,
        "pages": tuple(pages) if pages is not None else _ui_pages(),
        "n_tools": len(tool_schemas()),
        "categories_fa": tuple(t for _c, t in CATALOG.CATEGORIES),
        "sources": keys,
        "n_remote_providers": len([k for k in LP.PROVIDERS if k != "local"]),
        "mode": MODE.manifest()["mode"],
        "routes": ROUTES,
        "labels": EVIDENCE_LABELS,
    }


def about_text(lang, pages=None):
    f = about_facts(pages)
    if lang == "fa":
        d = (lambda n: str(n).translate(_FA_DIGITS))
        lines = ["**\u0627\u0646\u062f\u0631\u0632 (Andarz)**\u060c \u0646\u0633\u062e\u0647\u0654 %s: \u062f\u0633\u062a\u06cc\u0627\u0631 \u0645\u0627\u0644\u06cc \u0645\u062d\u0644\u06cc \u0648 \u062f\u0648\u0632\u0628\u0627\u0646\u0647 (\u0641\u0627\u0631\u0633\u06cc \u0648 \u0627\u0646\u06af\u0644\u06cc\u0633\u06cc) \u06a9\u0647 \u0631\u0648\u06cc \u0647\u0645\u06cc\u0646 \u0631\u0627\u06cc\u0627\u0646\u0647 \u0627\u062c\u0631\u0627 \u0645\u06cc \u0634\u0648\u062f. \u0627\u0648\u0644 \u0634\u0627\u0647\u062f\u060c \u0628\u0639\u062f \u067e\u0627\u0633\u062e." % f["version"],
                 "", "**\u0635\u0641\u062d\u0647 \u0647\u0627 (%s):**" % d(len(f["pages"]))]
        lines += ["- %s" % t for _h, t in f["pages"]] or ["- (\u0631\u0627\u0628\u0637 \u0648\u0628: python scripts/ui.py)"]
        lines += ["", "**\u0645\u0627\u0634\u06cc\u0646 \u062d\u0633\u0627\u0628 \u0647\u0627:** %s \u0645\u062d\u0627\u0633\u0628\u0647\u0654 \u0642\u0637\u0639\u06cc \u0628\u062f\u0648\u0646 \u0645\u062f\u0644\u060c \u062f\u0631 %s \u062f\u0633\u062a\u0647: %s." % (
            d(f["n_tools"]), d(len(f["categories_fa"])), "\u060c ".join(f["categories_fa"])),
                  "", "**\u0645\u0646\u0627\u0628\u0639 \u062f\u0627\u062f\u0647 (%s)** \u2014 \u0647\u06cc\u0686 \u06a9\u062f\u0627\u0645 \u0644\u062d\u0638\u0647 \u0627\u06cc \u06cc\u0627 \u0642\u0627\u0628\u0644 \u0645\u0639\u0627\u0645\u0644\u0647 \u0646\u06cc\u0633\u062a:" % d(len(f["sources"]))]
        lines += ["- %s: %s (%s)" % (s["name_fa"], s["what_fa"], s["access_fa"]) for s in f["sources"]]
        lines += ["", "**\u0645\u0648\u062a\u0648\u0631 \u067e\u0627\u0633\u062e:** \u0622\u0641\u0644\u0627\u06cc\u0646 (\u0645\u062f\u0644 \u0645\u062d\u0644\u06cc\u060c \u067e\u06cc\u0634 \u0641\u0631\u0636\u060c \u0647\u06cc\u0686 \u062f\u0627\u062f\u0647 \u0627\u06cc \u0627\u0632 \u0631\u0627\u06cc\u0627\u0646\u0647 \u062e\u0627\u0631\u062c \u0646\u0645\u06cc \u0634\u0648\u062f) \u06cc\u0627 \u0622\u0646\u0644\u0627\u06cc\u0646 (%s \u0627\u0631\u0627\u0626\u0647 \u062f\u0647\u0646\u062f\u0647\u0654 \u0622\u0645\u0627\u062f\u0647 \u06cc\u0627 \u0627\u0631\u0627\u0626\u0647 \u062f\u0647\u0646\u062f\u0647\u0654 \u062e\u0648\u062f\u062a\u0627\u0646\u061b \u06a9\u0644\u06cc\u062f \u0641\u0642\u0637 \u062f\u0631 \u0645\u062a\u063a\u06cc\u0631 \u0645\u062d\u06cc\u0637\u06cc)." % d(f["n_remote_providers"]),
                  "**\u0645\u0633\u06cc\u0631\u0647\u0627\u06cc \u067e\u0627\u0633\u062e (\u0628\u062f\u0648\u0646 \u0645\u062f\u0644 \u0627\u0646\u062a\u062e\u0627\u0628 \u0645\u06cc \u0634\u0648\u0646\u062f):** %s." % "\u060c ".join(f["routes"]),
                  "", "**\u0627\u06cc\u0645\u0646\u06cc:** \u062d\u0627\u0644\u062a \u0627\u062c\u0631\u0627 %s (\u0641\u0642\u0637 \u062a\u062d\u0644\u06cc\u0644). \u0645\u0639\u0627\u0645\u0644\u0647\u0654 \u0648\u0627\u0642\u0639\u06cc \u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u0627\u0633\u062a \u0648 \u0627\u0632 \u0627\u06cc\u0646\u062c\u0627 \u0631\u0648\u0634\u0646 \u0646\u0645\u06cc \u0634\u0648\u062f\u061b \u0645\u0639\u0627\u0645\u0644\u0647\u0654 \u06a9\u0627\u063a\u0630\u06cc \u0641\u0642\u0637 \u0634\u0628\u06cc\u0647 \u0633\u0627\u0632\u06cc \u0627\u0633\u062a. \u062e\u0631\u0648\u062c\u06cc \u062a\u062d\u0644\u06cc\u0644\u06cc \u0627\u0633\u062a\u060c \u0646\u0647 \u062a\u0648\u0635\u06cc\u0647\u0654 \u0645\u0627\u0644\u06cc." % f["mode"],
                  "", "**\u0628\u0631\u0686\u0633\u0628 \u0647\u0627\u06cc \u0634\u0627\u0647\u062f:**"]
        lines += ["- %s: %s" % (k, fa) for k, _en, fa in f["labels"]]
        lines += ["", "\u0627\u06cc\u0646 \u067e\u0627\u0633\u062e \u0628\u062f\u0648\u0646 \u0645\u062f\u0644 \u0648 \u0627\u0632 \u0641\u0647\u0631\u0633\u062a \u0647\u0627\u06cc \u062e\u0648\u062f \u0628\u0631\u0646\u0627\u0645\u0647 \u0633\u0627\u062e\u062a\u0647 \u0634\u062f\u0647 \u0627\u0633\u062a (VERIFIED \u062f\u0631 \u0644\u062d\u0638\u0647\u0654 \u067e\u0627\u0633\u062e)."]
        return "\n".join(lines)
    lines = ["**Andarz (\u0627\u0646\u062f\u0631\u0632)**, version %s: a local, bilingual (Persian and English) financial assistant "
             "that runs on this computer. Evidence first, then the answer." % f["version"],
             "", "**Pages (%d):**" % len(f["pages"])]
    lines += ["- %s  (%s)" % (h, t) for h, t in f["pages"]] or ["- (web UI: python scripts/ui.py)"]
    lines += ["", "**Calculators:** %d deterministic tools, no model needed, in %d categories." % (f["n_tools"], len(f["categories_fa"])),
              "", "**Data sources (%d)** -- none is real-time or tradable:" % len(f["sources"])]
    lines += ["- %s%s" % (s["key"], (" (no key; optional %s)" if s["optional"] else " (needs %s)") % ", ".join(s["env"])
                          if s["env"] else " (no key)") for s in f["sources"]]
    lines += ["", "**Engines:** offline (the local model, the default; nothing leaves the machine) or online "
                  "(%d built-in providers or your own; keys only in environment variables)." % f["n_remote_providers"],
              "**Routes (chosen without the model):** %s." % ", ".join(f["routes"]),
              "", "**Safety:** execution mode %s (analysis only). Live trading is disabled and cannot be switched on from "
                  "here; paper trading is a simulation. The output is analysis, not financial advice." % f["mode"],
              "", "**Evidence labels:**"]
    lines += ["- %s: %s" % (k, en) for k, en, _fa in f["labels"]]
    lines += ["", "This reply was built from the program's own registries, without the model (VERIFIED at answer time)."]
    return "\n".join(lines)


def _lang(question):
    return "fa" if detect_language(question) == "fa" else "en"


def _numbers_in(question):
    """Numbers the question states (years and citation markers masked)."""
    return L.extract_numbers(L.mask_years(L.fold_digits(question or "")))


def _strip_calls(text):
    """The reply as a person reads it: tool-call blocks removed."""
    return L._TOOL_BLOCK_RE.sub("", text or "").strip()


def _restates(value, text):
    """True if the reply states the tool's value (or that value as a percent)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return True                          # nothing numeric to restate
    tol = max(0.005, abs(v) * 0.0005)        # 2 dp, or 0.05 % of a large value
    return L.value_matches(v, _strip_calls(text), tol)


class Assistant(object):
    """
    One question in, one checked answer out. Pure apart from the runner, the
    macro fetcher and the audit log, all of which are injected -- the test suite
    drives every route with a scripted model and no network.
    """

    def __init__(self, runner, index=None, macro_fetch=None, audit=None,
                 clock=None, use_macro=True, pages=None, hub=None):
        self.runner = runner
        self.hub = hub                           # D-0143: DataHub for the crypto route (None: route off)
        self.pages = pages                       # None -> the web UI's NAV, read live (D-0143)
        self.index = index
        self.macro_fetch = macro_fetch or MACRO.fetch
        self.audit = audit
        self.clock = clock or (lambda: datetime.datetime.now(datetime.timezone.utc))
        self.use_macro = use_macro
        from tools.registry import tool_schemas
        self.schemas_by_name = {}
        for s in tool_schemas():
            fn = s.get("function", s)
            self.schemas_by_name[fn["name"]] = fn

    # ---- routing -------------------------------------------------------
    def route(self, question):
        """(route, detail). Decided without the model."""
        if is_about(question):                   # D-0143: before every other route
            return "about", {}
        if self.hub is not None:                 # D-0143: before tools (an address is full of digits)
            cq = crypto_query(question)
            if cq:
                return "crypto", {"query": cq}
        from tools.selector import select_tools
        sel = select_tools(question)
        # D-0136: numbers that are part of a catalogue series NAME ("10-year",
        # "اوراق ۱۰ ساله") are not operands. MEASURED: the owner's macro question
        # went to the tools route because "۱۰ ساله" and "۶ بانک" counted as 2.
        operands = (_numbers_in(MACRO.strip_series_terms(question)) if self.use_macro
                    and MACRO.select(question) else _numbers_in(question))
        if len(operands) >= 2 and not sel["fallback_used"]:
            return "tools", {"families": sel["families"]}
        if self.use_macro:
            series = MACRO.select(question)
            if series:
                return "macro", {"series": series}
        if self.index is not None and len(self.index):
            res = self.index.search(question, top_k=TOP_K, min_trust=MIN_TRUST)
            if res.ok:
                return "rag", {"retrieval": res}
        return "plain", {}

    # ---- the four routes ----------------------------------------------
    def _generate(self, prompt):
        text, m = self.runner.generate(prompt)
        return RP._continue_if_cut(self.runner, prompt, text, m, CONTINUE_BUDGET)

    def _tools(self, question, out):
        from tools.registry import call_tool
        from tools.selector import schemas_for
        first = RP.build_tools_prompt(question, schemas_for(question), refusal_language=True)
        text, m = self._generate(first)
        calls = L.parse_tool_calls(text)[0]
        if L.TOOL_CALL_CAP is not None:
            calls = calls[:L.TOOL_CALL_CAP]
        executed = []
        for c in calls:
            res = call_tool(c["name"], c["arguments"])
            executed.append({"name": c["name"], "arguments": c["arguments"], "ok": res.get("ok"),
                             "value": res.get("value"), "error": res.get("error"),
                             "unit": res.get("units")})
        out["tool_results"] = executed
        if executed:
            follow = RP.build_tools_followup_prompt(first, text, executed)
            text, m2 = self.runner.generate(follow)
            out["second_turn_new_calls"] = len(L.parse_tool_calls(text)[0])   # never executed
        if executed and any(e["ok"] for e in executed):
            if not any(_restates(e["value"], text) for e in executed if e["ok"]):
                out["warnings"].append(WARN_TOOL_NOT_RESTATED[out["lang"]])
        return text

    def _evidence_answer(self, question, passages, out, macro_series=()):
        prompt = RP.build_rag_prompt(question, passages, refusal_language=True)
        text, _m = self._generate(prompt)
        out["evidence"] = [{"citation": p.provenance.citation(), "text": p.text,
                            "source": p.provenance.source, "trust": p.provenance.trust_level}
                           for p in passages]
        out["check"] = self._check(text, passages, macro_series)
        if out["check"] == "CONTRADICTED":
            out["warnings"].append(WARN_CONTRADICTED[out["lang"]])
        return text

    def _check(self, text, passages, macro_series):
        """SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED / CONTRADICTED / NOT_CHECKED."""
        visible = _strip_calls(text)
        if not visible or L.is_abstention(visible):
            return "NOT_CHECKED"
        statuses = []
        if macro_series:
            pct = MACRO.verify_percent_claim(visible, passages)
            if pct:
                statuses.append(pct)
        for claim in L.split_claims(visible):
            if macro_series:
                # D-0137: a claim whose only magnitudes are percentages was
                # already judged by verify_percent_claim above. verify_claim
                # SKIPS percentages by design, so it reports "no numeric
                # magnitude" (UNSUPPORTED) for exactly those lines -- MEASURED on
                # the owner's 2026-10-23 run: 7 correct figures, verdict
                # PARTIALLY_SUPPORTED. Also drop the "12" of "12-month" / "۱۲ ماهه":
                # a period length, not a figure (it matched a stray 12 by luck).
                claim = MACRO.mask_period_words(claim)
                if not MACRO.non_percent_magnitudes(claim):
                    continue
            per = [verify_claim(claim, p).status for p in passages]
            statuses.append("SUPPORTED" if "SUPPORTED" in per else
                            "CONTRADICTED" if "CONTRADICTED" in per else "UNSUPPORTED")
        if not statuses:
            return "NOT_CHECKED"
        if "CONTRADICTED" in statuses:
            return "CONTRADICTED"
        if all(s == "SUPPORTED" for s in statuses):
            return "SUPPORTED"
        return "PARTIALLY_SUPPORTED" if "SUPPORTED" in statuses else "UNSUPPORTED"

    def _macro(self, question, series, out):
        passages, used, notes = [], [], []
        years = MACRO.years_in(question)
        months = MACRO.months_in(question) if years else []
        for key in series:
            try:
                # D-0136: a question naming a year gets that year's window, never
                # just the newest rows (RAG-EN-004: "January 2024").
                facts = self.macro_fetch(key, **MACRO.window_for(key, years, self.clock().date()))
            except (MACRO.MacroError, AccessError, RuntimeError, ValueError) as exc:
                # D-0138: say WHICH source failed and that it was retried, in
                # plain words; the raw TLS text stays in the record for support.
                notes.append("%s (%s): %s" % (key, MACRO.SERIES[key]["source"],
                                              "network timeout after %d retries" % MACRO.RETRIES
                                              if MACRO.is_transient(exc) else exc))
                out.setdefault("macro_errors", []).append("%s: %s" % (key, exc))
                continue
            # D-0136: several series in one question -> newest row each (CPI keeps
            # its year-earlier row + COMPUTED change). MEASURED: the owner's
            # 10-series question rendered 22 evidence rows at 2 per series.
            rows = 1 if (len(series) > 2 and not years) else 2
            passages.extend(MACRO.evidence_for(key, facts, lang=out["lang"], years=years,
                                               max_rows=rows, months=months))
            used.append(key)
        out["macro_series"] = used
        out["macro_unavailable"] = notes
        if not passages:
            return None              # caller falls back; the reason is recorded
        out["data_as_of"] = max(p.period_end for p in passages).isoformat()
        out["sources"] = sorted({MACRO.SERIES[k]["source"] for k in used})
        return self._evidence_answer(question, passages, out, macro_series=used)

    def answer(self, question):
        question = (question or "").strip()
        if not question:
            raise ValueError("empty question")
        t0 = time.time()
        out = {"question": question, "lang": _lang(question), "warnings": [], "sources": [],
               "evidence": [], "tool_results": [], "check": None, "data_as_of": None}
        route, detail = self.route(question)
        text = None
        if route == "about":
            # Never the model: the registries answer (the runner may even be None here).
            text = about_text(out["lang"], self.pages)
            out["about"] = True
            out["no_model"] = "about"
        if route == "crypto":
            # Never the model: CoinGecko's figures, shown as retrieved (the runner may be None here).
            res = self.hub.crypto_lookup(detail["query"])
            text = crypto_text(out["lang"], res)
            out["crypto"] = res
            out["no_model"] = "crypto"
            out["sources"] = ["coingecko"]
            out["data_as_of"] = (res.get("coin") or {}).get("last_updated")
        if route == "tools":
            text = self._tools(question, out)
        elif route == "macro":
            text = self._macro(question, detail["series"], out)
            if text is None:                                  # no macro data: fall back
                route = "rag" if (self.index is not None and self.index.search(
                    question, top_k=TOP_K, min_trust=MIN_TRUST).ok) else "plain"
                detail = ({"retrieval": self.index.search(question, top_k=TOP_K, min_trust=MIN_TRUST)}
                          if route == "rag" else {})
        if route == "rag" and text is None:
            hits = list(detail["retrieval"].hits)
            out["sources"] = sorted({p.provenance.source for p in hits})
            text = self._evidence_answer(question, hits, out)
            ends = [p.provenance.effective_date for p in hits if p.provenance.effective_date]
            out["data_as_of"] = max(ends).isoformat() if ends else None
        if route == "plain" and text is None:
            text, _m = self._generate(RP.build_plain_prompt(question, refusal_language=True))
        out["route"] = route
        out["model_text"] = text
        g = guard_execution_claims(_strip_calls(text), lang=out["lang"])
        out["execution_guard_blocked"] = g["blocked"]
        if g["blocked"]:
            # The reader sees only the guard notice. A figure check or a tool
            # warning about the REPLACED text would describe words that are no
            # longer shown (MEASURED in the smoke test: "Buy 100 TSLA" printed a
            # CONTRADICTED warning above the refusal notice).
            out["check"] = "BLOCKED" if out["check"] is not None else None
            out["warnings"] = [w for w in out["warnings"]
                               if w not in WARN_CONTRADICTED.values()
                               and w not in WARN_TOOL_NOT_RESTATED.values()]
        shown, n_latex = ST.plain_math(g["text"])
        out["reply"] = shown
        out["latex_rewritten"] = n_latex
        out["notices"] = self._notices(out)
        out["seconds"] = round(time.time() - t0, 2)
        out["answered_at"] = self.clock().isoformat()
        if self.audit is not None:
            self.audit.write("ask", self.clock(), question=question, route=route,
                             reply=out["reply"], check=out["check"],
                             tool_results=out["tool_results"], warnings=out["warnings"],
                             sources=out["sources"], blocked=g["blocked"])
        return out

    @staticmethod
    def _notices(out):
        keys = []
        for name in out["sources"]:
            for k in ("fred", "bis_statistics", "ecb_data_portal", "world_bank_indicators",
                      "imf_sdmx_data", "gdelt_doc", "nyfed_markets_data", "sec_edgar_xbrl",
                      "sec_edgar_submissions", "coingecko"):
                try:
                    if k == name or get_source(k).name == name:
                        keys.append(k)
                except Exception:          # noqa: BLE001 -- display path only
                    continue
        return required_notices(keys)


#: D-0143: turns answered without a model -> (render note, HTML meta note)
_NO_MODEL = {"about": ("built from the registries", "registries"),
             "crypto": ("CoinGecko data as retrieved", "CoinGecko")}


def render(out):
    """The answer as printed. Every section is labelled; nothing is hidden."""
    fa = out["lang"] == "fa"
    lines = ["route: %s%s%s" % (out["route"], "   data as of: %s" % out["data_as_of"]
                                if out.get("data_as_of") else "",
                                "   (no model: %s)" % _NO_MODEL[out["no_model"]][0] if out.get("no_model") else "")]
    for w in out["warnings"]:
        lines.append(w)
    lines.append("")
    lines.append(out["reply"] or "(empty reply)")
    if out["tool_results"]:
        lines.append("")
        lines.append("Calculations (deterministic tool, COMPUTED):")
        for e in out["tool_results"]:
            if e["ok"]:
                lines.append("  %s(%s) = %s%s" % (e["name"], json.dumps(e["arguments"], ensure_ascii=False),
                                                  e["value"], " %s" % e["unit"] if e.get("unit") else ""))
            else:
                lines.append("  %s: ERROR %s" % (e["name"], e["error"]))
    if out["evidence"]:
        lines.append("")
        lines.append("Evidence shown to the model (RETRIEVED; figure check: %s):" % out["check"])
        for i, e in enumerate(out["evidence"], 1):
            lines.append("  [%d] %s" % (i, e["text"]))
            lines.append("      %s  (%s)" % (e["citation"], e["trust"]))
    if out.get("macro_unavailable"):
        lines.append("")
        lines.append("Macro data not available: " + "; ".join(out["macro_unavailable"]))
    if out["notices"]:
        lines.append("")
        lines.extend(out["notices"])
    lines.append("")
    lines.append("\u0627\u06cc\u0646 \u062e\u0631\u0648\u062c\u06cc \u062a\u062d\u0644\u06cc\u0644\u06cc \u0627\u0633\u062a\u060c "
                 "\u0646\u0647 \u062a\u0648\u0635\u06cc\u0647\u0654 \u0645\u0627\u0644\u06cc \u0634\u062e\u0635\u06cc."
                 if fa else "Analytical information, not personalised financial advice.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# D-0136: right-to-left display.
#
# MEASURED by the owner 2026-10-23: in PowerShell the Persian reply is shown
# left-to-right with letters disconnected and words out of order. That is the
# Windows console itself (conhost, and Windows Terminal) -- it has no complete
# bidirectional-text support, so no text a program prints can make it right.
# A browser does bidi and Persian shaping correctly, so the answer is ALSO
# written to a small HTML file (dir="rtl" for Persian, dir="auto" per line so
# English lines stay left-to-right) and opened. Default ON for Windows,
# --html forces it elsewhere, --no-html turns it off.
#
# Every piece of text is html.escape()d: the reply and the evidence are
# UNTRUSTED (SS.10), and a reply containing "<script>" must display as text.
# ---------------------------------------------------------------------------
DEFAULT_HTML = os.path.join(os.path.expanduser("~"), ".marfin", "ask_answer.html")

_HTML_HEAD = """<!DOCTYPE html>
<html lang="fa"><head><meta charset="utf-8">%s
<title>Andarz</title>
<style>
body{font-family:Vazirmatn,"Segoe UI",Tahoma,Arial,sans-serif;font-size:17px;line-height:1.9;
     max-width:60em;margin:1.5em auto;padding:0 1em;background:#F8EADC;color:#09251C}
.turn{background:#FDF6EE;border:1px solid #E3C49E;border-radius:8px;padding:1em 1.4em;margin:1em 0}
.q{font-weight:bold;font-size:1.1em}
.meta{color:#3E5A4E;font-size:.85em;direction:ltr;text-align:left}
.warn{background:#F6E0C4;border:1px solid #A55704;padding:.5em .8em;border-radius:6px;margin:.6em 0}
.reply p{margin:.4em 0}
.reply ul,.reply ol{margin:.3em 0;padding-inline-start:1.6em}
.reply li{margin:.15em 0}
.ev,.calc{font-size:.9em;color:#09251C;border-top:1px dashed #E3C49E;margin-top:.8em;padding-top:.5em}
.ev div,.calc div{margin:.25em 0}
.cite{color:#3E5A4E;font-size:.85em;direction:ltr;text-align:left}
.note{color:#3E5A4E;font-size:.85em;margin-top:.8em}
</style></head><body>
"""


def _inline(text):
    """Escape, then render **bold** only. Nothing else from the model becomes markup."""
    import html as _h
    import re as _re
    esc = _h.escape(text or "", quote=True)
    return _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)


_BULLET = None


def _reply_html(text):
    """
    D-0137: the model writes Markdown lists ("*   item", "    *   sub-item",
    "1. item"). MEASURED on the owner's page: the stars were shown literally.
    Lines become <ul>/<ol> items, nested by indentation (4 spaces or a tab per
    level, at most 3 levels); every other line is a paragraph. Each line's TEXT
    still goes through _inline (escaped; only **bold** becomes markup), so the
    list structure is the only thing added.
    """
    import re as _re
    global _BULLET
    if _BULLET is None:
        _BULLET = _re.compile(r"^(?P<ind>[ \t]*)(?:(?P<ul>[*\-\u2022])|(?P<ol>\d{1,3}[.)]))\s+(?P<body>.*)$")
    out, stack = [], []                      # stack of open list tags, one per level
    for line in text.splitlines():
        m = _BULLET.match(line)
        if not m:
            while stack:
                out.append("</%s>" % stack.pop())
            if line.strip():
                out.append('<p dir="auto">%s</p>' % _inline(line.strip()))
            continue
        ind = m.group("ind").replace("\t", "    ")
        level = min(len(ind) // 2 // 2 + 1, 3)          # 0-3 spaces -> 1, 4-7 -> 2, ...
        tag = "ul" if m.group("ul") else "ol"
        while len(stack) > level:
            out.append("</%s>" % stack.pop())
        if len(stack) == level and stack[-1] != tag:
            out.append("</%s>" % stack.pop())
        while len(stack) < level:
            out.append('<%s dir="auto">' % tag)
            stack.append(tag)
        out.append('<li dir="auto">%s</li>' % _inline(m.group("body")))
    while stack:
        out.append("</%s>" % stack.pop())
    return "".join(out)


def turn_html(out):
    """D-0140: ONE answered turn as an HTML fragment (shared by the page and scripts/ui.py)."""
    import html as _h
    parts = []
    rtl = out["lang"] == "fa"
    parts.append('<div class="turn" dir="%s">' % ("rtl" if rtl else "ltr"))
    parts.append('<div class="q" dir="auto">%s</div>' % _inline(out["question"]))
    parts.append('<div class="meta">route: %s%s%s</div>' % (
        _h.escape(out["route"]), (" &middot; data as of: %s" % _h.escape(out["data_as_of"]))
        if out.get("data_as_of") else "", " &middot; no model (%s)" % _NO_MODEL[out["no_model"]][1]
        if out.get("no_model") else ""))
    for w in out["warnings"]:
        parts.append('<div class="warn" dir="auto">%s</div>' % _inline(w))
    parts.append('<div class="reply">%s</div>' % _reply_html(out["reply"] or "(empty reply)"))
    if out["tool_results"]:
        parts.append('<div class="calc" dir="ltr"><b>Calculations (deterministic tool, COMPUTED)</b>')
        for e in out["tool_results"]:
            txt = ("%s(%s) = %s%s" % (e["name"], json.dumps(e["arguments"], ensure_ascii=False),
                                      e["value"], " %s" % e["unit"] if e.get("unit") else "")
                   if e["ok"] else "%s: ERROR %s" % (e["name"], e["error"]))
            parts.append("<div>%s</div>" % _h.escape(txt))
        parts.append("</div>")
    if out["evidence"]:
        parts.append('<div class="ev"><b dir="ltr">Evidence shown to the model (RETRIEVED; figure check: %s)</b>'
                     % _h.escape(str(out["check"])))
        for i, e in enumerate(out["evidence"], 1):
            parts.append('<div dir="auto">[%d] %s</div><div class="cite">%s (%s)</div>'
                         % (i, _h.escape(e["text"]), _h.escape(e["citation"]), _h.escape(e["trust"])))
        parts.append("</div>")
    if out.get("macro_unavailable"):
        parts.append('<div class="note" dir="ltr">Macro data not available: %s</div>'
                     % _h.escape("; ".join(out["macro_unavailable"])))
    for n in out["notices"]:
        parts.append('<div class="note" dir="ltr">%s</div>' % _h.escape(n))
    parts.append('<div class="note">%s</div>' % _h.escape(render(out).rsplit("\n", 1)[-1]))
    parts.append("</div>")
    return "".join(parts)


def render_html(outs, refresh_seconds=None):
    """A complete HTML page for one or more answered turns (newest last)."""
    import html as _h
    head = _HTML_HEAD % ('<meta http-equiv="refresh" content="%d">' % refresh_seconds
                         if refresh_seconds else "")
    parts = [head]
    for out in outs:
        parts.append(turn_html(out))
    parts.append("</body></html>\n")
    return "".join(parts)


def write_html(path, outs, refresh_seconds=None):
    L.ensure_parent_dir(path)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_html(outs, refresh_seconds))
    return path


def build_index_from(path):
    """The RAG index over a corpus file, or None for --corpus none."""
    if not path or path.lower() == "none":
        return None
    full = path if os.path.isabs(path) else os.path.join(_ROOT, path)
    return RP.build_index(RP.load_jsonl(full))


def open_audit(path):
    if not path:
        return None
    from execution.paper import AuditLog
    L.ensure_parent_dir(path)
    return AuditLog(path)


def main(argv=None, runner=None, stdin=None):
    ap = argparse.ArgumentParser(description="Ask Andarz (local model only).")
    ap.add_argument("question", nargs="?", help="omit for an interactive session")
    ap.add_argument("--model", help="path to the GGUF file (in-process llama.cpp)")
    ap.add_argument("--server", choices=("ollama", "lmstudio"),
                    help="use a LOOPBACK Ollama / LM Studio server instead (needs --model-id)")
    ap.add_argument("--model-id", help="the model name as the server knows it")
    ap.add_argument("--server-url", help="loopback URL (default: the backend's standard port)")
    ap.add_argument("--ctx", type=int, default=16384)
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--max-tokens", type=int, default=RP.DEFAULT_MAX_TOKENS)
    ap.add_argument("--corpus", default=DEFAULT_CORPUS,
                    help="RAG corpus (JSONL), or 'none'. Default: the evaluation corpus")
    ap.add_argument("--no-macro", action="store_true", help="never fetch FRED / BIS data")
    ap.add_argument("--audit", default=DEFAULT_AUDIT, help="audit log path")
    ap.add_argument("--no-audit", action="store_true")
    ap.add_argument("--json", action="store_true", help="print the full record as JSON")
    ap.add_argument("--html", nargs="?", const=DEFAULT_HTML, default=None,
                    help="also write the answer as a right-to-left HTML page and open it "
                         "(default ON on Windows, whose console cannot show Persian correctly)")
    ap.add_argument("--no-html", action="store_true", help="never write or open the HTML page")
    ap.add_argument("--no-open", action="store_true", help="write the HTML page but do not open it")
    a = ap.parse_args(argv)
    html_path = None if a.no_html else (a.html or (DEFAULT_HTML if os.name == "nt" else None))

    if runner is None:
        if a.server:
            if a.model:
                print("ERROR: give --model OR --server, not both.")
                return 2
            from llm.local_server import ServerRunner, ServerError
            try:
                runner = ServerRunner(a.server, a.model_id, base_url=a.server_url,
                                      max_tokens=a.max_tokens, num_ctx=a.ctx, num_thread=a.threads)
            except ServerError as exc:
                print("ERROR: %s" % exc)
                return 2
        else:
            if not a.model:
                print("ERROR: --model <path to the GGUF> is required (or --server).")
                return 2
            if not os.path.isfile(a.model):
                print("ERROR: model file not found: %s" % a.model)
                return 2
            try:
                from llama_cpp import Llama
            except ImportError:
                print("ERROR: llama-cpp-python is not installed (pip install llama-cpp-python).")
                return 2
            RP.assert_no_execution_capability()
            print("loading %s ..." % os.path.basename(a.model))
            runner = RP.ModelRunner(Llama(model_path=a.model, n_ctx=a.ctx, n_threads=a.threads,
                                          verbose=False), max_tokens=a.max_tokens)
    RP.assert_no_execution_capability()
    try:
        index = build_index_from(a.corpus)
    except (OSError, ValueError, KeyError) as exc:
        print("ERROR: cannot load corpus %s: %s" % (a.corpus, exc))
        return 2
    audit = None if a.no_audit else open_audit(a.audit)
    bot = Assistant(runner, index=index, audit=audit, use_macro=not a.no_macro)

    session = []

    def one(q, interactive=False):
        out = bot.answer(q)
        print(L.safe(json.dumps(out, ensure_ascii=False, indent=2, default=str)
                     if a.json else render(out)))
        if html_path:
            session.append(out)
            # Interactive: the page lists the whole session and reloads itself
            # every 5 s, so it is opened once and then just follows along.
            write_html(html_path, session, refresh_seconds=5 if interactive else None)
            print("HTML (right-to-left): %s" % html_path)
            if not a.no_open and len(session) == 1:
                import webbrowser
                try:
                    webbrowser.open("file:///" + os.path.abspath(html_path).replace("\\", "/"))
                except Exception:                     # noqa: BLE001 -- display only
                    pass

    if a.question:
        one(a.question)
        return 0
    src = stdin or sys.stdin
    print("Andarz -- ask in Persian or English. /quit to leave.")
    while True:
        try:
            sys.stdout.write("\n> ")
            sys.stdout.flush()
            raw = src.readline()
        except KeyboardInterrupt:
            break
        if raw == "":
            break
        q = raw.strip()
        if q in ("/quit", "/exit", "/q"):
            break
        if q:
            one(q, interactive=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                           # noqa: BLE001
        print("INTERNAL ERROR (%s): %s -- a bug in ask.py, not a refusal." % (type(exc).__name__, exc))
        sys.exit(3)
