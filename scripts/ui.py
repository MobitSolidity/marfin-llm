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
import re
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
from rag import datahub as DH                                  # noqa: E402
from tools import catalog_fa as CAT                            # noqa: E402
from llm import settings as PS                                 # noqa: E402
from llm import providers as LP                                # noqa: E402
from llm import clients as LC                                  # noqa: E402

HOST = "127.0.0.1"
PORT = 8765
MAX_BODY = 64 * 1024
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "[::1]")
PAPER_DIR = os.path.join(os.path.expanduser("~"), ".marfin", "paper")
PAPER_ACCOUNT = "PAPER-0001"
PAPER_CASH = 100000.0
#: Typed by the human on the commit form. Distinct from the kill-switch phrase on purpose.
COMMIT_PHRASE = "CONFIRM"

NAV = (("/", "داشبورد"), ("/markets", "بازارها و داده‌ها"), ("/calc", "فرمول‌ها و ماشین‌حساب‌ها"),
       ("/ask", "پرسش از مدل"), ("/macro", "سری‌های کلان"), ("/paper", "معاملهٔ کاغذی"),
       ("/audit", "گزارش ممیزی"), ("/maintenance", "نگهداری"), ("/providers", "ارائه‌دهنده‌ها"),
       ("/phase11", "فاز ۱۱ (معلق)"))

#: D-0141: the look lives in two static files, served from a fixed whitelist (never a path
#: taken from the request), so the Content-Security-Policy can forbid inline styles and
#: inline scripts entirely.
ASSET_DIR = os.path.join(_HERE, "ui_assets")
BRAND_DIR = os.path.join(_ROOT, "assets", "brand")
STATIC = {"/static/app.css": ("app.css", "text/css; charset=utf-8"),
          "/static/app.js": ("app.js", "text/javascript; charset=utf-8"),
          # D-0142: the logo has ONE source (assets/brand/), shared with the README.
          "/static/logo.svg": (os.path.join(BRAND_DIR, "logo.svg"), "image/svg+xml; charset=utf-8"),
          "/static/favicon.svg": (os.path.join(BRAND_DIR, "favicon.svg"), "image/svg+xml; charset=utf-8")}
