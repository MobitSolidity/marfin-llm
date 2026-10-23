#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ask.py -- ask marfin-llm a question, on the i5-12400 (D-0135).

    python scripts\\ask.py --model C:\\models\\Qwen3.5-4B-Q4_K_M.gguf "What was Apple's net income in fiscal 2023?"
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

ROUTES = ("tools", "macro", "rag", "plain")

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
                 clock=None, use_macro=True):
        self.runner = runner
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
        for key in series:
            try:
                # D-0136: a question naming a year gets that year's window, never
                # just the newest rows (RAG-EN-004: "January 2024").
                facts = self.macro_fetch(key, **MACRO.window_for(key, years, self.clock().date()))
            except (MACRO.MacroError, AccessError, RuntimeError, ValueError) as exc:
                notes.append("%s: %s" % (key, exc))
                continue
            # D-0136: several series in one question -> newest row each (CPI keeps
            # its year-earlier row + COMPUTED change). MEASURED: the owner's
            # 10-series question rendered 22 evidence rows at 2 per series.
            rows = 1 if (len(series) > 2 and not years) else 2
            passages.extend(MACRO.evidence_for(key, facts, lang=out["lang"], years=years,
                                               max_rows=rows))
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
                      "sec_edgar_submissions"):
                try:
                    if k == name or get_source(k).name == name:
                        keys.append(k)
                except Exception:          # noqa: BLE001 -- display path only
                    continue
        return required_notices(keys)


def render(out):
    """The answer as printed. Every section is labelled; nothing is hidden."""
    fa = out["lang"] == "fa"
    lines = ["route: %s%s" % (out["route"], "   data as of: %s" % out["data_as_of"]
                              if out.get("data_as_of") else "")]
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
<title>marfin-llm</title>
<style>
body{font-family:Vazirmatn,"Segoe UI",Tahoma,Arial,sans-serif;font-size:17px;line-height:1.9;
     max-width:60em;margin:1.5em auto;padding:0 1em;background:#fafafa;color:#222}
.turn{background:#fff;border:1px solid #ddd;border-radius:8px;padding:1em 1.4em;margin:1em 0}
.q{font-weight:bold;font-size:1.1em}
.meta{color:#666;font-size:.85em;direction:ltr;text-align:left}
.warn{background:#fff3cd;border:1px solid #e0b400;padding:.5em .8em;border-radius:6px;margin:.6em 0}
.reply p{margin:.4em 0}
.ev,.calc{font-size:.9em;color:#333;border-top:1px dashed #ccc;margin-top:.8em;padding-top:.5em}
.ev div,.calc div{margin:.25em 0}
.cite{color:#777;font-size:.85em;direction:ltr;text-align:left}
.note{color:#555;font-size:.85em;margin-top:.8em}
</style></head><body>
"""


def _inline(text):
    """Escape, then render **bold** only. Nothing else from the model becomes markup."""
    import html as _h
    import re as _re
    esc = _h.escape(text or "", quote=True)
    return _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)


def render_html(outs, refresh_seconds=None):
    """A complete HTML page for one or more answered turns (newest last)."""
    import html as _h
    head = _HTML_HEAD % ('<meta http-equiv="refresh" content="%d">' % refresh_seconds
                         if refresh_seconds else "")
    parts = [head]
    for out in outs:
        rtl = out["lang"] == "fa"
        parts.append('<div class="turn" dir="%s">' % ("rtl" if rtl else "ltr"))
        parts.append('<div class="q" dir="auto">%s</div>' % _inline(out["question"]))
        parts.append('<div class="meta">route: %s%s</div>' % (
            _h.escape(out["route"]), (" &middot; data as of: %s" % _h.escape(out["data_as_of"]))
            if out.get("data_as_of") else ""))
        for w in out["warnings"]:
            parts.append('<div class="warn" dir="auto">%s</div>' % _inline(w))
        parts.append('<div class="reply">')
        for line in (out["reply"] or "(empty reply)").splitlines():
            if line.strip():
                parts.append('<p dir="auto">%s</p>' % _inline(line))
        parts.append("</div>")
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
    ap = argparse.ArgumentParser(description="Ask marfin-llm (local model only).")
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
    print("marfin-llm -- ask in Persian or English. /quit to leave.")
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
