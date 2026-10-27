#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ui.py -- marfin-llm in the browser: every capability on one local page (D-0140).

    python scripts\\ui.py --model C:\\models\\Qwen3.5-4B-Q4_K_M.gguf
    python scripts\\ui.py --server lmstudio --model-id qwen3.5-4b
    python scripts\\ui.py                      (everything except "ask" works without a model)

Then open http://127.0.0.1:8765 (opened automatically).

WHY A WEB PAGE AND NOT A BETTER CONSOLE
---------------------------------------
The owner asked for "a proper UI, web or CLI, that exposes all capabilities and is simple
for others". The Windows console cannot show Persian correctly (MEASURED by the owner on
2026-10-23, D-0136): it has no bidirectional text and no Persian letter joining. A browser
handles both. So the UI is a page, served by the Python standard library, so nothing new
needs installing.

PAGES
-----
  /             dashboard: mode, model, maintenance status, Phase 11 gate
  /ask          ask a question (the scripts/ask.py Assistant: tools/macro/RAG/plain,
                figure check, execution guard, audit)
  /calc         all 85 deterministic calculators, each with a form built from its schema
  /macro        the 11 FRED / BIS catalogue series
  /paper        paper trading: preview -> human confirmation -> commit, cancel, reconcile,
                kill switch
  /audit        both hash-chained audit logs (ask and paper), with chain verification
  /maintenance  the Phase 10 report (tools/maintain.py)
  /providers    which model providers are configured (presence and length only, never keys)
  /phase11      the live-trading readiness gate and the kill-switch drill

SAFETY, AND WHY EACH RULE EXISTS
--------------------------------
- LOOPBACK ONLY. The server binds 127.0.0.1 and refuses any other --host. It also refuses
  requests whose Host header is not loopback, which defeats DNS rebinding: a web page on
  the internet cannot reach this server through a name that resolves to 127.0.0.1.
- Every POST carries a per-process random token (CSRF). Without it, any web page the
  owner visits could submit a paper order through his browser.
- Everything shown is html.escape()d. Model replies, retrieved evidence and audit records
  are UNTRUSTED (SS.10), and a reply containing "<script>" must display as text.
- No live trading path exists here. Paper commit needs principal HUMAN, the preview's
  single-use token, a typed confirmation, and PAPER_TRADING enabled in
  %USERPROFILE%\\.marfin\\execution.conf. This UI never writes that file: enabling a mode
  is a file the human edits (execution/mode.py explains why).
- Paper quotes are TYPED BY THE USER and are labelled USER_SUPPLIED. The only market data
  this project has (Alpha Vantage free tier) is END_OF_DAY, and the engine refuses a quote
  older than 5 s. A quote the user typed is honest about what it is. A delayed quote
  relabelled as fresh would not be.
- No key is ever displayed. /providers uses credential_status() (presence and length).