CSP = ("default-src 'none'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
       "form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
try:
    VERSION = open(os.path.join(_ROOT, "VERSION"), encoding="utf-8").read().strip()
except OSError:                                     # pragma: no cover -- display only
    VERSION = "?"


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


def fmtn(v, nd=None):
    """A number for display: grouped thousands, sensible decimals. None -> a dash."""
    if v is None:
        return "\u2014"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    a = abs(v)
    if nd is None:
        nd = 0 if a >= 1e6 else (2 if a >= 10 else 4)
    return "{:,.{nd}f}".format(v, nd=nd)


def svg_line(points, w=640, h=180, pad=30, label=""):
    """
    A line chart as inline SVG built from attributes only (no style attribute, so the
    Content-Security-Policy can forbid inline styles). Every text node is escaped.
    points: [(x label, value)], oldest first.
    """
    pts = [(str(x), float(y)) for x, y in points if y is not None]
    if len(pts) < 2:
        return '<p class="muted">برای نمودار دست‌کم دو نقطه لازم است.</p>'
    ys = [y for _, y in pts]
    lo, hi = min(ys), max(ys)
    if hi == lo:
        lo, hi = lo - 1.0, hi + 1.0
    n = len(pts)

    def X(i):
        return pad + (w - 2 * pad) * i / float(n - 1)

    def Y(y):
        return h - pad - (h - 2 * pad) * (y - lo) / (hi - lo)
    line = " ".join("%.1f,%.1f" % (X(i), Y(y)) for i, (_, y) in enumerate(pts))
    area = "M%.1f,%.1f L%s L%.1f,%.1f Z" % (X(0), h - pad, line.replace(" ", " L"), X(n - 1), h - pad)
    grid = "".join('<line class="grid" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/><text class="ax" x="2" y="%.1f">%s</text>'
                   % (pad, Y(v), w - pad, Y(v), Y(v) - 3, esc(fmtn(v))) for v in (lo, (lo + hi) / 2.0, hi))
    dots = "" if n > 160 else "".join(
        '<circle class="pt" cx="%.1f" cy="%.1f" r="5"><title>%s: %s</title></circle>'
        % (X(i), Y(y), esc(x), esc(fmtn(y))) for i, (x, y) in enumerate(pts))
    xl = ('<text class="ax" x="%d" y="%d">%s</text><text class="ax" x="%d" y="%d" text-anchor="end">%s</text>'
          % (pad, h - 8, esc(pts[0][0]), w - pad, h - 8, esc(pts[-1][0])))
    return ('<svg class="chart%s" viewBox="0 0 %d %d" role="img" aria-label="%s">%s<path class="area" d="%s"/>'
            '<polyline class="line" points="%s"/>%s%s</svg>') % (
        " down" if ys[-1] < ys[0] else "", w, h, esc(label), grid, area, line, dots, xl)


def svg_multi(series, w=680, h=240, pad=34):
    """Several lines on one x axis (years). series: [(name, [(x, value)])]. Returns (svg, legend)."""
    xs = sorted({x for _, pts in series for x, _ in pts})
    ys = [y for _, pts in series for _, y in pts if y is not None]
    if len(xs) < 2 or not ys:
        return '<p class="muted">داده برای نمودار کافی نیست.</p>', ""
    lo, hi = min(ys), max(ys)
    if hi == lo:
        lo, hi = lo - 1.0, hi + 1.0
    pos = {x: i for i, x in enumerate(xs)}

    def X(x):
        return pad + (w - 2 * pad) * pos[x] / float(len(xs) - 1)

    def Y(y):
        return h - pad - (h - 2 * pad) * (y - lo) / (hi - lo)
    out = ["".join('<line class="grid" x1="%d" y1="%.1f" x2="%d" y2="%.1f"/><text class="ax" x="2" y="%.1f">%s</text>'
                   % (pad, Y(v), w - pad, Y(v), Y(v) - 3, esc(fmtn(v))) for v in (lo, (lo + hi) / 2.0, hi))]
    legend = []
    for i, (name, pts) in enumerate(series):
        p = [(x, y) for x, y in sorted(pts) if y is not None]
        cls = "s%d" % (i % 8)
        if len(p) >= 2:
            out.append('<polyline class="m %s" points="%s"/>' % (cls, " ".join("%.1f,%.1f" % (X(x), Y(y)) for x, y in p)))
        out.extend('<circle class="pt" cx="%.1f" cy="%.1f" r="5"><title>%s %s: %s</title></circle>'
                   % (X(x), Y(y), esc(name), esc(x), esc(fmtn(y))) for x, y in p)
        legend.append('<span><i class="%s"></i>%s</span>' % (cls, esc(name)))
    out.append('<text class="ax" x="%d" y="%d">%s</text><text class="ax" x="%d" y="%d" text-anchor="end">%s</text>'
               % (pad, h - 8, esc(xs[0]), w - pad, h - 8, esc(xs[-1])))
    return ('<svg class="chart" viewBox="0 0 %d %d" role="img">%s</svg>' % (w, h, "".join(out)),
            '<div class="legend">%s</div>' % "".join(legend))


def svg_bar(value, vmax):
    """A horizontal bar, width as an SVG attribute (never a style)."""
    width = 0.0 if not vmax else max(0.0, min(100.0, abs(value) / float(vmax) * 100.0))
    return ('<svg class="bar" viewBox="0 0 100 10" preserveAspectRatio="none"><rect class="track" width="100" height="10" rx="5"/>'
            '<rect class="fill %s" width="%.1f" height="10" rx="5"/></svg>') % ("neg" if value < 0 else "pos", width)


def value_table(v):
    """A dict or list result (MACD, Bollinger, a coupon schedule) as an escaped table."""
    if isinstance(v, dict):
        return '<div class="tbl"><table>%s</table></div>' % "".join(
            '<tr><th class="ltr">%s</th><td class="num">%s</td></tr>' % (esc(k), esc(fmtn(x) if isinstance(x, (int, float)) else x))
            for k, x in v.items())
    if isinstance(v, list) and v and all(isinstance(r, dict) for r in v):
        cols = list(v[0])
        return '<div class="tbl"><table><tr>%s</tr>%s</table></div>' % (
            "".join('<th class="ltr">%s</th>' % esc(c) for c in cols),
            "".join("<tr>%s</tr>" % "".join('<td class="num">%s</td>' % esc(fmtn(r.get(c)) if isinstance(r.get(c), (int, float)) else r.get(c))
                                            for c in cols) for r in v))
    return "<code>%s</code>" % esc(v)


def notices_html(ns):
    return "".join('<p class="note ltr">%s</p>' % esc(n) for n in ns or ())


class App(object):
    """
    Pure request handling: handle(method, path, query, form, host) -> Response. The HTTP
    server is a thin shell around it, so every page and every refusal is testable without
    a socket.
    """

    def __init__(self, assistant=None, paper_dir=PAPER_DIR, ask_audit_path=ASK.DEFAULT_AUDIT,
                 macro_fetch=None, clock=_now, model_label=None, readiness=None, maintain=None, hub=None,
                 settings_path=PS.DEFAULT_PATH, remote_factory=None, lister=None):
        self.assistant = assistant
        # D-0142: provider settings (~/.marfin/providers.json; never a key). A bad file is
        # REPORTED on the providers page and the defaults (local engine) are used -- the
        # file itself is left untouched so nothing the owner entered is thrown away.
        self.settings_path = settings_path
        self.settings_error = None
        try:
            self.settings = PS.load(settings_path)
            PS.apply(self.settings)
        except (PS.SettingsError, LP.ProviderError) as exc:
            self.settings, self.settings_error = PS.defaults(), str(exc)
        self._remote_factory = remote_factory or (lambda app: app._build_remote())
        self._lister = lister or LC.list_models
        self._remote = None                     # (settings fingerprint, assistant, label)
        self._audit = None
        self.hub = hub or DH.DataHub()
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
    def audit(self):
        """
        ONE AuditLog for every engine. MEASURED 2026-10-28: two AuditLog objects on the same
        file break the hash chain ("line 2 does not chain to line 1"), so the online engine
        shares the local assistant's log instead of opening its own.
        """
        if self.assistant is not None and getattr(self.assistant, "audit", None) is not None:
            return self.assistant.audit
        if self._audit is None:
            self._audit = ASK.open_audit(self.ask_audit_path)
        return self._audit

    def remote_label(self):
        act = self.settings["active"]
        if not act.get("provider"):
            return None
        eff = PS.effective(self.settings, act["provider"])
        return "%s: %s" % (act["provider"], eff["model_id"] or "?")

    def _build_remote(self):
        """The online Assistant from the saved settings. Raises ProviderError/ValueError as refusals."""
        act = self.settings["active"]
        prov = act.get("provider")
        if not prov:
            raise LP.ProviderError("no online provider is selected; choose one on the providers page")
        eff = PS.effective(self.settings, prov)
        if not eff["model_id"]:
            raise LP.ProviderError("no model id for %s; enter one on the providers page" % prov)
        runner = ASK.RP.RemoteRunner(prov, eff["model_id"], max_tokens=ASK.RP.DEFAULT_MAX_TOKENS,
                                     base_url=eff["base_url"], allow_paid=bool(act.get("allow_paid")))
        local = self.assistant
        index = local.index if local is not None else ASK.build_index_from(ASK.DEFAULT_CORPUS)
        use_macro = local.use_macro if local is not None else True
        return (ASK.Assistant(runner, index=index, audit=self.audit(), use_macro=use_macro),
                "%s: %s" % (prov, eff["model_id"]))

    def remote_assistant(self):
        key = json.dumps([self.settings["active"], self.settings["overrides"], self.settings["custom"]],
                         sort_keys=True)
        if self._remote is None or self._remote[0] != key:
            bot, label = self._remote_factory(self)
            self._remote = (key, bot, label)
        return self._remote[1], self._remote[2]

    def engine(self):
        if self._engine is None:
            rp = json.load(open(LR.PAPER_POLICY, encoding="utf-8"))
            lim = dict(rp["limits"])
            self._engine = PP.PaperEngine(self.paper_dir, {PAPER_ACCOUNT: PAPER_CASH},
                                          PP.RiskLimits(lim.pop("instrument_allowlist"), **lim))
        return self._engine

    def page(self, path, title, body, status=200, subtitle=""):
        nav = "".join('<a href="%s"%s><span class="dot"></span>%s</a>' % (h, ' class="on"' if h == path else "", esc(t))
                      for h, t in NAV)
        doc = ('<!DOCTYPE html><html lang="fa" dir="rtl"><head><meta charset="utf-8">'
               '<meta name="viewport" content="width=device-width,initial-scale=1">'
               '<meta name="color-scheme" content="light dark">'
               '<title>%s - marfin-llm</title><link rel="icon" href="/static/favicon.svg" type="image/svg+xml">'
               '<link rel="stylesheet" href="/static/app.css">'
               '<script src="/static/app.js" defer></script></head><body><div class="shell">'
               '<aside class="side"><a class="brand" href="/"><img class="logo" src="/static/logo.svg" alt="" width="36" height="36"><span>marfin<b>llm</b></span></a>'
               '<nav class="nav">%s</nav><div class="side-foot">نسخهٔ %s &middot; فقط روی همین رایانه</div></aside>'
               '<div class="main"><header class="top"><details class="menu"><summary>منو</summary>'
               '<nav class="nav nav-m">%s</nav></details><div class="top-title"><h1>%s</h1>%s</div>'
               '<button class="theme" type="button" data-theme-toggle title="روشن / تیره">&#9680;</button></header>'
               '<main class="content">%s</main>'
               '<footer class="foot">این خروجی تحلیلی است، نه توصیهٔ مالی شخصی. معاملهٔ واقعی در این برنامه غیرفعال است '
               '(فاز ۱۱ معلق).</footer></div></div></body></html>') % (
            esc(title), nav, esc(VERSION), nav, esc(title),
            ('<p class="sub">%s</p>' % esc(subtitle)) if subtitle else "", body)
        return Response(status, doc, headers={"Content-Security-Policy": CSP,
                                              "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                                              "X-Content-Type-Options": "nosniff"})

    def static(self, path):
        name, ctype = STATIC[path]
        with open(name if os.path.isabs(name) else os.path.join(ASSET_DIR, name), encoding="utf-8") as fh:
            return Response(200, fh.read(), ctype, headers={"X-Content-Type-Options": "nosniff",
                                                            "Content-Security-Policy": CSP})

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
        if method == "GET" and path in STATIC:
            return self.static(path)
        routes = {"/": self.p_home, "/markets": self.p_markets, "/ask": self.p_ask, "/calc": self.p_calc,
                  "/macro": self.p_macro,
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
        unmet, total = len(mf["unmet_live_prerequisites"]), mf["n_live_prerequisites"]
        model = (esc(self.model_label) if self.assistant else
                 '<span class="due">بارگذاری نشده</span>')
        stats = [
            ("حالت اجرا", '<code>%s</code>' % esc(mf["mode"]), "از %s" % esc(mf["source"])),
            ("معاملهٔ واقعی", '<span class="bad">غیرفعال</span>', "فاز ۱۱ معلق (%d از %d پیش‌نیاز برآورده نشده)"
             % (unmet, total)),
            ("مدل زبانی", model, "صفحهٔ «پرسش» به مدل نیاز دارد" if not self.assistant else "محلی، بدون اینترنت"),
            ("فرمول‌ها", "%d" % len(REG.tool_names()), "%d دسته، هر کدام با آموزش کوتاه" % len(CAT.CATEGORIES)),
            ("منابع داده", "%d" % len(DH.SOURCES_FA), "ECB، BIS، FRED، بانک جهانی، Alpha Vantage، CoinGecko، SEC"),
            ("کلید FRED", '<span class="ok">تنظیم شده</span>' if os.environ.get("FRED_API_KEY")
             else '<span class="due">تنظیم نشده</span>', "اوراق، نفت، گاز و شاخص دلار به آن نیاز دارند"),
        ]
        body = '<div class="stats">%s</div>' % "".join(
            '<div class="stat"><div class="k">%s</div><div class="v">%s</div><div class="d">%s</div></div>' % (esc(k), v, d)
            for k, v, d in stats)
        if not self.assistant:
            body += ('<div class="warn">مدل بارگذاری نشده است. برای صفحهٔ «پرسش»، برنامه را با <code>--model</code> یا '
                     '<code>--server</code> اجرا کنید. بقیهٔ صفحه‌ها بدون مدل کار می‌کنند.</div>')
        tiles = (("/markets", "بازارها و داده‌ها", "نرخ ۲۹ ارز، نرخ بهرهٔ ۴۰ بانک مرکزی، اوراق و نفت آمریکا، شاخص‌های ۵۸ کشور"),
                 ("/calc", "فرمول‌ها و ماشین‌حساب‌ها", "۸۵ محاسبهٔ دقیق آفلاین با آموزش و مثال آماده"),
                 ("/ask", "پرسش از مدل", "سؤال به فارسی یا انگلیسی؛ اعداد با شواهد کنترل می‌شوند"),
                 ("/paper", "معاملهٔ کاغذی", "تمرین سفارش با پول مجازی و همهٔ کنترل‌های ریسک"),
                 ("/macro", "سری‌های کلان", "تورم، بیکاری و نرخ بهره با بازهٔ زمانی دلخواه"),
                 ("/audit", "گزارش ممیزی", "همهٔ پرسش‌ها و سفارش‌ها با زنجیرهٔ هش قابل بررسی"))
        body += '<div class="tiles">%s</div>' % "".join(
            '<a class="tile" href="%s"><b>%s</b><span>%s</span></a>' % (h, esc(t), esc(d)) for h, t, d in tiles)
        return self.page("/", "داشبورد", body, subtitle="همه چیز روی همین رایانه اجرا می‌شود؛ هیچ پرسشی بیرون نمی‌رود.")

    # -- markets (D-0141) ------------------------------------------------------------------
    MARKET_TABS = (("overview", "نمای کلی"), ("crypto", "رمزارزها"), ("forex", "فارکس"), ("stocks", "سهام آمریکا"),
                   ("fx", "نرخ مرجع ارزها"), ("rates", "نرخ بهرهٔ بانک‌های مرکزی"), ("us", "اوراق و کالا"),
                   ("world", "اقتصاد کشورها"), ("sources", "منابع"))

    def _try(self, fn):
        try:
            return fn(), None
        except DH.DataError as exc:
            return None, '<div class="err">دریافت نشد (هیچ عددی جایگزین نمی‌شود): <code>%s</code></div>' % esc(exc)

    def _fx_table(self, fx, limit=None):
        rows = fx["rows"][:limit] if limit else fx["rows"]
        return ('<div class="tbl"><table><tr><th>ارز</th><th>کد</th><th class="num">به ازای ۱ یورو</th>'
                '<th class="num">به ازای ۱ دلار</th><th class="num">تاریخ</th></tr>%s</table></div>') % "".join(
            '<tr><td><a href="/markets?tab=fx&amp;ccy=%s">%s</a></td><td class="ltr">%s</td><td class="num">%s</td>'
            '<td class="num">%s</td><td class="num">%s</td></tr>' % (
                esc(urllib.parse.quote(r["ccy"])), esc(r["name_fa"]), esc(r["ccy"]), esc(fmtn(r["per_eur"])),
                esc(fmtn(r["per_usd"])), esc(r["date"])) for r in rows)

    def _rates_table(self, pr, limit=None, stale=False):
        rows = [r for r in pr["rows"] if r["stale"] == stale]
        rows = rows[:limit] if limit else rows
        vmax = max([abs(r["rate"]) for r in rows] or [1.0])
        return ('<div class="tbl"><table><tr><th>کشور / منطقه</th><th class="num">نرخ (٪)</th><th></th>'
                '<th class="num">تاریخ</th></tr>%s</table></div>') % "".join(
            '<tr><td>%s <span class="muted ltr">%s</span></td><td class="num">%s</td><td>%s</td><td class="num">%s</td></tr>'
            % (esc(r["name_fa"]), esc(r["area"]), esc(fmtn(r["rate"], 2)), svg_bar(r["rate"], vmax), esc(r["date"]))
            for r in rows)

    def _spark_card(self, s, href):
        if s.get("error"):
            return ('<div class="card spark-card"><b>%s</b><p class="muted ltr">%s</p><div class="err">%s</div></div>'
                    % (esc(s["title_fa"]), esc(s["unit"]), esc(s["error"])))
        pts = s["points"]
        first, last = pts[0]["value"], pts[-1]["value"]
        chg = last - first
        return ('<a class="card spark-card tile" href="%s"><b>%s</b><div class="v">%s</div><div class="u ltr">%s &middot; %s</div>'
                '%s<div class="u">تغییر در %d روز معاملاتی: <span class="%s">%s</span></div></a>') % (
            href, esc(s["title_fa"]), esc(fmtn(last)), esc(s["unit"]), esc(pts[-1]["date"]),
            svg_line([(p["date"], p["value"]) for p in pts], w=300, h=80, pad=6, label=s["series"]),
            len(pts), "ok" if chg >= 0 else "bad", esc(("+" if chg >= 0 else "") + fmtn(chg)))

    def p_markets(self, method, q, f):
        tab = q.get("tab") or "overview"
        if tab not in dict(self.MARKET_TABS):
            tab = "overview"
        tabs = '<nav class="tabs">%s</nav>' % "".join(
            '<a href="/markets?tab=%s"%s>%s</a>' % (k, ' class="on"' if k == tab else "", esc(t)) for k, t in self.MARKET_TABS)
        body = tabs + getattr(self, "_mk_" + tab)(q)
        return self.page("/markets", "بازارها و داده‌ها", body,
                         subtitle="داده‌های رسمی روزانه یا سالانه از چند منبع مجاز؛ هیچ‌کدام لحظه‌ای نیست.")

    def _mk_overview(self, q):
        out = ['<div class="grid g2">']
        fx, err = self._try(self.hub.fx)
        out.append('<div class="card"><h2>ارزهای اصلی</h2>%s%s<p class="note">%s</p><a href="/markets?tab=fx">همهٔ ۲۹ ارز و '
                   'مبدل ارز &larr;</a></div>' % (err or self._fx_table(
                       {"rows": [r for r in fx["rows"] if r["ccy"] in ("USD", "GBP", "JPY", "CHF", "CNY", "TRY")]}),
                       notices_html(fx["notices"]) if fx else "", esc(fx["note"]) if fx else ""))
        pr, err = self._try(self.hub.policy_rates)
        out.append('<div class="card"><h2>بالاترین نرخ‌های بهرهٔ سیاستی</h2>%s%s<a href="/markets?tab=rates">همهٔ بانک‌های '
                   'مرکزی &larr;</a></div>' % (err or self._rates_table(pr, limit=8), notices_html(pr["notices"]) if pr else ""))
        cr, err = self._try(lambda: self.hub.crypto("usd", 50))
        out.append('<div class="card"><h2>رمزارزهای بزرگ</h2>%s%s<a href="/markets?tab=crypto">۵۰ رمزارز بزرگ و نمودار &larr;</a>'
                   '</div>' % (err or self._crypto_table(cr, limit=6, compact=True), self._attrib(cr) if cr else ""))
        out.append("</div>")
        board = self.hub.fred_board(30)
        out.append('<h2>اوراق خزانه، نفت، گاز و دلار آمریکا</h2><div class="grid g3">%s</div>' % "".join(
            self._spark_card(s, "/markets?tab=us&amp;series=%s" % esc(s["series"])) for s in board))
        out.append(notices_html(DH.required_notices(["fred"])))
        return "".join(out)

    def _mk_fx(self, q):
        fx, err = self._try(self.hub.fx)
        if err:
            return err
        ccys = ["EUR"] + [r["ccy"] for r in fx["rows"]]
        conv = ""
        if q.get("amount") or q.get("from") or q.get("to"):
            try:
                amount = parse_number((q.get("amount") or "").strip())
                c = self.hub.convert(amount, q.get("from") or "", q.get("to") or "", fx)
                conv = ('<div class="card result"><div class="muted">%s %s =</div><div class="big" id="fx-result">%s %s</div>'
                        '<p class="note">نرخ: ۱ %s = %s %s &middot; تاریخ نرخ‌ها %s &middot; %s</p>'
                        '<button type="button" class="ghost is-hidden" data-copy="#fx-result">کپی</button></div>') % (
                    esc(fmtn(c["amount"])), esc(c["from"]), esc(fmtn(c["result"])), esc(c["to"]), esc(c["from"]),
                    esc(fmtn(c["rate"], 6)), esc(c["to"]), esc(c["date"]), esc(c["label"]))
            except (DH.DataError, ValueError) as exc:
                conv = '<div class="err">تبدیل انجام نشد: <code>%s</code></div>' % esc(exc)

        def sel(name, cur):
            return '<select name="%s">%s</select>' % (name, "".join(
                '<option value="%s"%s>%s %s</option>' % (esc(c), " selected" if c == cur else "", esc(c),
                                                       esc(DH.CURRENCIES.get(c, "یورو"))) for c in ccys))
        form = ('<form method="get" action="/markets" class="card"><input type="hidden" name="tab" value="fx">'
                '<h2>مبدل ارز</h2><div class="form-row"><label>مبلغ<input name="amount" dir="ltr" value="%s"></label>'
                '<label>از%s</label><label>به%s</label><button>تبدیل</button></div>'
                '<p class="note">نرخ متقاطع از دو نرخ مرجع همان روز محاسبه می‌شود (COMPUTED)؛ اگر تاریخ‌ها فرق کنند رد می‌شود.</p>'
                '</form>') % (esc(q.get("amount") or "100"), sel("from", q.get("from") or "USD"), sel("to", q.get("to") or "EUR"))
        chart = ""
        ccy = q.get("ccy") or "USD"
        hist, herr = self._try(lambda: self.hub.fx_history(ccy, 90))
        if hist:
            chart = ('<div class="card"><h2>%s در برابر یورو (۹۰ روز اخیر)</h2>%s<p class="note ltr">%s per EUR, ECB reference rate</p>'
                     '</div>') % (esc(DH.CURRENCIES.get(ccy, ccy)), svg_line([(p["date"], p["value"]) for p in hist],
                                                                           label=ccy), esc(ccy))
        else:
            chart = herr or ""
        return (conv + form + chart + '<div class="card"><h2>نرخ مرجع همهٔ ارزها</h2><p class="note">%s</p>%s%s</div>'
                % (esc(fx["note"]), self._fx_table(fx), notices_html(fx["notices"])))

    def _mk_rates(self, q):
        pr, err = self._try(self.hub.policy_rates)
        if err:
            return err
        return ('<div class="card"><h2>%d بانک مرکزی با دادهٔ جاری</h2>%s<p class="note">%s</p>%s</div>'
                '<details class="card"><summary>سری‌های قدیمی و متوقف‌شده (%d)</summary>%s</details>') % (
            pr["n_current"], self._rates_table(pr), esc(pr["note"]), notices_html(pr["notices"]),
            len(pr["rows"]) - pr["n_current"], self._rates_table(pr, stale=True))

    def _mk_us(self, q):
        series = q.get("series")
        if series:
            s, err = self._try(lambda: self.hub.fred_series(series, 250))
            if err:
                return err + '<p><a href="/markets?tab=us">&larr; همهٔ سری‌ها</a></p>'
            pts = s["points"]
            vals = [p["value"] for p in pts]
            stats = (("آخرین", fmtn(vals[-1])), ("کمینه", fmtn(min(vals))), ("بیشینه", fmtn(max(vals))),
                     ("میانگین", fmtn(sum(vals) / len(vals))))
            return ('<p><a href="/markets?tab=us">&larr; همهٔ سری‌ها</a></p><div class="card"><h2>%s</h2>'
                    '<p class="muted ltr">%s &middot; %s &middot; %d observations</p><div class="stats">%s</div>%s%s</div>') % (
                esc(s["title_fa"]), esc(s["series"]), esc(s["unit"]), len(pts),
                "".join('<div class="stat"><div class="k">%s</div><div class="v ltr">%s</div></div>' % (esc(k), esc(v))
                        for k, v in stats),
                svg_line([(p["date"], p["value"]) for p in pts], h=240, label=s["series"]), notices_html(s["notices"]))
        board = self.hub.fred_board(60)
        return ('<div class="grid g3">%s</div>%s<p class="note">S&amp;P 500 عمداً حذف شده است: یادداشت FRED برای آن '
                'ادعای حق نشر دارد.</p>') % ("".join(self._spark_card(s, "/markets?tab=us&amp;series=%s" % esc(s["series"]))
                                                for s in board), notices_html(DH.required_notices(["fred"])))

    def _mk_world(self, q):
        ind = q.get("ind") or "FP.CPI.TOTL.ZG"
        if ind not in DH.WB_INDICATORS:
            ind = "FP.CPI.TOTL.ZG"
        chosen = [c for c in (q.get("c") or "IR,TR,US,XM,CN,GB").split(",") if c in DH.COUNTRIES][:8] or ["IR", "US"]
        opts = "".join('<option value="%s"%s>%s</option>' % (esc(k), " selected" if k == ind else "", esc(v[1]))
                       for k, v in DH.WB_INDICATORS.items())
        form = ('<form method="get" action="/markets" class="card"><input type="hidden" name="tab" value="world">'
                '<div class="form-row"><label>شاخص<select name="ind">%s</select></label>'
                '<label>کشورها (کد دوحرفی، با کاما، حداکثر ۸)<input name="c" dir="ltr" value="%s"></label>'
                '<button>نمایش</button></div><p class="note">کدها: %s</p></form>') % (
            opts, esc(",".join(chosen)), esc("، ".join("%s %s" % (k, v[1]) for k, v in sorted(DH.COUNTRIES.items()))))
        w, err = self._try(lambda: self.hub.world(ind, chosen, mrv=8))
        if err:
            return form + err
        chart, legend = svg_multi([(r["name_fa"], [(p["year"], p["value"]) for p in r["points"]]) for r in w["rows"]])
        years = sorted({p["year"] for r in w["rows"] for p in r["points"]})
        table = '<div class="tbl"><table><tr><th>کشور</th>%s</tr>%s</table></div>' % (
            "".join('<th class="num">%s</th>' % y for y in years),
            "".join("<tr><td>%s</td>%s</tr>" % (esc(r["name_fa"]), "".join(
                '<td class="num">%s</td>' % esc(fmtn({p["year"]: p["value"] for p in r["points"]}.get(y))) for y in years))
                for r in w["rows"]))
        return form + ('<div class="card"><h2>%s</h2><p class="muted ltr">%s &middot; %s</p>%s%s%s<p class="note">%s</p>%s</div>'
                       % (esc(w["title_fa"]), esc(ind), esc(w["unit"]), chart, legend, table, esc(w["note"]),
                          notices_html(w["notices"])))

    # -- D-0142: crypto, forex pairs, US stocks ------------------------------------------
    @staticmethod
    def _chg(v):
        if v is None:
            return '<span class="muted">\u2014</span>'
        return '<span class="chg %s">%s%s%%</span>' % ("up" if v > 0 else ("down" if v < 0 else ""),
                                                      "+" if v > 0 else "", esc("%.2f" % v))

    @staticmethod
    def _attrib(data):
        """CoinGecko API terms §4: 'Powered by CoinGecko', prominent and legible (CSS keeps it >= 10pt)."""
        return '<p class="attrib ltr">%s</p>' % " &middot; ".join(esc(n) for n in (data or {}).get("notices") or ())

    def _crypto_table(self, cr, limit=None, compact=False):
        rows = cr["rows"][:limit] if limit else cr["rows"]
        vs = cr["vs"].upper()
        head = ('<tr><th class="num">#</th><th>نام</th><th class="num">قیمت (%s)</th><th class="num">۲۴ ساعت</th>%s</tr>'
                % (esc(vs), "" if compact else '<th class="num">۷ روز</th><th class="num">ارزش بازار</th>'
                                                '<th class="num">حجم ۲۴ ساعت</th>'))
        body = "".join(
            '<tr><td class="num">%s</td><td><a href="/markets?tab=crypto&amp;coin=%s&amp;vs=%s"><b class="ltr">%s</b></a> '
            '<span class="muted">%s</span></td><td class="num">%s</td><td class="num">%s</td>%s</tr>' % (
                esc(r["rank"] or "\u2014"), esc(urllib.parse.quote(r["id"])), esc(cr["vs"]), esc(r["symbol"]), esc(r["name"]),
                esc(fmtn(r["price"])), self._chg(r["change_24h"]),
                "" if compact else '<td class="num">%s</td><td class="num">%s</td><td class="num">%s</td>' % (
                    self._chg(r["change_7d"]), esc(fmtn(r["market_cap"])), esc(fmtn(r["volume"]))))
            for r in rows)
        return '<div class="tbl"><table>%s%s</table></div>' % (head, body)

    def _mk_crypto(self, q):
        from market import coingecko as _cg
        vs = (q.get("vs") or "usd").strip().lower()
        if vs not in _cg.VS_CURRENCIES:
            vs = "usd"
        coin = (q.get("coin") or "").strip().lower()
        out = []
        g, err = self._try(self.hub.crypto_global)
        if err:
            out.append(err)
        else:
            out.append('<div class="stats">%s</div>' % "".join(
                '<div class="stat"><div class="k">%s</div><div class="v ltr">%s</div><div class="d">%s</div></div>' % (k, v, d)
                for k, v, d in (
                    ("ارزش کل بازار", esc(fmtn(g["total_market_cap_usd"])) + " $", "تغییر ۲۴ ساعت: " + self._chg(g["change_24h"])),
                    ("حجم معاملات ۲۴ ساعت", esc(fmtn(g["total_volume_usd"])) + " $", "همهٔ صرافی‌های پوشش‌داده‌شده"),
                    ("سهم بیت‌کوین", esc("%.2f%%" % g["btc_dominance"]) if g["btc_dominance"] is not None else "\u2014",
                     "اتریوم: " + (esc("%.2f%%" % g["eth_dominance"]) if g["eth_dominance"] is not None else "\u2014")),
                    ("رمزارزهای فعال", esc(fmtn(g["active"])), "به‌روزرسانی: " + esc(g["updated"] or "\u2014")))))
        if coin:
            ch, err = self._try(lambda: self.hub.crypto_chart(coin, vs, 90))
            if err:
                out.append(err)
            else:
                pts = ch["points"]
                first, last = pts[0]["value"], pts[-1]["value"]
                out.append('<div class="card"><h2 class="ltr">%s / %s</h2><div class="big">%s</div><p class="note">%s &middot; '
                           'تغییر در ۹۰ روز (COMPUTED): %s</p>%s<p class="note ltr">%s</p></div>' % (
                               esc(coin), esc(vs.upper()), esc(fmtn(last)), esc(pts[-1]["date"]),
                               self._chg((last / first - 1.0) * 100.0 if first else None),
                               svg_line([(p["date"], p["value"]) for p in pts], h=240, label=coin), esc(ch["label"])))
        chips = "".join('<a class="chip%s" href="/markets?tab=crypto&amp;vs=%s">%s</a>' % (
            " on" if v == vs else "", v, v.upper()) for v in _cg.VS_CURRENCIES)
        cr, err = self._try(lambda: self.hub.crypto(vs, 50))
        out.append('<div class="card"><h2>۵۰ رمزارز بزرگ بر اساس ارزش بازار</h2><div class="chips">%s</div>%s%s%s</div>' % (
            chips, err or self._crypto_table(cr), ('<p class="note">%s</p>' % esc(cr["note"])) if cr else "",
            self._attrib(cr) if cr else self._attrib({"notices": DH.required_notices(["coingecko"])})))
        return "".join(out)

    def _mk_forex(self, q):
        from market import av_markets as _avm
        frm, to = (q.get("from") or "").strip().upper(), (q.get("to") or "").strip().upper()
        chips = "".join('<a class="chip%s" href="/markets?tab=forex&amp;from=%s&amp;to=%s">%s/%s</a>' % (
            " on" if (a, b) == (frm, to) else "", a, b, a, b) for a, b in _avm.MAJOR_PAIRS)
        form = ('<form method="get" action="/markets" class="card"><input type="hidden" name="tab" value="forex">'
                '<h2>جفت‌ارز</h2><div class="chips">%s</div><div class="form-row"><label>ارز پایه<input name="from" dir="ltr" '
                'maxlength="3" value="%s" placeholder="EUR"></label><label>ارز مظنه<input name="to" dir="ltr" maxlength="3" '
                'value="%s" placeholder="USD"></label><button>نمایش</button></div><p class="note">Alpha Vantage رایگان '
                '(FX_DAILY): نرخ روزانه؛ هر جفت یک درخواست از سهمیهٔ ۲۵تایی روزانه. تا جفتی را انتخاب نکنید چیزی دریافت '
                'نمی‌شود. برای ۲۹ نرخ مرجع رسمی بدون سهمیه، زبانهٔ <a href="/markets?tab=fx">نرخ مرجع ارزها</a> را ببینید.'
                '</p></form>') % (chips, esc(frm), esc(to))
        if not (frm or to):
            return form
        p, err = self._try(lambda: self.hub.fx_pair(frm, to))
        if err:
            return form + err
        last, rows = p["last"], p["rows"]
        table = "".join('<tr><td class="num">%s</td><td class="num">%s</td><td class="num">%s</td><td class="num">%s</td>'
                        '<td class="num">%s</td></tr>' % (esc(r["date"]), esc(fmtn(r["open"], 5)), esc(fmtn(r["high"], 5)),
                                                          esc(fmtn(r["low"], 5)), esc(fmtn(r["close"], 5)))
                        for r in reversed(rows[-10:]))
        return form + ('<div class="card"><h2 class="ltr">%s/%s</h2><div class="big">%s</div><p class="note">بسته شدن %s '
                       '&middot; تغییر روزانه: %s &middot; %s</p>%s<div class="tbl"><table><tr><th class="num">تاریخ</th>'
                       '<th class="num">باز شدن</th><th class="num">بیشترین</th><th class="num">کمترین</th>'
                       '<th class="num">بسته شدن</th></tr>%s</table></div><p class="note ltr">%s</p></div>') % (
            esc(p["from"]), esc(p["to"]), esc(fmtn(last["close"], 5)), esc(last["date"]), self._chg(p["change_pct"]),
            esc(p["note"]), svg_line([(r["date"], r["close"]) for r in rows], h=240, label="%s/%s" % (p["from"], p["to"])),
            table, esc(p["label"]))

    def _fundamentals_card(self, t):
        fu, err = self._try(lambda: self.hub.fundamentals(t))
        if err:
            return ('<div class="card"><h2>صورت‌های مالی سالانه (SEC)</h2>%s<p class="note">برای این بخش ایمیل تماس را در '
                    '<code>SEC_CONTACT_EMAIL</code> بگذارید؛ SEC بدون آن درخواست را رد می‌کند.</p></div>') % err
        years = sorted({p["fy_end"] for m in fu["metrics"] for p in m["points"]})[-5:]
        head = "".join('<th class="num">%s</th>' % esc(y[:4] + "/" + y[5:7]) for y in years)
        rows = []
        for m in fu["metrics"]:
            by = {p["fy_end"]: p["value"] for p in m["points"]}
            if not by:
                continue
            rows.append('<tr><th>%s <span class="muted ltr">%s</span></th>%s</tr>' % (
                esc(m["title_fa"]), esc(m["unit"]),
                "".join('<td class="num">%s</td>' % esc(fmtn(by.get(y))) for y in years)))
        return ('<div class="card"><h2>صورت‌های مالی سالانه: <span class="ltr">%s</span></h2><p class="muted">پایان سال مالی '
                '(سال/ماه)</p><div class="tbl"><table><tr><th>شاخص</th>%s</tr>%s</table></div><p class="note">%s</p>'
                '<p class="note ltr">%s &middot; CIK %s</p></div>') % (
            esc(fu["name"]), head, "".join(rows), esc(fu["note"]), esc(fu["label"]), esc(fu["cik"]))

    def _mk_stocks(self, q):
        sym = (q.get("symbol") or "").strip()
        kw = (q.get("q") or "").strip()
        form = ('<form method="get" action="/markets" class="card"><input type="hidden" name="tab" value="stocks">'
                '<div class="form-row"><label>نماد سهم (مثلاً IBM یا AAPL)<input name="symbol" dir="ltr" value="%s"></label>'
                '<button>نمایش</button></div><p class="note">قیمت: Alpha Vantage رایگان، فقط قیمت پایانی روز، ۲۵ درخواست در '
                'روز، با کلید <code>ALPHAVANTAGE_API_KEY</code> (قیمت لحظه‌ای در نسخهٔ رایگان از نظر مقررات مجاز نیست). '
                'صورت‌های مالی: SEC EDGAR، رسمی و رایگان.</p></form>'
                '<form method="get" action="/markets" class="card"><input type="hidden" name="tab" value="stocks">'
                '<div class="form-row"><label>جست‌وجوی نماد با نام شرکت<input name="q" dir="ltr" value="%s" '
                'placeholder="microsoft"></label><button class="ghost">جست‌وجو</button></div></form>') % (esc(sym), esc(kw))
        out = [form]
        if kw:
            res, err = self._try(lambda: self.hub.search(kw))
            out.append(err or ('<div class="card"><h2>نتیجهٔ جست‌وجو</h2><div class="tbl"><table><tr><th>نماد</th><th>نام</th>'
                               '<th>نوع</th><th>منطقه</th><th>ارز</th></tr>%s</table></div></div>') % ("".join(
                '<tr><td class="ltr"><a href="/markets?tab=stocks&amp;symbol=%s">%s</a></td><td class="ltr">%s</td><td>%s</td>'
                '<td>%s</td><td class="ltr">%s</td></tr>' % (esc(urllib.parse.quote(r["symbol"])), esc(r["symbol"]),
                                                            esc(r["name"]), esc(r["type"]), esc(r["region"]), esc(r["currency"]))
                for r in res) or '<tr><td colspan="5" class="muted">نتیجه‌ای پیدا نشد.</td></tr>'))
        if not sym:
            return "".join(out)
        s, err = self._try(lambda: self.hub.stock(sym))
        if err:
            out.append(err)
        else:
            pts = s["points"]
            chg = ((pts[-1]["value"] / pts[-2]["value"] - 1.0) * 100.0) if len(pts) > 1 and pts[-2]["value"] else None
            out.append(('<div class="card"><h2 class="ltr">%s</h2><div class="big">%s</div><p class="note">%s &middot; تغییر '
                        'روزانه (COMPUTED): %s &middot; %s</p>%s<p class="note ltr">%s</p></div>') % (
                esc(s["symbol"]), esc(fmtn(s["last"]["value"])), esc(s["last"]["date"]), self._chg(chg), esc(s["note"]),
                svg_line([(p["date"], p["value"]) for p in pts], h=240, label=s["symbol"]), esc(s["label"])))
        if re.match(r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$", sym):
            out.append(self._fundamentals_card(sym))
        return "".join(out)

    def _mk_sources(self, q):
        rows = "".join('<tr><td>%s</td><td>%s</td><td>%s</td><td class="ltr">%s</td></tr>' % (
            esc(n), esc(d), esc(k), esc(key)) for key, n, d, k in DH.SOURCES_FA)
        return ('<div class="card"><h2>منابع داده و دلیل انتخاب</h2><p>هیچ منبع رایگانی همهٔ بازارها را پوشش نمی‌دهد و مجوز '
                'استفادهٔ ماشینی هم داشته باشد؛ پس برای هر نوع دارایی قوی‌ترین منبع مجاز انتخاب شده و همه کنار هم کار می‌کنند.</p>'
                '<div class="tbl"><table><tr><th>منبع</th><th>چه می‌دهد</th><th>نیاز</th><th>کلید ثبت</th></tr>%s</table></div>'
                '<p class="note">کنار گذاشته‌شده‌ها: Twelve Data (پولی)، TradingView (شرایطش استفادهٔ ماشینی را منع می‌کند)، '
                'Stooq (شرایطش خوانا نبود)، Kraken (شرایطش ساکنان ایران را مستثنا می‌کند)، Binance (صفحهٔ شرایطش بررسی‌پذیر '
                'نبود)، بازار ایران (به تصمیم مالک خارج از محدوده). داده‌ها روی دیسک ذخیره نمی‌شوند و فقط %d دقیقه در حافظه '
                'می‌مانند.</p>%s</div>') % (rows, int(DH.CACHE_TTL_S // 60),
                                            self._attrib({"notices": DH.required_notices(["coingecko"])}))

    def p_ask(self, method, q, f):
        body = ""
        saved_engine = self.settings["active"]["engine"]
        engine = (f.get("engine") if method == "POST" else None) or saved_engine
        rlabel = self.remote_label()
        if self.assistant is None and engine == "local":
            body += ('<div class="warn">مدل محلی بارگذاری نشده است. سرور را این‌طور اجرا کنید:<pre>python scripts\\ui.py '
                     '--model C:\\models\\Qwen3.5-4B-Q4_K_M.gguf</pre>یا موتور «آنلاین» را انتخاب کنید '
                     '(<a href="/providers">ارائه‌دهنده‌ها</a>). بقیهٔ صفحه‌ها بدون مدل کار می‌کنند.</div>')
        if method == "POST":
            question = (f.get("question") or "").strip()
            if engine not in PS.ENGINES:
                body += '<div class="err">موتور ناشناخته: <code>%s</code></div>' % esc(engine)
            elif not question:
                body += '<div class="err">سؤال خالی است.</div>'
            elif engine == "remote":
                try:
                    bot, label = self.remote_assistant()
                    out = bot.answer(question)
                except (LP.ProviderError, ValueError) as exc:
                    body += ('<div class="err">موتور آنلاین در دسترس نیست: %s<br>'
                             '<a href="/providers">تنظیم ارائه‌دهنده</a></div>') % esc(LP.redact(exc))
                else:
                    out["engine_label"] = "آنلاین · " + label
                    self.history.append(out)
            elif self.assistant is None:
                body += '<div class="err">بدون مدل نمی‌توان پاسخ داد.</div>'
            else:
                out = self.assistant.answer(question)
                out["engine_label"] = "آفلاین · " + (self.model_label or "مدل محلی")
                self.history.append(out)
        examples = ("نرخ تورم آمریکا در ژانویه ۲۰۲۴ چقدر بود؟", "سهمی با قیمت ۱۵۰ دلار و سود هر سهم ۸٫۴۰ دلار؛ P/E چقدر است؟",
                    "موجودی ۵۰٬۰۰۰ دلار، ریسک ۲٪، ورود ۸۰ و حد ضرر ۷۶؛ چند سهم بخرم؟", "What was Apple's net income in fiscal 2023?")
        seg = ('<fieldset class="seg"><legend>موتور پاسخ‌گویی</legend>'
               '<label><input type="radio" name="engine" value="local"%s> آفلاین <span class="muted">(%s، بدون اینترنت)</span></label>'
               '<label><input type="radio" name="engine" value="remote"%s%s> آنلاین <span class="muted ltr">(%s)</span></label>'
               '</fieldset>') % (
            ' checked' if engine != "remote" else "", esc(self.model_label or "مدل محلی"),
            ' checked' if engine == "remote" else "", "" if rlabel else " disabled",
            esc(rlabel or "تنظیم نشده"))
        body += ('<form method="post" class="card" data-busy="در حال فکر کردن...">%s%s<textarea id="q" name="question" rows="3" '
                 'dir="auto" placeholder="مثلاً: نرخ تورم آمریکا در ژانویه ۲۰۲۴ چقدر بود؟"></textarea>'
                 '<div class="chips">%s</div><div class="form-row"><button>بپرس</button>'
                 '<span class="note">Ctrl+Enter هم ارسال می‌کند. آفلاین روی i5-12400 هر پاسخ حدود ۳۰ تا ۹۰ ثانیه '
                 '(MEASURED در بنچمارک). آنلاین: سؤال و داده‌های بازیابی‌شده به ارائه‌دهندهٔ انتخابی فرستاده می‌شود.'
                 '</span></div></form>') % (self.hidden(), seg, "".join(
                     '<button type="button" class="chip is-hidden" data-target="#q" data-fill="%s">%s</button>'
                     % (esc(e), esc(e)) for e in examples))
        for out in reversed(self.history):
            if out.get("engine_label"):
                body += '<div class="engine-tag">%s</div>' % esc(out["engine_label"])
            body += ASK.turn_html(out)
        return self.page("/ask", "پرسش از مدل", body,
                         subtitle="مسیر خودکار: محاسبه، داده‌های کلان، اسناد یا پاسخ ساده؛ اعداد پاسخ با شواهد کنترل می‌شوند.")

    def _calc_index(self, unknown=""):
        cats = CAT.by_category()
        chips = '<button type="button" class="chip on is-hidden" data-cat-chip="all">همه</button>' + "".join(
            '<button type="button" class="chip is-hidden" data-cat-chip="%s">%s (%d)</button>' % (k, esc(t), len(n))
            for k, t, n in cats)
        secs = []
        for key, title, names in cats:
            cards = "".join(
                '<a class="tool-card" href="/calc?tool=%s" data-cat="%s" data-search="%s"><span class="tool-title">%s</span>'
                '<span class="rule"></span><span class="tool-usage">%s</span><span class="tool-name ltr">%s</span></a>' % (
                    esc(urllib.parse.quote(n)), key, esc(" ".join((n, CAT.TOOLS[n][1], CAT.TOOLS[n][2], title))),
                    esc(CAT.TOOLS[n][1]), esc(CAT.TOOLS[n][2]), esc(n)) for n in names)
            secs.append('<section class="cat" id="cat-%s"><h2>%s <span class="badge">%d</span></h2><div class="cards">%s</div>'
                        '</section>' % (key, esc(title), len(names), cards))
        head = ('<div class="toolbar"><input id="tool-search" class="search is-hidden" type="search" '
                'placeholder="جست‌وجو: نام فارسی، انگلیسی یا کاربرد (کلید /)" aria-label="جست‌وجو"> '
                '<span class="muted"><span id="tool-count">%d</span> فرمول</span></div><div class="chips">%s</div>'
                '<p id="tool-empty" class="muted is-hidden">فرمولی با این عبارت پیدا نشد.</p>') % (len(CAT.TOOLS), chips)
        body = (('<div class="err">ابزار ناشناخته: <code>%s</code></div>' % esc(unknown)) if unknown else "") + head + "".join(secs)
        return self.page("/calc", "فرمول‌ها و ماشین‌حساب‌ها", body,
                         subtitle="%d محاسبهٔ قطعی و آفلاین؛ به مدل یا اینترنت نیاز ندارند. زیر نام هر فرمول کاربردش آمده است."
                         % len(CAT.TOOLS))

    def p_calc(self, method, q, f):
        schemas = {s["function"]["name"]: s for s in REG.tool_schemas()}
        name = (f.get("tool") if method == "POST" else q.get("tool")) or ""
        if name not in schemas:
            return self._calc_index(unknown=name)
        sch = schemas[name]
        fn = sch["function"]
        req = set(fn["parameters"]["required"])
        cat, title, usage, example = CAT.TOOLS[name]
        values = dict(f) if method == "POST" else (
            {k: CAT.example_text(v) for k, v in example.items()} if q.get("example") else {})
        result = ""
        if method == "POST":
            try:
                args = form_to_arguments(sch, f)
                r = REG.call_tool(name, args)
            except ValueError as exc:
                r = {"ok": False, "error": "invalid_argument", "message": str(exc)}
            if r["ok"]:
                v = r["value"]
                pretty = (('<div class="big" id="calc-value">%s</div>' % esc(fmtn(v, 6 if abs(v) < 10 else 4)))
                          if isinstance(v, (int, float)) and not isinstance(v, bool) else
                          value_table(v) if isinstance(v, (dict, list)) else "")
                result = ('<div class="card result"><div class="muted">نتیجه (COMPUTED)</div>%s'
                          '<details><summary class="note">مقدار دقیق و جزئیات</summary><p><code>%s</code> %s</p>'
                          '<span class="note">فرمول:</span> <code>%s</code><br><span class="note">ورودی‌ها:</span> <code>%s</code>%s'
                          '</details><button type="button" class="ghost is-hidden" data-copy="#calc-value">کپی</button></div>'
                          % (pretty, esc(r["value"]), esc(r.get("units") or ""), esc(r.get("formula")),
                             esc(json.dumps(r.get("inputs"), ensure_ascii=False, default=str)),
                             ("<br><span class=\"note\">%s</span>" % esc(r["notes"])) if r.get("notes") else ""))
            else:
                result = '<div class="card refusal"><b>امتناع</b>: <code>%s</code> %s</div>' % (esc(r["error"]), esc(r.get("message")))
        fields = []
        for p, spec in fn["parameters"]["properties"].items():
            t = spec.get("type")
            label, hint = CAT.PARAMS[p]
            cur = values.get(p, "")
            if "enum" in spec:
                ctl = '<select name="%s"><option value=""></option>%s</select>' % (esc(p), "".join(
                    '<option value="%s"%s>%s</option>' % (esc(o), " selected" if cur == o else "", esc(CAT.ENUM_FA.get(o, o)))
                    for o in spec["enum"]))
            elif t == "boolean":
                ctl = '<select name="%s"><option value=""></option>%s</select>' % (esc(p), "".join(
                    '<option value="%s"%s>%s</option>' % (o, " selected" if cur == o else "", lab)
                    for o, lab in (("true", "بله (true)"), ("false", "خیر (false)"))))
            elif t == "array":
                ctl = '<textarea name="%s" rows="2" dir="ltr" placeholder="اعداد را با کاما جدا کنید">%s</textarea>' % (
                    esc(p), esc(cur))
            else:
                ctl = '<input name="%s" value="%s" dir="ltr" inputmode="decimal">' % (esc(p), esc(cur))
            fields.append('<div class="field"><label>%s%s <span class="muted ltr">%s</span></label>%s<span class="hint">%s</span></div>'
                          % (esc(label), ' <span class="req">*</span>' if p in req else "", esc(p), ctl, esc(hint)))
        body = ('<p><a href="/calc">&larr; همهٔ فرمول‌ها</a> &middot; <span class="badge">%s</span></p>'
                '<div class="card"><h2>%s <span class="muted ltr">%s</span></h2><hr class="rule"><p class="usage">%s</p>'
                '<p class="note ltr">%s</p><p class="example">مثال آماده: <a href="/calc?tool=%s&amp;example=1">پر کردن فرم با '
                'مثال</a> <span class="muted ltr">%s</span></p>'
                '<form method="post">%s<input type="hidden" name="tool" value="%s"><div class="fields">%s</div>'
                '<p class="note"><span class="req">*</span> الزامی؛ خانهٔ خالی یعنی مقدار پیش‌فرض. ارقام فارسی (۸٫۴۰) و '
                'جداکنندهٔ هزارگان (۵۰٬۰۰۰) هم پذیرفته می‌شوند.</p><button>محاسبه</button></form></div>%s') % (
            esc(CAT.category_title(cat)), esc(title), esc(name), esc(usage), esc(fn["description"]),
            esc(urllib.parse.quote(name)), esc(json.dumps(example, ensure_ascii=False)), self.hidden(), esc(name),
            "".join(fields), result)
        return self.page("/calc", title, body, subtitle=usage)

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

    # -- D-0142: providers manager ---------------------------------------------------
    def _save_settings(self, new):
        """Validate, write atomically, then register. Returns None, or the refusal text."""
        try:
            clean = PS.validate(new)
            PS.save(clean, self.settings_path)
            PS.apply(clean)
        except (PS.SettingsError, LP.ProviderError) as exc:
            return str(exc)
        except OSError as exc:
            return "could not write %s: %s" % (self.settings_path, type(exc).__name__)
        self.settings, self.settings_error, self._remote = clean, None, None
        return None

    def _provider_action(self, f):
        """(ok_html, err_text) for one POST on the providers page."""
        import copy
        act = (f.get("action") or "").strip()
        new = copy.deepcopy(self.settings)
        name = (f.get("name") or "").strip()
        if act == "set_engine":
            new["active"] = {"engine": (f.get("engine") or "local").strip(),
                             "provider": (f.get("provider") or "").strip() or None,
                             "model_id": (f.get("model_id") or "").strip() or None,
                             "allow_paid": f.get("allow_paid") == "on"}
            if new["active"]["engine"] == "local" and not new["active"]["provider"]:
                new["active"]["provider"] = None
            err = self._save_settings(new)
            return (None, err) if err else ("موتور ذخیره شد: <b>%s</b>" % (
                "آفلاین (مدل محلی)" if new["active"]["engine"] == "local" else esc(self.remote_label())), None)
        if act == "save_override":
            if name not in LP.PROVIDERS or name == "local":
                return None, "only a built-in remote provider takes an override"
            entry = {k: (f.get(k) or "").strip() for k in ("base_url", "model_id") if (f.get(k) or "").strip()}
            if entry:
                new["overrides"][name] = entry
            else:
                new["overrides"].pop(name, None)
            err = self._save_settings(new)
            return (None, err) if err else ("تنظیمات <code>%s</code> ذخیره شد." % esc(name), None)
        if act == "clear_override":
            new["overrides"].pop(name, None)
            err = self._save_settings(new)
            return (None, err) if err else ("آدرس و مدل <code>%s</code> به پیش‌فرض برگشت." % esc(name), None)
        if act == "save_custom":
            new["custom"][name] = {"label": (f.get("label") or "").strip() or name,
                                   "wire": (f.get("wire") or "").strip(),
                                   "base_url": (f.get("base_url") or "").strip(),
                                   "env_key": (f.get("env_key") or "").strip() or None,
                                   "model_id": (f.get("model_id") or "").strip() or None}
            err = self._save_settings(new)
            return (None, err) if err else ("ارائه‌دهندهٔ <code>%s</code> ذخیره شد." % esc(name), None)
        if act == "delete_custom":
            if name not in new["custom"]:
                return None, "no user-defined provider named %r" % name
            del new["custom"][name]
            note = ""
            if new["active"].get("provider") == name:
                new["active"] = {"engine": "local", "provider": None, "model_id": None, "allow_paid": False}
                note = " موتور به «آفلاین» برگشت، چون همین ارائه‌دهنده انتخاب شده بود."
            err = self._save_settings(new)
            return (None, err) if err else ("<code>%s</code> حذف شد.%s" % (esc(name), note), None)
        if act == "test":
            try:
                LP.get_provider(name)
                if name == "local":
                    raise LP.ProviderError("the local model has no network endpoint to test")
                eff = PS.effective(self.settings, name)
                res = self._lister(name, base_url=eff["base_url"])
            except LP.ProviderError as exc:
                return None, "connection test failed: %s" % LP.redact(exc)
            ids = res.get("models") or []
            return ('اتصال به <code>%s</code> برقرار است (HTTP %s، %d مدل؛ MEASURED). نمونه: %s' % (
                esc(name), esc(res.get("http_status")), int(res.get("count") or 0),
                " ".join('<code>%s</code>' % esc(m) for m in ids[:12]) or "—"), None)
        return None, "unknown action %r" % act

    def p_providers(self, method, q, f):
        msg = ""
        if method == "POST":
            ok, err = self._provider_action(f)
            msg = ('<div class="err">انجام نشد: %s</div>' % esc(err)) if err else '<div class="okbox">%s</div>' % ok
        if self.settings_error:
            msg = ('<div class="err">فایل تنظیمات خوانده نشد و به آن دست زده نشد: %s<br>تا اصلاح آن، تنظیمات '
                   'پیش‌فرض (موتور آفلاین) به کار می‌رود.</div>' % esc(self.settings_error)) + msg
        rows = PS.provider_rows(self.settings)
        act = self.settings["active"]
        opts = "".join('<option value="%s"%s>%s — %s</option>' % (
            esc(r["provider"]), " selected" if r["provider"] == act.get("provider") else "",
            esc(r["provider"]), esc(r["label"])) for r in rows)
        engine_card = (
            '<form method="post" class="card"><h2>موتور پاسخ‌گویی صفحهٔ «پرسش»</h2>%s'
            '<input type="hidden" name="action" value="set_engine">'
            '<fieldset class="seg"><legend>پیش‌فرض</legend>'
            '<label><input type="radio" name="engine" value="local"%s> آفلاین (مدل محلی؛ هیچ داده‌ای از رایانه خارج نمی‌شود)</label>'
            '<label><input type="radio" name="engine" value="remote"%s> آنلاین (ارائه‌دهندهٔ زیر)</label></fieldset>'
            '<div class="fields"><div class="field"><label>ارائه‌دهنده<select name="provider"><option value="">—</option>%s'
            '</select></label></div><div class="field"><label>شناسهٔ مدل<input name="model_id" class="ltr" value="%s" '
            'placeholder="مثلاً llama-3.3-70b-versatile"></label><span class="hint">خالی = مدلِ ذخیره‌شده برای همان '
            'ارائه‌دهنده</span></div><div class="field"><label class="check"><input type="checkbox" name="allow_paid"%s> '
            'اجازهٔ ارائه‌دهندهٔ پولی یا نامعلوم</label><span class="hint">بدون این، فقط ارائه‌دهنده‌های رایگانِ مستند '
            'یا سرورهای روی همین رایانه اجرا می‌شوند.</span></div></div><div class="form-row"><button>ذخیره</button>'
            '<span class="note">انتخاب در صفحهٔ «پرسش» برای هر سؤال قابل تغییر است.</span></div></form>') % (
            self.hidden(), " checked" if act["engine"] == "local" else "", " checked" if act["engine"] == "remote" else "",
            opts, esc(act.get("model_id") or ""), " checked" if act.get("allow_paid") else "")

        def key_cell(r):
            if not r["key_needed"]:
                return '<span class="muted">نیاز ندارد</span>'
            return '<code>%s</code> %s' % (esc(r["env_key"]), '<span class="badge okb">تنظیم شده</span>' if r["key_set"]
                                           else '<span class="badge dueb">تنظیم نشده</span>')

        def actions(r):
            out = ('<form method="post" class="inline">%s<input type="hidden" name="action" value="test">'
                   '<input type="hidden" name="name" value="%s"><button class="ghost" data-busy="...">آزمون اتصال</button>'
                   '</form>') % (self.hidden(), esc(r["provider"]))
            if r["user_defined"]:
                out += ('<form method="post" class="inline" data-confirm="ارائه‌دهندهٔ %s حذف شود؟">%s'
                        '<input type="hidden" name="action" value="delete_custom"><input type="hidden" name="name" '
                        'value="%s"><button class="ghost danger">حذف</button></form>') % (
                    esc(r["provider"]), self.hidden(), esc(r["provider"]))
            return out
        free = {True: '<span class="badge okb">رایگان مستند</span>', False: '<span class="badge badb">پولی</span>',
                None: '<span class="badge dueb">نامعلوم</span>'}
        trs = "".join(
            '<tr><td class="ltr"><b>%s</b>%s<div class="muted">%s</div></td><td class="ltr">%s</td><td>%s</td>'
            '<td class="ltr"><code>%s</code><div class="muted">%s</div></td><td class="ltr">%s</td><td>%s</td><td>%s</td></tr>' % (
                esc(r["provider"]), ' <span class="badge">شما</span>' if r["user_defined"] else "", esc(r["label"]),
                esc(r["wire"]), key_cell(r), esc(r["base_url"] or "—"),
                {"override": "تغییر داده‌اید", "user": "ارائه‌دهندهٔ شما", "built-in": "پیش‌فرض"}[r["base_url_origin"]],
                esc(r["model_id"] or "—"), free[r["free_tier"]], actions(r)) for r in rows)
        table = ('<div class="card"><h2>ارائه‌دهنده‌ها <span class="badge">%d</span></h2><div class="tbl"><table>'
                 '<tr><th>نام</th><th>گویش API</th><th>کلید</th><th>آدرس پایه (base URL)</th><th>مدل</th><th>هزینه</th>'
                 '<th></th></tr>%s</table></div><p class="note">کلیدها هرگز نمایش یا ذخیره نمی‌شوند؛ فقط وجودشان در متغیر '
                 'محیطی بررسی می‌شود. «آزمون اتصال» فهرست مدل‌ها را می‌گیرد (بدون مصرف توکن) و ریدایرکت را دنبال '
                 'نمی‌کند.</p></div>') % (len(rows), trs)
        builtin = "".join('<option value="%s">%s</option>' % (esc(n), esc(n)) for n in LP.provider_names() if n != "local")
        override = (
            '<form method="post" class="card"><h2>تغییر آدرس پایه یا مدل یک ارائه‌دهندهٔ داخلی</h2>%s'
            '<input type="hidden" name="action" value="save_override"><div class="fields">'
            '<div class="field"><label>ارائه‌دهنده<select name="name">%s</select></label></div>'
            '<div class="field"><label>آدرس پایهٔ دلخواه<input name="base_url" class="ltr" placeholder="https://.../v1"></label>'
            '<span class="hint">خالی = آدرس پیش‌فرض. فقط https، یا http برای localhost.</span></div>'
            '<div class="field"><label>شناسهٔ مدل<input name="model_id" class="ltr"></label></div></div>'
            '<div class="form-row"><button>ذخیره</button><button name="action" value="clear_override" class="ghost">'
            'بازگشت به پیش‌فرض</button></div></form>') % (self.hidden(), builtin)
        wires = "".join('<option value="%s">%s</option>' % (w, t) for w, t in (
            ("openai", "سازگار با OpenAI (Groq، OpenRouter، vLLM، LM Studio، Ollama، ...)"),
            ("anthropic", "Anthropic"), ("google", "Google Gemini")))
        add = (
            '<form method="post" class="card"><h2>افزودن یا ویرایش ارائه‌دهندهٔ شخصی</h2>%s'
            '<input type="hidden" name="action" value="save_custom"><div class="fields">'
            '<div class="field"><label>نام کوتاه *<input name="name" class="ltr" required pattern="[a-z][a-z0-9-]{1,31}" '
            'placeholder="mylab"></label><span class="hint">حروف کوچک انگلیسی، رقم و «-». نام تکراری = ویرایش.</span></div>'
            '<div class="field"><label>عنوان<input name="label" placeholder="My Lab"></label></div>'
            '<div class="field"><label>گویش API *<select name="wire">%s</select></label></div>'
            '<div class="field"><label>آدرس پایه *<input name="base_url" class="ltr" required placeholder="https://api.example.com/v1">'
            '</label><span class="hint">https، یا http://localhost:PORT/v1 برای سرور محلی.</span></div>'
            '<div class="field"><label>نام متغیر محیطی کلید<input name="env_key" class="ltr" placeholder="MYLAB_API_KEY">'
            '</label><span class="hint">فقط «نام» متغیر، نه خود کلید. برای localhost می‌تواند خالی بماند.</span></div>'
            '<div class="field"><label>شناسهٔ مدل<input name="model_id" class="ltr"></label></div></div>'
            '<div class="form-row"><button>ذخیره</button></div></form>') % (self.hidden(), wires)
        howto = ('<div class="card"><h2>کلید را کجا بگذارم؟</h2><p>در PowerShell یک بار اجرا کنید و برنامه را دوباره باز کنید:</p>'
                 '<pre>setx MYLAB_API_KEY "کلید شما"</pre><p class="note">تنظیمات (بدون کلید) در <code class="ltr">%s</code> '
                 'ذخیره می‌شود، بیرون از مخزن.</p></div>') % esc(self.settings_path)
        return self.page("/providers", "ارائه‌دهنده‌ها و موتور پاسخ‌گویی", msg + engine_card + table + add + override + howto,
                         subtitle="افزودن API، آدرس پایهٔ دلخواه، مدل، و جابه‌جایی بین آفلاین و آنلاین.")

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