Exit codes: 0 stopped normally, 2 refused (bad arguments, model missing), 3 internal error.
"""
from __future__ import annotations

import argparse
import datetime
import html
import json
import os
import secrets
import sys
import urllib.parse

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_ROOT, "tools"))

import ask as ASK                                              # noqa: E402
from execution import live_readiness as LR                     # noqa: E402
from execution import mode as M                                # noqa: E402
from execution import paper as PP                              # noqa: E402
from rag import macro as MACRO                                 # noqa: E402
from tools import registry as REG                              # noqa: E402
from calc.persian_num import parse_number                      # noqa: E402

HOST = "127.0.0.1"
PORT = 8765
MAX_BODY = 64 * 1024
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "[::1]")
PAPER_DIR = os.path.join(os.path.expanduser("~"), ".marfin", "paper")
PAPER_ACCOUNT = "PAPER-0001"
PAPER_CASH = 100000.0
#: Typed by the human on the commit form. Distinct from the kill-switch phrase on purpose.
COMMIT_PHRASE = "CONFIRM"

NAV = (("/", "داشبورد"), ("/ask", "پرسش"), ("/calc", "ماشین‌حساب‌ها"), ("/macro", "داده‌های کلان"),
       ("/paper", "معاملهٔ کاغذی"), ("/audit", "گزارش ممیزی"), ("/maintenance", "نگهداری"),
       ("/providers", "ارائه‌دهنده‌ها"), ("/phase11", "فاز ۱۱ (معاملهٔ واقعی)"))

CSS = """
body{font-family:Vazirmatn,"Segoe UI",Tahoma,Arial,sans-serif;font-size:16px;line-height:1.8;margin:0;
     background:#f4f5f7;color:#222}
header{background:#1f3a5f;color:#fff;padding:.6em 1.2em}
header b{font-size:1.2em;margin-inline-end:1em}
nav a{color:#fff;margin-inline-end:1em;text-decoration:none;white-space:nowrap}
nav a.on{border-bottom:2px solid #ffd166}
main{max-width:64em;margin:1em auto;padding:0 1em}
.card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:1em 1.3em;margin:1em 0}
.ok{color:#11772e;font-weight:bold}.bad{color:#b00020;font-weight:bold}.due{color:#a36b00;font-weight:bold}
.warn{background:#fff3cd;border:1px solid #e0b400;padding:.5em .8em;border-radius:6px;margin:.6em 0}
.err{background:#fde2e4;border:1px solid #b00020;padding:.5em .8em;border-radius:6px;margin:.6em 0}
.banner{background:#e7f0ff;border:1px solid #3a6fd8;padding:.5em .8em;border-radius:6px;margin:.6em 0;font-weight:bold}
table{border-collapse:collapse;width:100%;font-size:.92em}td,th{border:1px solid #ddd;padding:.3em .5em;vertical-align:top}
th{background:#eef1f5}
.ltr{direction:ltr;text-align:left}code,pre{direction:ltr;text-align:left;font-family:Consolas,monospace;font-size:.88em}
pre{white-space:pre-wrap;background:#f7f7f7;padding:.6em;border-radius:6px;max-height:30em;overflow:auto}
input,select,textarea{font:inherit;padding:.25em .4em;margin:.15em 0}textarea{width:100%}
button{font:inherit;padding:.35em 1.1em;background:#1f3a5f;color:#fff;border:0;border-radius:6px;cursor:pointer}
button.danger{background:#b00020}
label{display:inline-block;min-width:11em}
.turn{background:#fff;border:1px solid #ddd;border-radius:8px;padding:1em 1.4em;margin:1em 0}
.q{font-weight:bold}.meta,.cite{color:#666;font-size:.85em;direction:ltr;text-align:left}
.ev,.calc{font-size:.9em;border-top:1px dashed #ccc;margin-top:.8em;padding-top:.5em}.note{color:#555;font-size:.85em}
.grid a{display:inline-block;margin:.15em .3em;padding:.1em .5em;background:#eef1f5;border-radius:4px;
        text-decoration:none;color:#1f3a5f;direction:ltr}
"""


def esc(x):
    return html.escape("" if x is None else str(x), quote=True)


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


class Response(object):
    __slots__ = ("status", "ctype", "body", "headers")

    def __init__(self, status, body, ctype="text/html; charset=utf-8", headers=None):
        self.status, self.body, self.ctype, self.headers = status, body, ctype, dict(headers or {})


def num(form, field):
    """A form number (Persian digits accepted). A bad value is a PaperError, shown as a refusal."""
    raw = (form.get(field) or "").strip()
    try:
        return parse_number(raw)
    except Exception:                                   # noqa: BLE001 -- converted, not swallowed
        raise PP.PaperError("%s: %r is not a number" % (field, raw))


def parse_array(text):
    """'1, 2 ، ۳' -> ['1', '2', '۳']. Strings, so the registry's Persian-digit parser sees them."""
    import re
    return [t for t in re.split(r"[,\s\u060c;]+", text or "") if t]


def form_to_arguments(schema, form):
    """
    Build call_tool arguments from a submitted form. A blank field is OMITTED (so the tool's
    own default or 'missing argument' refusal applies). Values stay strings: the registry
    coerces them, and it is the one place that refuses NaN, inf and bad enum values.
    """
    props = schema["function"]["parameters"]["properties"]
    args = {}
    for name, spec in props.items():
        raw = (form.get(name) or "").strip()
        if raw == "":
            continue
        t = spec.get("type")
        if t == "array":
            args[name] = parse_array(raw)
        elif t == "boolean":
            if raw not in ("true", "false"):
                raise ValueError("%s must be true or false" % name)
            args[name] = raw == "true"
        else:
            args[name] = raw
    return args


class App(object):
    """
    Pure request handling: handle(method, path, query, form, host) -> Response. The HTTP
    server is a thin shell around it, so every page and every refusal is testable without
    a socket.
    """

    def __init__(self, assistant=None, paper_dir=PAPER_DIR, ask_audit_path=ASK.DEFAULT_AUDIT,
                 macro_fetch=None, clock=_now, model_label=None, readiness=None, maintain=None):
        self.assistant = assistant
        self.csrf = secrets.token_urlsafe(24)
        self.paper_dir = paper_dir
        self.ask_audit_path = ask_audit_path
        self.macro_fetch = macro_fetch or MACRO.macro_data
        self.clock = clock
        self.model_label = model_label
        self._readiness = readiness or LR.readiness
        self._maintain = maintain
        self._engine = None
        self.history = []                       # answered turns this session, newest last

    # -- infrastructure ------------------------------------------------------
    def engine(self):
        if self._engine is None:
            rp = json.load(open(LR.PAPER_POLICY, encoding="utf-8"))
            lim = dict(rp["limits"])
            self._engine = PP.PaperEngine(self.paper_dir, {PAPER_ACCOUNT: PAPER_CASH},
                                          PP.RiskLimits(lim.pop("instrument_allowlist"), **lim))
        return self._engine

    def page(self, path, title, body, status=200):
        nav = "".join('<a href="%s"%s>%s</a>' % (h, ' class="on"' if h == path else "", esc(t))
                      for h, t in NAV)
        doc = ('<!DOCTYPE html><html lang="fa" dir="rtl"><head><meta charset="utf-8">'
               '<meta name="viewport" content="width=device-width,initial-scale=1">'
               '<title>%s - marfin-llm</title><style>%s</style></head><body>'
               '<header><b>marfin-llm</b><nav>%s</nav></header><main><h2>%s</h2>%s'
               '<p class="note">این خروجی تحلیلی است، نه توصیهٔ مالی شخصی. معاملهٔ واقعی در این برنامه غیرفعال است.</p>'
               '</main></body></html>') % (esc(title), CSS, nav, esc(title), body)
        return Response(status, doc, headers={"Content-Security-Policy":
                                              "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'",
                                              "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"})

    def hidden(self):
        return '<input type="hidden" name="csrf" value="%s">' % esc(self.csrf)

    def handle(self, method, path, query=None, form=None, host="127.0.0.1"):
        query, form = query or {}, form or {}
        hostname = (host or "").rsplit(":", 1)[0] if not (host or "").startswith("[") else (host or "").split("]")[0] + "]"
        if hostname not in LOOPBACK_HOSTS:
            return Response(403, "refused: this UI only answers on loopback (Host %s)" % esc(host),
                            "text/plain; charset=utf-8")
        if method == "POST" and not secrets.compare_digest(str(form.get("csrf", "")), self.csrf):
            return Response(403, "refused: missing or wrong form token (CSRF). Reload the page.",
                            "text/plain; charset=utf-8")
        if method not in ("GET", "POST"):
            return Response(405, "method not allowed", "text/plain; charset=utf-8")
        routes = {"/": self.p_home, "/ask": self.p_ask, "/calc": self.p_calc, "/macro": self.p_macro,
                  "/paper": self.p_paper, "/audit": self.p_audit, "/maintenance": self.p_maintenance,
                  "/providers": self.p_providers, "/phase11": self.p_phase11}
        fn = routes.get(path)
        if fn is None:
            return self.page(path, "یافت نشد", '<p>این صفحه وجود ندارد.</p>', 404)
        try:
            return fn(method, query, form)
        except Exception as exc:                   # noqa: BLE001 -- shown, not swallowed
            return self.page(path, "خطای داخلی", '<div class="err">INTERNAL ERROR (%s): %s<br>'
                             'این یک باگ در برنامه است، نه امتناع.</div>' % (esc(type(exc).__name__), esc(exc)), 500)

    # -- pages -----------------------------------------------------------------
    def p_home(self, method, q, f):
        mf = M.manifest()
        rows = [("حالت اجرا (execution mode)", '<code>%s</code> (منبع: %s)' % (esc(mf["mode"]), esc(mf["source"]))),
                ("معاملهٔ واقعی", '<span class="bad">غیرفعال</span> (%d از %d پیش‌نیاز برآورده نشده)'
                 % (len(mf["unmet_live_prerequisites"]), mf["n_live_prerequisites"])),
                ("مدل", esc(self.model_label) if self.assistant else
                 '<span class="due">بارگذاری نشده</span>: صفحهٔ «پرسش» به مدل نیاز دارد. با <code>--model</code> یا <code>--server</code> اجرا کنید.'),
                ("ماشین‌حساب‌ها", "%d ابزار قطعی" % len(REG.tool_names())),
                ("سری‌های کلان", "%d سری (FRED و BIS)" % len(MACRO.SERIES)),
                ("کلید FRED", '<span class="ok">تنظیم شده</span>' if os.environ.get("FRED_API_KEY")
                 else '<span class="due">تنظیم نشده</span>: سری‌های FRED کار نمی‌کنند؛ BIS کار می‌کند')]
        body = '<div class="card"><table>%s</table></div>' % "".join(
            "<tr><th>%s</th><td>%s</td></tr>" % (esc(a), b) for a, b in rows)
        body += ('<div class="card"><b>از کجا شروع کنم؟</b><ul>'
                 '<li><a href="/ask">پرسش</a>: سؤال مالی به فارسی یا انگلیسی. برنامه خودش مسیر را انتخاب می‌کند: محاسبه، داده‌های کلان، اسناد یا پاسخ ساده.</li>'
                 '<li><a href="/calc">ماشین‌حساب‌ها</a>: محاسبهٔ دقیق بدون مدل (P/E، CAGR، اندازهٔ پوزیشن، اوراق، اختیار معامله، ...).</li>'
                 '<li><a href="/macro">داده‌های کلان</a>: تورم، بیکاری، نرخ بهره و نرخ بانک‌های مرکزی، مستقیم از منبع.</li>'
                 '<li><a href="/paper">معاملهٔ کاغذی</a>: تمرین سفارش با پول مجازی، با همهٔ کنترل‌های ریسک.</li></ul></div>')
        return self.page("/", "داشبورد", body)

    def p_ask(self, method, q, f):
        body = ""
        if self.assistant is None:
            body += ('<div class="warn">مدل بارگذاری نشده است. سرور را این‌طور اجرا کنید:<pre>python scripts\\ui.py '
                     '--model C:\\models\\Qwen3.5-4B-Q4_K_M.gguf</pre>بقیهٔ صفحه‌ها بدون مدل کار می‌کنند.</div>')
        if method == "POST":
            question = (f.get("question") or "").strip()
            if not question:
                body += '<div class="err">سؤال خالی است.</div>'
            elif self.assistant is None:
                body += '<div class="err">بدون مدل نمی‌توان پاسخ داد.</div>'
            else:
                self.history.append(self.assistant.answer(question))
        body += ('<form method="post" class="card">%s<textarea name="question" rows="3" dir="auto" '
                 'placeholder="مثلاً: نرخ تورم آمریکا در ژانویه ۲۰۲۴ چقدر بود؟"></textarea><br>'
                 '<button>بپرس</button> <span class="note">روی i5-12400 هر پاسخ حدود ۳۰ تا ۹۰ ثانیه طول می‌کشد (MEASURED در بنچمارک).</span></form>'
                 % self.hidden())
        for out in reversed(self.history):
            body += ASK.turn_html(out)
        return self.page("/ask", "پرسش", body)

    def p_calc(self, method, q, f):
        schemas = {s["function"]["name"]: s for s in REG.tool_schemas()}
        name = (f.get("tool") if method == "POST" else q.get("tool")) or ""
        if name not in schemas:
            body = '<div class="card"><p>%d ماشین‌حساب قطعی. هیچ‌کدام به مدل یا اینترنت نیاز ندارند. یکی را انتخاب کنید:</p><div class="grid">%s</div></div>' % (
                len(schemas), "".join('<a href="/calc?tool=%s" title="%s">%s</a>' % (
                    esc(urllib.parse.quote(n)), esc(schemas[n]["function"]["description"]), esc(n))
                    for n in sorted(schemas)))
            if name:
                body = '<div class="err">ابزار ناشناخته: <code>%s</code></div>' % esc(name) + body
            return self.page("/calc", "ماشین‌حساب‌ها", body)
        sch = schemas[name]
        fn = sch["function"]
        req = set(fn["parameters"]["required"])
        result = ""
        if method == "POST":
            try:
                args = form_to_arguments(sch, f)
                r = REG.call_tool(name, args)
            except ValueError as exc:
                r = {"ok": False, "error": "invalid_argument", "message": str(exc)}
            if r["ok"]:
                result = ('<div class="card"><b>نتیجه (COMPUTED):</b> <code>%s</code> %s<br>'
                          '<span class="note">فرمول:</span> <code>%s</code><br><span class="note">ورودی‌ها:</span> <code>%s</code>%s</div>'
                          % (esc(r["value"]), esc(r.get("units") or ""), esc(r.get("formula")),
                             esc(json.dumps(r.get("inputs"), ensure_ascii=False, default=str)),
                             ("<br><span class=\"note\">%s</span>" % esc(r["notes"])) if r.get("notes") else ""))
            else:
                result = '<div class="err">امتناع: <code>%s</code> %s</div>' % (esc(r["error"]), esc(r.get("message")))
        rows = []
        for p, spec in fn["parameters"]["properties"].items():
            t = spec.get("type")
            val = esc(f.get(p, "")) if method == "POST" else ""
            if "enum" in spec:
                ctl = '<select name="%s"><option value=""></option>%s</select>' % (esc(p), "".join(
                    '<option%s>%s</option>' % (" selected" if f.get(p) == o else "", esc(o)) for o in spec["enum"]))
            elif t == "boolean":
                ctl = '<select name="%s"><option value=""></option><option>true</option><option>false</option></select>' % esc(p)
            else:
                ctl = '<input name="%s" value="%s" dir="ltr" size="40"%s>' % (
                    esc(p), val, ' placeholder="اعداد را با کاما جدا کنید"' if t == "array" else "")
            rows.append("<tr><th class=\"ltr\">%s%s</th><td>%s <span class=\"note\">%s</span></td></tr>"
                        % (esc(p), " *" if p in req else "", ctl, esc(t)))
        body = ('<p><a href="/calc">&larr; همهٔ ماشین‌حساب‌ها</a></p><div class="card"><h3 class="ltr">%s</h3>'
                '<p class="ltr">%s</p><form method="post">%s<input type="hidden" name="tool" value="%s">'
                '<table>%s</table><p class="note">* الزامی. ارقام فارسی هم پذیرفته می‌شوند (۸٫۴۰).</p>'
                '<button>محاسبه</button></form></div>%s') % (
            esc(name), esc(fn["description"]), self.hidden(), esc(name), "".join(rows), result)
        return self.page("/calc", "ماشین‌حساب: " + name, body)

    def p_macro(self, method, q, f):
        result = ""
        if method == "POST":
            series = f.get("series") or ""
            try:
                if series not in MACRO.SERIES:
                    raise MACRO.MacroError("series %r is not in the catalogue" % series)
                d = self.macro_fetch(series, start_date=(f.get("start") or None),
                                     end_date=(f.get("end") or None), limit=int(f.get("limit") or 13))
                result = ('<div class="card"><b class="ltr">%s</b> (%s، %s، %s) <span class="note">RETRIEVED</span>'
                          '<table><tr><th>تاریخ</th><th>مقدار</th></tr>%s</table>%s</div>') % (
                    esc(series), esc(d["source"]), esc(d["unit"]), esc(d["frequency"]),
                    "".join("<tr><td class=\"ltr\">%s</td><td class=\"ltr\">%s</td></tr>" % (esc(o["date"]), esc(o["value"]))
                            for o in d["observations"]),
                    "".join('<p class="note ltr">%s</p>' % esc(n) for n in d.get("notices") or ()))
            except Exception as exc:                # noqa: BLE001 -- a refusal is shown verbatim
                result = '<div class="err">دریافت نشد (هیچ عددی جایگزین نمی‌شود): <code>%s</code></div>' % esc(exc)
        opts = "".join('<option value="%s">%s (%s)</option>' % (esc(k), esc(v.get("title_fa") or v["title"]), esc(k))
                       for k, v in MACRO.SERIES.items())
        body = ('<form method="post" class="card">%s<label>سری</label><select name="series">%s</select><br>'
                '<label>از تاریخ (اختیاری)</label><input name="start" dir="ltr" placeholder="2024-01-01"><br>'
                '<label>تا تاریخ (اختیاری)</label><input name="end" dir="ltr" placeholder="2024-12-31"><br>'
                '<label>حداکثر تعداد</label><input name="limit" value="13" dir="ltr" size="5"><br>'
                '<button>دریافت</button> <span class="note">سری‌های FRED به متغیر محیطی FRED_API_KEY نیاز دارند.</span></form>%s'
                ) % (self.hidden(), opts, result)
        return self.page("/macro", "داده‌های کلان", body)

    def _quote(self, f):
        return PP.QuoteSnapshot(f.get("instrument", ""), num(f, "bid"), num(f, "ask"), num(f, "last"),
                                self.clock(), f.get("market_status") or "OPEN", "USER_SUPPLIED (typed in the UI)")

    def p_paper(self, method, q, f):
        eng = self.engine()
        msg = ""
        action = f.get("action") if method == "POST" else None
        try:
            if action == "preview":
                pv = eng.preview(PAPER_ACCOUNT, "PAPER", f.get("instrument", ""), f.get("side"), num(f, "quantity"),
                                 f.get("order_type"), f.get("client_order_id") or ("ui-" + secrets.token_hex(4)),
                                 self._quote(f), limit_price=(num(f, "limit_price") if (f.get("limit_price") or "").strip() else None),
                                 now=self.clock())
                rows = "".join('<tr><td class="ltr">%s</td><td class="%s">%s</td><td class="ltr">%s</td></tr>' % (
                    esc(k), "ok" if v["status"] == "PASS" else "bad", esc(v["status"]), esc(v["detail"]))
                    for k, v in pv["risk_checks"].items())
                msg = ('<div class="card"><div class="banner">%s</div><b>نتیجهٔ بررسی ریسک: <span class="%s">%s</span></b>'
                       ' &middot; مبلغ تخمینی %s &middot; انقضا %s<table>%s</table>') % (
                    esc(pv["banner"]), "ok" if pv["verdict"] == "PASS" else "bad", esc(pv["verdict"]),
                    esc(pv["estimated_notional"]), esc(pv["preview_expiry"]), rows)
                if pv["verdict"] == "PASS":
                    keep = "".join('<input type="hidden" name="%s" value="%s">' % (esc(k), esc(f.get(k, "")))
                                   for k in ("instrument", "bid", "ask", "last", "market_status"))
                    msg += ('<form method="post">%s%s<input type="hidden" name="action" value="commit">'
                            '<input type="hidden" name="preview_id" value="%s"><input type="hidden" name="token" value="%s">'
                            '<p>برای ثبت، عبارت <code>%s</code> را تایپ کنید:</p><input name="phrase" dir="ltr"> '
                            '<button class="danger">ثبت سفارش کاغذی</button></form>') % (
                        self.hidden(), keep, esc(pv["preview_id"]), esc(pv["confirmation_token"]), esc(COMMIT_PHRASE))
                msg += "</div>"
            elif action == "commit":
                if (f.get("phrase") or "").strip() != COMMIT_PHRASE:
                    raise PP.PaperError("confirmation phrase not typed; nothing was submitted")
                o = eng.commit(f.get("preview_id"), f.get("token"), "ui-" + (f.get("preview_id") or ""), "HUMAN",
                               self._quote(f), now=self.clock())
                msg = '<div class="card"><span class="ok">ثبت شد</span> (کاغذی): <code>%s</code> وضعیت <code>%s</code></div>' % (
                    esc(o["order_id"]), esc(o["state"]))
            elif action == "cancel":
                o = eng.cancel(f.get("order_id"), "HUMAN", now=self.clock())
                msg = '<div class="card">لغو: <code>%s</code> &rarr; <code>%s</code></div>' % (esc(o["order_id"]), esc(o["state"]))
            elif action == "reconcile":
                r = eng.reconcile(now=self.clock())
                msg = '<div class="card">تطبیق: <span class="%s">%s</span> %s</div>' % (
                    "ok" if r["ok"] else "bad", "OK" if r["ok"] else "MISMATCH", esc("; ".join(r["problems"])))
            elif action == "kill_on":
                eng.kill.engage("HUMAN", f.get("reason") or "engaged from the UI", self.clock())
                msg = '<div class="card bad">کلید توقف اضطراری فعال شد.</div>'
            elif action == "kill_off":
                eng.kill.disengage("HUMAN", f.get("phrase") or "", f.get("reason") or "", self.clock())
                msg = '<div class="card ok">کلید توقف اضطراری غیرفعال شد.</div>'
            elif action is not None:
                raise PP.PaperError("unknown action %r" % action)
        except (PP.PaperError, M.ExecutionModeError) as exc:
            msg = '<div class="err">امتناع: %s</div>' % esc(exc)
        enabled = M.is_permitted("submit_paper_order")
        lim = eng.limits
        body = '<div class="banner">PAPER TRADING: بازار شبیه‌سازی‌شده، بدون پول واقعی</div>' + msg
        if not enabled:
            body += ('<div class="warn">ثبت سفارش کاغذی خاموش است (حالت فعلی: <code>%s</code>). پیش‌نمایش کار می‌کند. '
                     'برای روشن کردن، این دو خط را در فایل <code>%s</code> بنویسید:<pre>mode = PAPER_TRADING\n'
                     'i_have_enabled_paper_trading = yes</pre>این برنامه خودش این فایل را نمی‌نویسد.</div>') % (
                esc(M.current_mode()), esc(M.CONFIG_PATH))
        body += ('<form method="post" class="card">%s<input type="hidden" name="action" value="preview"><b>سفارش جدید</b><br>'
                 '<label>نماد</label><select name="instrument">%s</select><br>'
                 '<label>سمت</label><select name="side">%s</select><br>'
                 '<label>تعداد</label><input name="quantity" dir="ltr" size="8"><br>'
                 '<label>نوع</label><select name="order_type"><option>market</option><option>limit</option></select> '
                 '<input name="limit_price" dir="ltr" size="8" placeholder="قیمت limit"><br>'
                 '<p class="note">قیمت لحظه‌ای را خودتان از کارگزار یا سایت معتبر وارد کنید. این برنامه دادهٔ لحظه‌ای مجاز ندارد '
                 '(Alpha Vantage رایگان فقط END_OF_DAY است) و این قیمت با برچسب USER_SUPPLIED ثبت می‌شود.</p>'
                 '<label>bid</label><input name="bid" dir="ltr" size="8"> <label>ask</label><input name="ask" dir="ltr" size="8"> '
                 '<label>last</label><input name="last" dir="ltr" size="8"><br>'
                 '<label>وضعیت بازار</label><select name="market_status"><option>OPEN</option><option>CLOSED</option></select><br>'
                 '<button>پیش‌نمایش و بررسی ریسک</button></form>') % (
            self.hidden(), "".join("<option>%s</option>" % esc(i) for i in lim.instrument_allowlist),
            "".join("<option>%s</option>" % esc(s) for s in PP.SIDES))
        pos = eng.positions(PAPER_ACCOUNT)
        body += '<div class="card"><b>حساب %s</b>: نقد <code>%.2f</code> &middot; پوزیشن‌ها <code>%s</code>' % (
            esc(PAPER_ACCOUNT), eng.cash[PAPER_ACCOUNT], esc(json.dumps(pos)))
        if eng.orders:
            body += "<table><tr><th>سفارش</th><th>نماد</th><th>سمت</th><th>تعداد</th><th>پرشده</th><th>وضعیت</th><th></th></tr>"
            for o in eng.orders.values():
                cancel = ('<form method="post">%s<input type="hidden" name="action" value="cancel"><input type="hidden" '
                          'name="order_id" value="%s"><button>لغو</button></form>' % (self.hidden(), esc(o["order_id"]))
                          if o["state"] in ("ACKNOWLEDGED", "PARTIALLY_FILLED") else "")
                body += "<tr>%s<td>%s</td></tr>" % ("".join('<td class="ltr">%s</td>' % esc(o.get(k)) for k in (
                    "order_id", "instrument_id", "side", "quantity", "filled_qty", "state")), cancel)
            body += "</table>"
        body += ('<form method="post">%s<input type="hidden" name="action" value="reconcile"><button>تطبیق با بازار شبیه‌سازی‌شده</button></form></div>'
                 % self.hidden())
        engaged = eng.kill.engaged()
        body += '<div class="card"><b>کلید توقف اضطراری:</b> %s' % (
            '<span class="bad">فعال: هیچ سفارشی پذیرفته نمی‌شود</span>' if engaged else '<span class="ok">خاموش</span>')
        if engaged:
            body += ('<form method="post">%s<input type="hidden" name="action" value="kill_off"><p>برای غیرفعال کردن، این عبارت را دقیقاً تایپ کنید: '
                     '<code>%s</code></p><input name="phrase" dir="ltr" size="50"><br><label>دلیل</label><input name="reason"> '
                     '<button>غیرفعال کن</button></form>') % (self.hidden(), esc(PP.KillSwitch.PHRASE))
        else:
            body += ('<form method="post">%s<input type="hidden" name="action" value="kill_on"><label>دلیل</label><input name="reason"> '
                     '<button class="danger">توقف اضطراری</button></form>') % self.hidden()
        body += "</div>"
        body += '<div class="card"><b>سقف‌های ریسک</b> (configs/risk-policy.json، تأییدشده توسط مالک)<pre>%s</pre></div>' % esc(
            json.dumps({k: getattr(lim, k) for k in ("max_order_notional", "max_daily_notional", "max_position_qty",
                                                     "max_daily_loss", "max_orders_per_minute", "allow_short")}, indent=1))
        return self.page("/paper", "معاملهٔ کاغذی", body)

    def _audit_block(self, title, path):
        if not os.path.exists(path):
            return '<div class="card"><b>%s</b>: هنوز رکوردی ثبت نشده <code>%s</code></div>' % (esc(title), esc(path))
        log = PP.AuditLog.__new__(PP.AuditLog)
        log.path = path
        ok, n, problem = PP.AuditLog.verify(log)
        recs = PP.AuditLog.records(log)[-30:] if ok else []
        rows = "".join('<tr><td>%s</td><td class="ltr">%s</td><td class="ltr">%s</td><td dir="auto">%s</td></tr>' % (
            esc(r.get("seq")), esc(r.get("at")), esc(r.get("event")),
            esc(json.dumps({k: v for k, v in r.items() if k not in ("seq", "at", "event", "prev", "hash")},
                           ensure_ascii=False)[:400])) for r in reversed(recs))
        return ('<div class="card"><b>%s</b> <code>%s</code><br>زنجیرهٔ هش: %s (%d رکورد)%s'
                '<table><tr><th>#</th><th>زمان</th><th>رویداد</th><th>جزئیات</th></tr>%s</table></div>') % (
            esc(title), esc(path), '<span class="ok">سالم</span>' if ok else '<span class="bad">شکسته</span>', n,
            (' <span class="bad">%s</span>' % esc(problem)) if problem else "", rows)

    def p_audit(self, method, q, f):
        body = self._audit_block("پرسش‌ها (ask)", self.ask_audit_path)
        body += self._audit_block("معاملهٔ کاغذی", os.path.join(self.paper_dir, "audit.jsonl"))
        return self.page("/audit", "گزارش ممیزی", body)

    def p_maintenance(self, method, q, f):
        if self._maintain is None:
            import maintain as MT
            self._maintain = MT.run_checks
        rep = self._maintain()
        cls = {"OK": "ok", "DUE": "due", "FAIL": "bad"}[rep["status"]]
        rows = "".join('<tr><td class="%s">%s</td><td class="ltr">%s</td><td class="ltr">%s</td><td class="ltr">%s</td></tr>' % (
            {"INFO": "ok", "WARN": "due", "CRITICAL": "bad"}[x["severity"]], esc(x["severity"]), esc(x["check"]),
            esc(x["subject"]), esc(x["message"])) for x in rep["findings"])
        body = ('<div class="card">وضعیت: <span class="%s">%s</span> <code>%s</code><table><tr><th>سطح</th><th>بررسی</th>'
                '<th>موضوع</th><th>پیام</th></tr>%s</table></div>') % (cls, esc(rep["status"]), esc(rep["counts"]), rows)
        return self.page("/maintenance", "نگهداری (فاز ۱۰)", body)

    def p_providers(self, method, q, f):
        from llm.providers import credential_status
        rows = "".join('<tr><td class="ltr">%s</td><td>%s</td><td class="ltr">%s</td><td>%s</td></tr>' % (
            esc(r["provider"]), esc(r["label"]), esc(r["env_key"] or "-"),
            '<span class="ok">آماده</span>' if r["configured"] else '<span class="due">کلید ندارد</span>')
            for r in credential_status())
        body = ('<div class="card"><p>فقط وجود کلید نشان داده می‌شود، هرگز خود کلید. صفحهٔ «پرسش» فقط مدل محلی را به کار می‌برد.</p>'
                '<table><tr><th>ارائه‌دهنده</th><th>نام</th><th>متغیر محیطی</th><th>وضعیت</th></tr>%s</table></div>') % rows
        return self.page("/providers", "ارائه‌دهنده‌ها", body)

    def p_phase11(self, method, q, f):
        r = self._readiness()
        rows = "".join('<tr><td class="%s">%s</td><td>%s</td><td class="ltr">%s</td></tr>' % (
            "ok" if p["met"] else "bad", "✔" if p["met"] else "✘", esc(p["name"]), esc(p["evidence"]))
            for p in r["prerequisites"])
        dl = "".join('<tr><td class="ltr">%s</td><td class="ltr">%s</td></tr>' % (esc(k), esc(v))
                     for k, v in r["deliverables"].items())
        steps = "".join('<tr><td class="%s">%s</td><td class="ltr">%s</td><td class="ltr">%s</td></tr>' % (
            "ok" if s["ok"] else "bad", "✔" if s["ok"] else "✘", esc(s["step"]), esc(s["detail"]))
            for s in r["drill"]["steps"])
        body = ('<div class="card">نتیجه: <span class="%s">%s</span> &middot; %d از %d پیش‌نیاز فاز ۱۱ برآورده شده &middot; '
                '%d از %d پیش‌نیاز SS.6.1 برآورده نشده &middot; live_trading_enabled = <code>%s</code>'
                '<p class="note">این صفحه فقط گزارش می‌دهد. هیچ دکمه‌ای برای فعال کردن معاملهٔ واقعی وجود ندارد.</p></div>'
                '<div class="card"><b>پیش‌نیازها (SYSTEM_PROMPT §24)</b><table>%s</table></div>'
                '<div class="card"><b>تحویل‌دادنی‌ها</b><table>%s</table></div>'
                '<div class="card"><b>تمرین کلید توقف اضطراری</b> (%s)<table>%s</table></div>') % (
            "ok" if r["ready"] else "bad", esc(r["verdict"]), r["n_met"], r["n_total"], len(r["ss61_unmet"]),
            r["ss61_total"], esc(r["live_trading_enabled"]), rows, dl, esc(r["drill"]["label"]), steps)
        return self.page("/phase11", "فاز ۱۱: آمادگی معاملهٔ واقعی", body)


def make_handler(app):
    from http.server import BaseHTTPRequestHandler

    class H(BaseHTTPRequestHandler):
        server_version = "marfin-ui"

        def _go(self, method):
            u = urllib.parse.urlsplit(self.path)
            query = {k: v[-1] for k, v in urllib.parse.parse_qs(u.query).items()}
            form = {}
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                if n > MAX_BODY:
                    return self._send(Response(413, "request too large", "text/plain; charset=utf-8"))
                raw = self.rfile.read(n).decode("utf-8", "replace")
                form = {k: v[-1] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}
            self._send(app.handle(method, u.path, query, form, self.headers.get("Host", "")))

        def _send(self, r):
            data = r.body.encode("utf-8")
            self.send_response(r.status)
            self.send_header("Content-Type", r.ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for k, v in r.headers.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._go("GET")

        def do_POST(self):
            self._go("POST")

        def log_message(self, fmt, *args):            # quiet: no query strings in the console
            sys.stderr.write("%s %s\n" % (self.command, urllib.parse.urlsplit(self.path).path))

    return H


def refuse_args(a):
    """Why these arguments are refused, or None. Pure, so every refusal is testable without serving."""
    if a.host != HOST:
        return ("the UI binds 127.0.0.1 only (it can preview and commit paper orders); --host %s refused."
                % a.host)
    if a.model and a.server:
        return "give --model OR --server, not both."
    if a.model and not os.path.isfile(a.model):
        return "model file not found: %s" % a.model
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="marfin-llm local web UI (loopback only).")
    ap.add_argument("--model", help="GGUF file (in-process llama.cpp); without it, 'ask' is unavailable")
    ap.add_argument("--server", choices=("ollama", "lmstudio"))
    ap.add_argument("--model-id")
    ap.add_argument("--server-url")
    ap.add_argument("--ctx", type=int, default=16384)
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--max-tokens", type=int, default=ASK.RP.DEFAULT_MAX_TOKENS)
    ap.add_argument("--corpus", default=ASK.DEFAULT_CORPUS)
    ap.add_argument("--no-macro", action="store_true")
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args(argv)
    why = refuse_args(a)
    if why:
        print("ERROR: " + why)
        return 2
    ASK.RP.assert_no_execution_capability()
    assistant, label = None, None
    if a.model or a.server:
        if a.server:
            from llm.local_server import ServerRunner, ServerError
            try:
                runner = ServerRunner(a.server, a.model_id, base_url=a.server_url, max_tokens=a.max_tokens,
                                      num_ctx=a.ctx, num_thread=a.threads)
            except ServerError as exc:
                print("ERROR: %s" % exc)
                return 2
            label = "%s: %s" % (a.server, a.model_id)
        else:
            try:
                from llama_cpp import Llama
            except ImportError:
                print("ERROR: llama-cpp-python is not installed (pip install llama-cpp-python).")
                return 2
            print("loading %s ..." % os.path.basename(a.model))
            runner = ASK.RP.ModelRunner(Llama(model_path=a.model, n_ctx=a.ctx, n_threads=a.threads, verbose=False),
                                        max_tokens=a.max_tokens)
            label = os.path.basename(a.model)
        assistant = ASK.Assistant(runner, index=ASK.build_index_from(a.corpus), audit=ASK.open_audit(ASK.DEFAULT_AUDIT),
                                  use_macro=not a.no_macro)
    app = App(assistant=assistant, model_label=label)
    from http.server import ThreadingHTTPServer
    srv = ThreadingHTTPServer((HOST, a.port), make_handler(app))
    url = "http://%s:%d/" % (HOST, a.port)
    print("marfin-llm UI: %s   (Ctrl+C to stop)" % url)
    if not a.no_open:
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception:                               # noqa: BLE001 -- display only
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                            # noqa: BLE001
        print("INTERNAL ERROR (%s): %s -- a bug in ui.py, not a refusal." % (type(exc).__name__, exc))
        sys.exit(3)
