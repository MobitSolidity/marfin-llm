# -*- coding: utf-8 -*-
"""
D-0143: rebrand to Andarz, palette, responsive UI, about route, crypto lookup,
refresh controls, monitor page, learn page. Offline: no test opens a socket to the
internet. (V) verified invariant, (A) adversarial -- must refuse, (B) behaviour.
"""
import io
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from _harness import check, check_raises, check_true, section, summary  # noqa: E402
import _fake_data as FD                                                  # noqa: E402
import build_brand as BB                                                 # noqa: E402
import ui as U                                                           # noqa: E402
from llm import settings as PS                                           # noqa: E402

TMP = tempfile.mkdtemp(prefix="andarz_d0143_")
_SAVED_ENV = dict(os.environ)


def err_type(fn):
    """The exception class name fn raises, or None."""
    try:
        fn()
    except Exception as exc:                                    # noqa: BLE001
        return type(exc).__name__
    return None


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding="utf-8").read()


def app(**kw):
    kw.setdefault("settings_path", os.path.join(tempfile.mkdtemp(dir=TMP), "providers.json"))
    kw.setdefault("paper_dir", tempfile.mkdtemp(dir=TMP))
    kw.setdefault("ask_audit_path", os.path.join(tempfile.mkdtemp(dir=TMP), "a.jsonl"))
    kw.setdefault("hub", FD.hub())
    return U.App(**kw)


# ===========================================================================
section("1. rebrand: Andarz (اندرز) everywhere the user looks; history and settings kept")
# ===========================================================================
A = app()
home = A.handle("GET", "/").body
check_true("the sidebar shows Andarz and اندرز, not the old wordmark",
           'Andarz <b>اندرز</b>' in home and "marfin<b>llm</b>" not in home, "(V)")
check_true("every page title ends in '- Andarz'", "<title>داشبورد - Andarz</title>" in home, "(V)")
check_true("the sidebar uses the standalone mark from the static whitelist",
           'src="/static/mark.svg"' in home and "/static/mark.svg" in U.STATIC, "(V)")
for p in ("/static/logo.svg", "/static/mark.svg", "/static/favicon.svg", "/static/logo-dark.svg"):
    r = A.handle("GET", p)
    check_true("%s served as image/svg+xml from assets/brand/" % p,
               r.status == 200 and r.ctype.startswith("image/svg+xml") and "<svg" in r.body, "(V)")
check_true("brand assets are byte-identical to tools/build_brand.py output (single source, no drift)",
           BB.main(["--check"]) == 0, "(V)")
LOGOS = ("logo.svg", "logo-dark.svg", "logo-mono.svg", "mark.svg", "mark-light.svg", "mark-mono.svg", "favicon.svg")
for n in LOGOS:
    s = read("assets/brand/" + n)
    check_true("%s: hand-written vector only (no <text>, <image>, font or data: URL)" % n,
               not any(x in s for x in ("<text", "<image", "@font-face", "font-family", "data:", "base64")), "(V)")
    cols = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", s)}
    check_true("%s: only the owner's four palette colours" % n, cols <= set(BB.PALETTE), "(V) %r" % sorted(cols))
check_true("full logo carries both wordmarks (Latin and Persian) as drawn paths",
           "Andarz" in read("assets/brand/logo.svg") and read("assets/brand/logo.svg").count("<path") >= 2, "(V)")
check_true("monochrome logo uses exactly one colour", {c.upper() for c in re.findall(
    r"#[0-9A-Fa-f]{6}\b", read("assets/brand/logo-mono.svg"))} == {BB.GREEN}, "(V)")
for n in ("banner.svg", "terminal.svg"):
    s = read("assets/brand/" + n)
    check_true("%s: animation stops under prefers-reduced-motion" % n,
               "@media (prefers-reduced-motion:reduce)" in s and "animation:none" in s, "(V)")
check_true("the old D-0142 logo is gone (its navy/teal colours no longer appear in assets/brand)",
           not any(c in read("assets/brand/" + n).upper() for n in os.listdir(os.path.join(ROOT, "assets", "brand"))
                   for c in ("#0B1B36", "#0E7C7B", "#0D3B5C", "#7FF5DF")), "(V)")
js = read("scripts/ui_assets/app.js")
check_true("theme key is andarz-theme, and a choice saved under marfin-theme still applies",
           'getItem("andarz-theme") || window.localStorage.getItem("marfin-theme")' in js
           and 'setItem("andarz-theme"' in js, "(V)")
check_true("provider settings stay in ~/.marfin/providers.json (existing settings keep working)",
           PS.DEFAULT_PATH.endswith(os.path.join(".marfin", "providers.json")), "(V)")
_ua_hits = subprocess.run(["git", "-C", ROOT, "grep", "-n", "marfin-llm/0", "--", "src", "tools", "scripts"],
                          stdout=subprocess.PIPE, universal_newlines=True).stdout
check_true("no User-Agent still says marfin-llm/<version>", _ua_hits.strip() == "", "(V) %s" % _ua_hits[:200])
from rag import sec_facts as SF                                          # noqa: E402
check_true("SEC User-Agent names the product and the contact",
           SF.user_agent("me@example.com") == "Andarz/0.15 (me@example.com)", "(V)")
from llm import console as CON                                           # noqa: E402
from llm import panel as PAN                                             # noqa: E402
check_true("CLI prompt and console wordmark say Andarz", CON.PROMPT == "andarz> "
           and all("MARFIN" not in r.replace(" ", "") for r in PAN._WORDMARK), "(V)")
_ui_help = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "ui.py"), "--help"],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True).stdout
check_true("ui.py --help names Andarz", "Andarz" in _ui_help and "marfin-llm" not in _ui_help, "(V)")
check_true("README, MODEL_CARD and NOTICE carry the new name; the repository URL is unchanged",
           "**Andarz**" in read("README.md") and "Andarz" in read("MODEL_CARD.md").splitlines()[0]
           and read("NOTICE").startswith("Andarz") and "github.com/MobitSolidity/marfin-llm" in read("README.md"), "(V)")
check_true("history is not rewritten: DECISIONS.md still records marfin-llm",
           "marfin-llm" in read("DECISIONS.md"), "(V)")

# ===========================================================================
section("3. palette: colorhunt 09251c-a55704-f3d2af-f8eadc, AA contrast computed from app.css")
# ===========================================================================
CSS = read("scripts/ui_assets/app.css")


def _lum(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    f = (lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


check("contrast() reproduces the owner's measurement F8EADC/09251C = 13.76",
      round(contrast("#F8EADC", "#09251C"), 2), 13.76, method="(V)")
check("... and A55704/09251C = 3.07 (why a lighter amber is derived for dark-theme text)",
      round(contrast("#A55704", "#09251C"), 2), 3.07, method="(V)")


def _vars(block):
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})", block))


_light = _vars(CSS[CSS.index(":root{"):CSS.index("}", CSS.index(":root{"))])
_d0 = CSS.index(':root[data-theme="dark"]{')
_dark = _vars(CSS[_d0:CSS.index("}", _d0)])
_m0 = CSS.index(":root:not([data-theme=\"light\"]){")
_sys = _vars(CSS[_m0:CSS.index("}", _m0)])
check_true("the prefers-color-scheme block equals the explicit dark theme", _sys == _dark and len(_dark) >= 20, "(V)")
check_true("the four palette colours are the anchors of both themes",
           _light["bg"].upper() == "#F8EADC" and _light["ink"].upper() == "#09251C" and _light["info"].upper() == "#F3D2AF"
           and _dark["bg"].upper() == "#09251C" and _dark["ink"].upper() == "#F8EADC"
           and _light["fill"].upper() == "#A55704" and _dark["fill"].upper() == "#A55704", "(V)")
TEXT_PAIRS = [("ink", s) for s in ("bg", "panel", "panel2", "info", "okbg", "badbg", "duebg")] + \
             [("muted", s) for s in ("bg", "panel", "panel2")] + \
             [("brand", s) for s in ("bg", "panel", "panel2", "info")] + \
             [("btn-ink", "btn"), ("brand-ink", "brand"), ("ok", "okbg"), ("bad", "badbg"), ("due", "duebg"),
              ("ok", "panel"), ("bad", "panel"), ("due", "panel")]
for name, T in (("light", _light), ("dark", _dark)):
    worst = min((contrast(T[a], T[b]), a, b) for a, b in TEXT_PAIRS)
    check_true("%s theme: every text pairing meets WCAG AA 4.5:1 (worst %s/%s = %.2f)" % (name, worst[1], worst[2], worst[0]),
               worst[0] >= 4.5, "(V)")
    sw = min(contrast(T["s%d" % i], T[b]) for i in range(8) for b in ("bg", "panel"))
    check_true("%s theme: all 8 chart series reach 3:1 against the surfaces (graphics, WCAG 1.4.11): %.2f" % (name, sw),
               sw >= 3.0, "(V)")
    check_true("%s theme: the focus ring reaches 3:1 against the surfaces" % name,
               min(contrast(T["focus"], T[b]) for b in ("bg", "panel")) >= 3.0, "(V)")
check_true("dark theme never uses #A55704 for text or links (fails AA there: 3.07)",
           _dark["brand"].upper() != "#A55704" and _dark["due"].upper() != "#A55704", "(V)")
OLD_HEX = ("#0091FF #0B1220 #0B1B36 #0D1220 #0D3B5C #0E7C7B #0F2E25 #12805C #12A594 #151C2E #16213A #1B2333 #1B2337 "
           "#1B2647 #26304A #28C840 #2BC4B0 #2F5BEA #3A1820 #3A2A10 #3CCF91 #5BE6CF #5D6B82 #6B7280 #6D8DFF #7C4DFF "
           "#7FF5DF #8DA2C0 #8E4EC6 #9AA7BD #9FD8CF #A78BFA #B26B00 #BFF8EE #C6283B #CFE9F2 #D6409F #E0B400 #E3E8F0 "
           "#E5484D #E6EDF7 #E6F6EF #E7ECF5 #E9F0FF #F2A93B #F3F5F9 #F59E0B #F8FAFC #FAFAFA #FDECEE #FEBC2E #FF5F57 "
           "#FF6B7A #FFB547 #FFC857 #FFD978 #FFE7A8 #FFF3CD #FFF5E0 #B03A2E").split()
_scan = {p: read(p).upper() for p in ["scripts/ui_assets/app.css", "scripts/ui.py", "scripts/ask.py", "README.md"]
         + ["assets/brand/" + n for n in os.listdir(os.path.join(ROOT, "assets", "brand"))]}
_left = sorted({(p, h) for p, s in _scan.items() for h in OLD_HEX if re.search(re.escape(h) + r"(?![0-9A-F])", s)})
check_true("no colour of the old palette remains in the CSS, UI, ask page, README badges or brand SVGs",
           not _left, "(V) %r" % _left[:6])
check_true("old short hex colours (#fff, #222, #ddd ...) are gone from the ask page",
           not re.search(r"#(fff|222|333|555|666|777|ccc|ddd)\b", read("scripts/ask.py"), re.I), "(V)")
check_true("no gradient brand2 leftovers: buttons use the AA-checked --btn / --btn-ink pair",
           "--brand2" not in CSS and "background:var(--btn);color:var(--btn-ink)" in CSS, "(V)")
check_true("README badges use palette colours", all(c in read("README.md") for c in ("-09251C", "-A55704")), "(V)")
check_true("chart series are distinguishable without colour: 7 of 8 carry a dash pattern",
           len(re.findall(r"\.m\.s[1-7]\{stroke:var\(--s[1-7]\);stroke-dasharray:", CSS)) == 7, "(V)")
check_true("a falling line is dashed as well as red", "svg.chart.down .line{stroke:var(--bad);stroke-dasharray" in CSS, "(V)")
check_true("a rise shows ▲ and +, a fall shows ▼ and -, flat shows neither (not colour alone)",
           U.App._chg(1.5).count("\u25b2 +1.50") == 1 and "\u25bc -2.00" in U.App._chg(-2.0)
           and "\u25b2" not in U.App._chg(0.0) and "\u25bc" not in U.App._chg(0.0), "(V)")
_svg, _leg = U.svg_multi([("a", [("2020", 1.0), ("2021", 2.0)]), ("b", [("2020", 2.0), ("2021", 1.0)])])
check_true("the multi-line legend draws each series' own dash pattern (an SVG swatch, not a colour square)",
           _leg.count('<svg class="lg"') == 2 and 'class="m s1"' in _leg and "<i class" not in _leg, "(V)")

# ===========================================================================
section("2. responsive UI: rules asserted on app.css and the markup (browser audit is dev-only)")
# ===========================================================================
CSS = read("scripts/ui_assets/app.css")
check_true("one 44 px touch-target token, used by buttons, nav links, tabs, chips, inputs, the menu and the theme toggle",
           "--tap:44px" in CSS and all(r in CSS for r in (
               "min-height:var(--tap);", ".theme{background:var(--panel);color:var(--ink);border:1px solid var(--line);"
               "border-radius:10px;width:var(--tap);height:var(--tap)")) and CSS.count("min-height:var(--tap)") >= 10, "(V)")
check_true("inputs use a 16 px minimum font (no iOS zoom on focus)", "font-size:max(1rem,16px)" in CSS, "(V)")
check_true("a visible :focus-visible ring on every control, in the AA-checked --focus colour",
           ":focus-visible{outline:3px solid var(--focus)" in CSS, "(V)")
check_true("reduced motion stops animations and transitions globally",
           "@media (prefers-reduced-motion:reduce)" in CSS and "animation-duration:.01ms !important" in CSS, "(V)")
check_true("grid tracks never demand more than their column (min(...,100%)), so 320 px cannot overflow",
           all("minmax(min(%dpx,100%%),1fr)" % w in CSS for w in (320, 240, 200, 230, 250))
           and not re.search(r"minmax\(\d+px,1fr\)", CSS), "(V)")
check_true("long addresses, symbols and hashes wrap (overflow-wrap:anywhere on code, .ltr and cells)",
           "code,.ltr,td,th,.wrap{overflow-wrap:anywhere}" in CSS, "(V)")
check_true("narrow screens: tabs scroll sideways, form rows stack, buttons go full width",
           "@media (max-width:600px)" in CSS and ".tabs{flex-wrap:nowrap;overflow-x:auto" in CSS
           and ".form-row{flex-direction:column;align-items:stretch}" in CSS, "(V)")
check_true("a checkbox keeps its own size inside a full-width field (MEASURED overflow on /providers otherwise)",
           ".field input[type=checkbox],.field input[type=radio],label.check input,.seg input{width:22px;height:22px}" in CSS, "(V)")
check_true("every disclosure (<summary>) is a 44 px target", "details > summary{min-height:var(--tap)" in CSS, "(V)")
check_true("empty, stale and disabled states have styles", all(x in CSS for x in (
    ".empty{", ".stale{", 'button:disabled,button[aria-disabled="true"]{opacity:.6;cursor:not-allowed}')), "(V)")
b = A.handle("GET", "/").body
check_true("a skip link jumps to the main content (keyboard users)",
           '<a class="skip" href="#main">' in b and '<main class="content" id="main" tabindex="-1">' in b, "(V)")
check_true("the current page is marked aria-current=page in both the sidebar and the mobile menu",
           b.count('class="on" aria-current="page"') == 2, "(V)")
check_true("mobile menu is a <details> (works without JS) with a labelled summary",
           '<details class="menu"><summary aria-label="منوی صفحه‌ها">' in b, "(V)")
check_true("the theme toggle has an accessible name", 'aria-label="تغییر تم روشن و تیره"' in b, "(V)")
check_true("wrap_tables puts a bare table in a scrolling, focusable region",
           U.wrap_tables("<p><table><tr><td>x</td></tr></table></p>")
           == '<p><div class="tbl" tabindex="0" role="region" aria-label="جدول"><table><tr><td>x</td></tr></table></div></p>', "(V)")
check_true("... and leaves an already wrapped table alone",
           U.wrap_tables('<div class="tbl"><table><tr><td>x</td></tr></table></div>')
           == '<div class="tbl"><table><tr><td>x</td></tr></table></div>', "(V)")
check_true("... and does not wrap a table inside an escaped model reply (escaped text is not markup)",
           U.wrap_tables("&lt;table&gt;x&lt;/table&gt;") == "&lt;table&gt;x&lt;/table&gt;", "(A)")
for pth in ("/maintenance", "/phase11", "/audit", "/paper"):
    bb = A.handle("GET", pth).body
    check_true("%s: no bare <table> left outside a .tbl box (the pages that overflowed at 320 px)" % pth,
               not re.search(r'(?<!<div class="tbl" tabindex="0" role="region" aria-label="جدول">)(?<!<div class="tbl">)<table>', bb), "(V)")
check_true("the strict CSP is unchanged by the redesign",
           A.handle("GET", "/").headers["Content-Security-Policy"].startswith("default-src 'none'; style-src 'self'; script-src 'self'"), "(V)")
check_true("still no inline style or event handler anywhere on the home page",
           not re.search(r'\sstyle="|\son[a-z]+="', b), "(V)")

# ===========================================================================
section("8. self-introduction: deterministic 'about' route built from live registries")
# ===========================================================================
import json                                                              # noqa: E402
import ask as ASKM                                                       # noqa: E402
from tools.registry import tool_schemas                                  # noqa: E402
from rag import datahub as DH                                            # noqa: E402


class _Boom(object):
    """A runner that must never be called by the about route."""
    calls = 0

    def generate(self, prompt):
        _Boom.calls += 1
        raise AssertionError("the model was called for a self-introduction")


EN_TRIG = ("who are you", "Who are you?", "introduce yourself", "please introduce yourself",
           "what can you do", "Hello, what is Andarz?", "tell me about yourself", "help")
FA_TRIG = ("خودت را معرفی کن", "خودتو معرفی کن", "تو کی هستی؟", "چه کارهایی بلدی",
           "اندرز چیست", "از خودت بگو", "خودت\u200cرا معرفی کن")
NEG = ("What was Apple's P/E in 2023?", "P/E with price 150 and EPS 6?",
       "who are you going to recommend for my retirement portfolio given inflation and rates rising",
       "نرخ تورم آمریکا در ژانویه ۲۰۲۴ چقدر بود؟", "helpful ratios for banks", "")
for q in EN_TRIG + FA_TRIG:
    check_true("is_about(%r) is true" % q, ASKM.is_about(q), "(B)")
for q in NEG:
    check_true("is_about(%r) is false (not a self-introduction)" % q, not ASKM.is_about(q), "(A)")
check_true("route ROUTES lists 'about' first", ASKM.ROUTES[0] == "about", "(V)")

bot = ASKM.Assistant(_Boom(), use_macro=False)
for q in EN_TRIG[:3] + FA_TRIG[:3]:
    check_true("route(%r) == about" % q, bot.route(q)[0] == "about", "(B)")
_Boom.calls = 0
oe = bot.answer("who are you")
of = bot.answer("خودت را معرفی کن")
check("the model is never called for the about route", _Boom.calls, 0, method="(A)")
check_true("English question -> English reply", oe["lang"] == "en" and "Pages (" in oe["reply"]
           and "\u0635\u0641\u062d\u0647" not in oe["reply"].split("\n")[2], "(B)")
check_true("Persian question -> Persian reply", of["lang"] == "fa" and "\u0635\u0641\u062d\u0647 \u0647\u0627" in of["reply"]
           and "Pages (" not in of["reply"], "(B)")
for o in (oe, of):
    check_true("no 'Apple' or 'AAPL' anywhere in the %s about reply" % o["lang"],
               not re.search(r"apple|aapl", o["reply"], re.I), "(A)")
    check_true("%s reply carries the name, the version and the safety stance" % o["lang"],
               "Andarz" in o["reply"] and read("VERSION").strip() in o["reply"] and "ANALYSIS_ONLY" in o["reply"], "(V)")
f = ASKM.about_facts()
check("pages in the facts == len(ui.NAV)", len(f["pages"]), len(U.NAV), method="(V)")
check("n_tools == len(tool_schemas())", f["n_tools"], len(tool_schemas()), method="(V)")
check("sources == len(DataHub SOURCES_FA)", len(f["sources"]), len(DH.SOURCES_FA), method="(V)")
check_true("EN reply states the live counts", "**Pages (%d):**" % len(U.NAV) in oe["reply"]
           and "%d deterministic tools" % len(tool_schemas()) in oe["reply"]
           and "**Data sources (%d)**" % len(DH.SOURCES_FA) in oe["reply"], "(V)")
check_true("every DataHub source key is listed in the EN reply", all("- %s" % r[0] in oe["reply"] for r in DH.SOURCES_FA), "(V)")
check_true("keyed sources name their env var; CoinGecko's demo key is shown as optional",
           "fred (needs FRED_API_KEY)" in oe["reply"] and "coingecko (no key; optional COINGECKO_DEMO_API_KEY)" in oe["reply"], "(V)")
check_true("all five evidence labels are listed", all(k in oe["reply"] for k in
           ("VERIFIED", "MEASURED", "COMPUTED", "ESTIMATED", "UNKNOWN")), "(V)")
check_true("Persian counts use Persian digits", ("**\u0635\u0641\u062d\u0647 \u0647\u0627 (%s):**" % str(len(U.NAV)).translate(ASKM._FA_DIGITS)) in of["reply"], "(V)")
alt = ASKM.Assistant(_Boom(), use_macro=False, pages=(("/", "Home"), ("/x", "Extra page"))).answer("who are you")
check_true("content follows NAV: a different page list changes the reply", "**Pages (2):**" in alt["reply"]
           and "/x  (Extra page)" in alt["reply"] and alt["reply"] != oe["reply"], "(B)")
check_true("render() marks the turn as built without a model",
           ASKM.render(oe).splitlines()[0] == "route: about   (no model: built from the registries)", "(V)")
check_true("turn_html() meta marks the turn as built without a model",
           '<div class="meta">route: about &middot; no model (registries)</div>' in ASKM.turn_html(oe), "(V)")
check_true("a non-about turn has no 'no model' marker", "no model" not in ASKM.render(dict(oe, about=False, no_model=None, route="plain")).splitlines()[0], "(A)")

check_true("ask.py never imports ui (no import cycle; the UI passes pages=NAV instead)",
           not re.search(r"^\s*(?:import ui\b|from ui import)", read("scripts/ask.py"), re.M)
           and read("scripts/ui.py").count("pages=NAV") == 3, method="(V)")
apath = os.path.join(tempfile.mkdtemp(dir=TMP), "about.jsonl")
ASKM.Assistant(_Boom(), use_macro=False, audit=ASKM.open_audit(apath)).answer("introduce yourself")
recs = [json.loads(x) for x in io.open(apath, encoding="utf-8").read().splitlines() if x.strip()]
check_true("the audit log records the turn with route 'about'", len(recs) == 1 and json.dumps(recs[0]).count('"about"') >= 1, "(V)")

C = app()
check_true("UI with no model loaded: /ask still answers the self-introduction",
           C.assistant is None and "route: about" in C.handle("POST", "/ask", form={"csrf": C.csrf, "question": "خودت را معرفی کن"}).body, "(B)")
cb = C.handle("GET", "/ask").body
check_true("UI with no model: the about turn is labelled as model-free", "بدون مدل · از فهرست‌های برنامه" in cb, "(V)")
check_true("UI with no model: other questions are still refused (no fabricated answer)",
           "بدون مدل نمی‌توان پاسخ داد" in C.handle("POST", "/ask", form={"csrf": C.csrf, "question": "P/E with price 150 and EPS 6?"}).body, "(A)")
chips = re.findall(r'data-fill="([^"]*)"', cb)
check("the /ask page still has 4 example chips", len(chips), 4, method="(V)")
check_true("no chip mentions Apple/AAPL", not any(re.search(r"apple|aapl", c, re.I) for c in chips), "(A)")
check_true("the first chip is the self-introduction and it routes to 'about'", ASKM.is_about(chips[0].replace("&#x27;", "'")), "(B)")
check_true("ask.py docstring no longer uses Apple/AAPL as the example",
           not re.search(r"apple|aapl", ASKM.__doc__ or "", re.I), "(A)")
check_true("docs/deployment.md no longer uses Apple/AAPL as the example", not re.search(r"\bapple\b|\baapl\b", read("docs/deployment.md"), re.I), "(A)")

# ===========================================================================
section("4. crypto token lookup: CoinGecko /search, /coins/{id}, /coins/{platform}/contract/{address}")
# ===========================================================================
import urllib.parse                                                      # noqa: E402
from market import coingecko as CG                                       # noqa: E402
from market import crypto_resolve as CR                                  # noqa: E402

FXD = os.path.join(ROOT, "tests", "fixtures", "coingecko")


def fx(name):
    return json.loads(io.open(os.path.join(FXD, name), encoding="utf-8").read())


UNI = "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984"           # Uniswap on Ethereum (MEASURED fixture)
SOL = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"          # a valid base58 32-byte key
TRX = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"                    # a valid Tron base58check address
_CONTRACT = fx("contract_eth_uni.json")
# Solana / Tron answers are SYNTHETIC: the MEASURED contract shape with another platform's id.
_SYN = {("solana", SOL): dict(_CONTRACT, id="syn-sol", symbol="ssol", name="Synthetic Sol Token",
                              asset_platform_id="solana", contract_address=SOL, platforms={"solana": SOL}),
        ("tron", TRX): dict(_CONTRACT, id="syn-trx", symbol="strx", name="Synthetic Tron Token",
                            asset_platform_id="tron", contract_address=TRX, platforms={"tron": TRX})}
CGLOG = []


def cg_fx(url):
    CGLOG.append(url)
    u = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qs(u.query)
    if u.path.endswith("/search"):
        term = q["query"][0]
        if term == "uniswap":
            return fx("search_uniswap.json")
        if term == "uni":                       # the fixture's coins, searched by symbol
            return fx("search_uniswap.json")
        if term == "broken":
            return {"coins": "not a list"}
        return {"coins": [], "exchanges": [], "categories": []}
    if u.path.endswith("/coins/uniswap"):
        return fx("coin_uniswap.json")
    if u.path.endswith("/coins/listed-only"):
        raise CG.CoinNotFound("404")
    m = re.search(r"/coins/([a-z0-9-]+)/contract/(.+)$", u.path)
    if m:
        if (m.group(1), m.group(2)) == ("ethereum", UNI):
            return _CONTRACT
        if (m.group(1), m.group(2)) in _SYN:
            return _SYN[(m.group(1), m.group(2))]
        raise CG.CoinNotFound("404")            # MEASURED: unknown contract -> 404 coin not found
    return FD.cg_get(url)


def chub(**kw):
    kw.setdefault("cg_get", cg_fx)
    kw.setdefault("cg_per_min", 100)
    return FD.hub(**kw)


# -- fixtures are real recordings -----------------------------------------------------------
check_true("fixtures recorded from one live call per endpoint (search, coin, contract, 404, 429)",
           all(os.path.exists(os.path.join(FXD, n)) for n in (
               "search_uniswap.json", "coin_uniswap.json", "contract_eth_uni.json",
               "contract_not_found.json", "http_429_contract.json", "http_429_throttled.txt")), method="(M)")
check_true("the recorded 404 body is CoinGecko's own 'coin not found'",
           fx("contract_not_found.json") == {"error": "coin not found"}, method="(M)")
check_true("the recorded 429 body is refused, never parsed as data",
           err_type(lambda: CG.parse_coin(fx("http_429_contract.json"))) == "CoinGeckoError"
           and err_type(lambda: CG.parse_search(fx("http_429_contract.json"))) == "CoinGeckoError", method="(M)")
check_true("the 404 body becomes CoinNotFound (not a failure: 'not on this chain')",
           err_type(lambda: CG.parse_coin(fx("contract_not_found.json"))) == "CoinNotFound", method="(V)")

# -- parsing ---------------------------------------------------------------------------------
c = CG.parse_coin(fx("coin_uniswap.json"))
check_true("coin detail: name, symbol, rank and every monitor field parsed from the MEASURED fixture",
           (c["id"], c["symbol"], c["rank"]) == ("uniswap", "UNI", 25) and all(
               c[k] is not None for k in ("price", "change_24h", "change_7d", "market_cap", "volume", "high_24h",
                                          "low_24h", "ath", "atl", "circulating_supply", "total_supply", "max_supply")),
           method="(M)")
check_true("contract addresses come from CoinGecko's own platforms map",
           c["platforms"]["ethereum"] == UNI and c["platforms"]["polygon-pos"].startswith("0x"), method="(M)")
check_true("CoinGecko's timestamp is kept to the second, labelled UTC",
           re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC$", c["last_updated"] or "") is not None, method="(V)")
bare = CG.parse_coin({"id": "x-coin", "symbol": "x", "name": "X", "market_data": {"current_price": {"usd": 0}}})
check_true("a missing or zero figure is None (shown as a dash), never 0",
           bare["price"] is None and bare["market_cap"] is None and bare["ath"] is None and bare["last_updated"] is None,
           method="(A)")
for name, bad in (("a string price", {"id": "a", "symbol": "a", "name": "A", "market_data": {"current_price": {"usd": "7"}}}),
                  ("an infinite price", {"id": "a", "symbol": "a", "name": "A", "market_data": {"current_price": {"usd": float("inf")}}}),
                  ("a boolean supply", {"id": "a", "symbol": "a", "name": "A", "market_data": {"total_supply": True}}),
                  ("an id with a slash", {"id": "../x", "symbol": "a", "name": "A"}),
                  ("market_data not an object", {"id": "a", "symbol": "a", "name": "A", "market_data": []}),
                  ("not an object at all", ["a"])):
    check_true("parse_coin refuses %s (malformed JSON shape)" % name, err_type(lambda: CG.parse_coin(bad)) == "CoinGeckoError", method="(A)")
check_true("parse_search refuses a malformed payload", err_type(lambda: CG.parse_search({"coins": "x"})) == "CoinGeckoError"
           and err_type(lambda: CG.parse_search([1])) == "CoinGeckoError", method="(A)")
srch = CG.parse_search(fx("search_uniswap.json"))
check_true("search keeps only coins, in CoinGecko's order", [x["id"] for x in srch][:2] == ["uniswap", "uniswap-wormhole"], method="(M)")

# -- URLs: only whitelisted platforms and well-formed addresses reach the network ----------
check_true("contract URL: Ethereum address lower-cased (CoinGecko stores it lower-case, MEASURED)",
           CG.contract_url("ethereum", UNI.upper().replace("0X", "0x")).endswith("/coins/ethereum/contract/" + UNI), method="(M)")
for name, fn in (("an unknown platform", lambda: CG.contract_url("dogechain", UNI)),
                 ("a path in the platform", lambda: CG.contract_url("../ethereum", UNI)),
                 ("a short EVM address", lambda: CG.contract_url("ethereum", "0x1234")),
                 ("an EVM address on Solana", lambda: CG.contract_url("solana", UNI)),
                 ("a Solana key on Tron", lambda: CG.contract_url("tron", SOL)),
                 ("a query injected into an address", lambda: CG.contract_url("ethereum", UNI + "?x=1")),
                 ("an empty search", lambda: CG.search_url("   ")),
                 ("a 65-character search", lambda: CG.search_url("a" * 65)),
                 ("a coin id with a slash", lambda: CG.coin_url("a/b"))):
    check_true("URL builder refuses %s" % name, err_type(fn) == "CoinGeckoError", method="(A)")
check_true("chain order is the owner's: Ethereum, BSC, Polygon, Base, Arbitrum, Solana, Tron",
           [p[2] for p in CG.PLATFORMS] == ["Ethereum", "BNB Smart Chain", "Polygon PoS", "Base", "Arbitrum One",
                                            "Solana", "Tron"], method="(V)")

# -- classify / normalise -------------------------------------------------------------------
for text, kind in ((UNI, "evm"), (UNI.upper().replace("0X", "0x"), "evm"), ("\u06f0x" + UNI[2:], "evm"),
                   (SOL, "solana"), (TRX, "tron"), ("uniswap", "name"), ("UNI", "name"), ("\u0628\u06cc\u062a\u200c\u06a9\u0648\u06cc\u0646", "name"),
                   ("0x1234", "invalid"), (TRX[:-1] + "u", "invalid"), (SOL.lower(), "invalid"), (TRX.lower(), "invalid"),
                   ("12345", "invalid"), ("", "invalid"), ("a" * 65, "invalid")):
    check_true("classify(%r) -> %s" % (text[:24], kind), CR.classify(text)["kind"] == kind,
               method="(A)" if kind == "invalid" else "(B)")
check_true("normalise: Persian digits, ZWNJ and Arabic yeh/kaf are folded",
           CR.normalise("\u06f1\u06f2 \u200c\u0643\u064a") == "12 \u06a9\u06cc", method="(V)")
check_true("a mistyped Tron address is refused by its checksum (not searched as a name)",
           "checksum" in CR.classify(TRX[:-1] + "u")["reason"], method="(A)")

# -- the matching rule (pure) ---------------------------------------------------------------
p = CR.pick("uniswap", srch)
check_true("exact id/name -> resolved, the others kept as 'other matches'",
           p["status"] == "resolved" and p["coin_id"] == "uniswap" and p["match"] == "name" and len(p["candidates"]) == 2, method="(B)")
p = CR.pick("uni", srch)
check_true("a symbol shared by two coins -> AMBIGUOUS with ranked candidates, never a silent pick",
           p["status"] == "ambiguous" and p["coin_id"] is None and [x["id"] for x in p["candidates"]] == ["uniswap", "uniswap-wormhole"],
           method="(A)")
p = CR.pick("uni.e", srch)
check_true("a unique symbol -> resolved by symbol", p["status"] == "resolved" and p["match"] == "symbol"
           and p["coin_id"] == "bridged-uniswap-lightlink", method="(B)")
check_true("nothing returned -> not_found", CR.pick("zzz", [])["status"] == "not_found", method="(B)")
check_true("ranking: market-cap rank first, unranked last, CoinGecko's order breaking ties",
           [x["id"] for x in CR.rank([{"id": "a", "rank": None}, {"id": "b", "rank": 9}, {"id": "c", "rank": 2},
                                      {"id": "d", "rank": None}])] == ["c", "b", "a", "d"], method="(V)")

# -- resolve through the DataHub ------------------------------------------------------------
H = chub()
r = H.crypto_lookup("uniswap")
check_true("name -> resolved with CoinGecko's figures and the attribution",
           r["status"] == "resolved" and r["coin"]["id"] == "uniswap" and r["notices"] == ["Powered by CoinGecko"], method="(B)")
check_true("symbol shared by two coins -> ambiguous, no coin detail fetched",
           H.crypto_lookup("UNI")["status"] == "ambiguous" and not any("/coins/uniswap-wormhole" in u for u in CGLOG), method="(A)")
del CGLOG[:]
r = H.crypto_lookup(UNI.upper().replace("0X", "0x"))
check_true("EVM address (wrong case) -> found on Ethereum with ONE call; later chains 'not checked'",
           r["status"] == "resolved" and r["coin"]["found_on"] == "Ethereum" and len(CGLOG) == 1
           and r["checked"][0] == ("Ethereum", "found") and all(st == "not_checked" for _n, st in r["checked"][1:]), method="(B)")
del CGLOG[:]
r = H.crypto_lookup("0x" + "ab" * 20)
check_true("unknown EVM address -> every EVM chain tried in order, then not_found (no guess)",
           r["status"] == "not_found" and [n for n, _s in r["checked"]] == ["Ethereum", "BNB Smart Chain", "Polygon PoS", "Base",
                                                                         "Arbitrum One"] and len(CGLOG) == 5, method="(A)")
r = H.crypto_lookup(SOL)
check_true("Solana address -> the Solana platform only", r["status"] == "resolved" and r["coin"]["found_on"] == "Solana"
           and [n for n, _s in r["checked"]] == ["Solana"], method="(B)")
r = H.crypto_lookup(TRX)
check_true("Tron address -> the Tron platform only", r["status"] == "resolved" and r["coin"]["found_on"] == "Tron", method="(B)")
r = H.crypto_lookup("nosuchcoinzz")
check_true("a name CoinGecko does not know -> not_found, said plainly", r["status"] == "not_found" and r["coin"] is None, method="(A)")
r = H.crypto_lookup("0x1234")
check_true("invalid input -> refused with the reason, no network call", r["status"] == "invalid" and "40 hex" in r["reason"], method="(A)")
r = H.crypto_lookup("\u06cc\u0648\u0646\u06cc \u0633\u0648\u0627\u067e")
check_true("Persian name -> STATIC alias table -> CoinGecko search, labelled STATIC",
           r["status"] == "resolved" and r["alias"]["search"] == "uniswap" and "STATIC" in r["alias"]["label"], method="(B)")
check_true("the alias table only maps to search words (the coin itself always comes from CoinGecko)",
           all(isinstance(v, str) and v == v.lower() for v in CR.ALIASES_FA.values()), method="(V)")
r = H.crypto_lookup("broken")
check_true("malformed /search JSON -> 'error', never a fabricated coin", r["status"] == "error" and r["coin"] is None, method="(A)")

# -- cache, budget, 429 ---------------------------------------------------------------------
del CGLOG[:]
H.crypto_lookup("uniswap")
check("a repeated lookup within 10 minutes is served from the cache (0 network calls)", len(CGLOG), 0, method="(V)")
T = [1000.0]
HB = chub(cg_per_min=2, clock=lambda: T[0])
del CGLOG[:]
r = HB.crypto_lookup("0x" + "cd" * 20)
check_true("budget of 2/min: the 3rd chain is NOT requested; rate_limited with the chains checked so far",
           r["status"] == "rate_limited" and len(CGLOG) == 2 and r["retry_after_s"] > 0
           and ("Polygon PoS", "not_checked") in r["checked"] and "nothing was sent" in r["error"], method="(A)")
check_true("the budget is shown: 0 left, and when the next call frees up", HB.cg_budget()["left"] == 0
           and 1 <= HB.cg_budget()["retry_after_s"] <= 61, method="(V)")
T[0] += 61
check_true("after a minute the budget is back", HB.cg_budget()["left"] == 2, method="(B)")
check("keyless limit is 5/min (official Keyless page)", DH.DataHub().cg_limit() if not os.environ.get("COINGECKO_DEMO_API_KEY") else 5, 5,
      method="(V)")
os.environ["COINGECKO_DEMO_API_KEY"] = "CG-FAKEFAKEFAKEFAKE"
check("with the free Demo key: 30/min", DH.DataHub().cg_limit(), 30, method="(V)")
os.environ.pop("COINGECKO_DEMO_API_KEY")
N429 = []


def cg_429(url):
    N429.append(url)
    raise CG.CoinGeckoError("CoinGecko rate limit reached (status 429). The keyless limit is about 5 calls a minute")


r = chub(cg_get=cg_429).crypto_lookup("uniswap")
check_true("a CoinGecko 429 -> rate_limited, reported, and NOT retried (exactly one call)",
           r["status"] == "rate_limited" and "429" in r["error"] and len(N429) == 1, method="(A)")
_real_gate = CG.check_access
NET = []
try:
    def _deny(key, *a, **k):
        raise S_ACCESS("source %r is disabled" % key)
    from rag.sources import AccessError as S_ACCESS                     # noqa: E402
    CG.check_access = _deny
    for fn in (lambda: CG.fetch_search("uniswap", http_get=NET.append),
               lambda: CG.fetch_coin("uniswap", http_get=NET.append),
               lambda: CG.fetch_contract("ethereum", UNI, http_get=NET.append)):
        check_true("the registry gate runs BEFORE any network call (%d calls)" % len(NET),
                   err_type(fn) == "AccessError" and NET == [], method="(A)")
finally:
    CG.check_access = _real_gate

# -- UI: GET search box on Markets -> crypto (works without JS) -------------------------------
AU = app(hub=chub())
b4 = AU.handle("GET", "/markets", query={"tab": "crypto"}).body
check_true("Markets -> crypto has a GET search form (no JS needed) with a labelled field",
           '<form method="get" action="/markets" class="card" role="search">' in b4 and 'name="lookup"' in b4, method="(V)")
check_true("the form states the chain order and the CoinGecko budget left this minute",
           "Ethereum → BNB Smart Chain" in b4 and "سهمیهٔ CoinGecko" in b4, method="(V)")
bu = AU.handle("GET", "/markets", query={"tab": "crypto", "lookup": "uniswap"}).body
check_true("a lookup shows the coin, its contract addresses and 'Powered by CoinGecko'",
           "Uniswap (UNI)" in bu and UNI in bu and "Powered by CoinGecko" in bu and "آدرس قراردادها" in bu, method="(B)")
ba = AU.handle("GET", "/markets", query={"tab": "crypto", "lookup": "UNI"}).body
check_true("an ambiguous lookup lists ranked candidates as links, nothing picked",
           '<ul class="cands">' in ba and "lookup=uniswap-wormhole" in ba and "بی‌صدا انتخاب نمی‌شود" in ba, method="(A)")
bx = AU.handle("GET", "/markets", query={"tab": "crypto", "lookup": "<script>x</script>"}).body
check_true("hostile lookup text is escaped, never markup", "<script>x</script>" not in bx and "&lt;script&gt;" in bx, method="(A)")
check_true("still no inline style or handler on the crypto tab", not re.search(r'\sstyle="|\son[a-z]+="', bu), method="(V)")

# -- the crypto route in Assistant.route() -----------------------------------------------------
BOT = ASKM.Assistant(_Boom(), use_macro=False, hub=chub())
for q, want in (("uniswap token", "uniswap"), ("price of UNI coin", "uni"), (UNI, UNI), ("\u0642\u06cc\u0645\u062a \u0628\u06cc\u062a \u06a9\u0648\u06cc\u0646", "\u0628\u06cc\u062a \u06a9\u0648\u06cc\u0646"),
                (SOL, SOL), (TRX, TRX)):
    check_true("route(%r) -> crypto %r" % (q[:24], want[:24]), BOT.route(q) == ("crypto", {"query": want}), method="(B)")
for q in ("P/E with price 150 and EPS 6?", "who are you", "\u0646\u0631\u062e \u062a\u0648\u0631\u0645 \u0622\u0645\u0631\u06cc\u06a9\u0627 \u062f\u0631 \u0698\u0627\u0646\u0648\u06cc\u0647 \u06f2\u06f0\u06f2\u06f4 \u0686\u0642\u062f\u0631 \u0628\u0648\u062f\u061f"):
    check_true("route(%r) is not crypto" % q[:24], BOT.route(q)[0] != "crypto", method="(A)")
check_true("without a DataHub the crypto route is off (CLI: no silent network use)",
           ASKM.Assistant(_Boom(), use_macro=False).route("uniswap token")[0] != "crypto", method="(A)")
_Boom.calls = 0
oc = BOT.answer("uniswap token")
check_true("crypto answer: CoinGecko's figures, the model never called", _Boom.calls == 0 and "Uniswap (UNI)" in oc["reply"]
           and oc["route"] == "crypto", method="(A)")
check_true("crypto answer carries 'Powered by CoinGecko' and the not-real-time stance",
           "Powered by CoinGecko" in oc["notices"] and "not real-time" in oc["reply"], method="(V)")
check_true("render/turn_html mark the turn as model-free CoinGecko data",
           "(no model: CoinGecko data as retrieved)" in ASKM.render(oc).splitlines()[0]
           and "no model (CoinGecko)" in ASKM.turn_html(oc), method="(V)")
ocf = BOT.answer("\u0642\u06cc\u0645\u062a \u06cc\u0648\u0646\u06cc \u0633\u0648\u0627\u067e")
check_true("Persian question -> Persian answer", ocf["lang"] == "fa" and "\u0642\u06cc\u0645\u062a" in ocf["reply"], method="(B)")
check_true("ambiguous via the assistant: candidates listed, no figures invented",
           "none is picked silently" in BOT.answer("UNI coin")["reply"], method="(A)")
CU = app(hub=chub())
check_true("UI with no model: a token question is answered from CoinGecko",
           "Uniswap (UNI)" in CU.handle("POST", "/ask", form={"csrf": CU.csrf, "question": "uniswap token"}).body
           and "بدون مدل · داده‌های CoinGecko" in CU.handle("GET", "/ask").body, method="(B)")
check_true("DataHub source list mentions the token lookup",
           "\u062c\u0633\u062a\u200c\u0648\u062c\u0648\u06cc \u062a\u0648\u06a9\u0646" in dict((r[0], r[2]) for r in DH.SOURCES_FA)["coingecko"], method="(V)")
check_true("legal doc lists the new CoinGecko endpoints", all(e in read("docs/legal/market-data-providers.md") for e in
           ("/search", "/coins/{id}", "/coins/{platform}/contract/{address}")), method="(V)")

os.environ.clear()
os.environ.update(_SAVED_ENV)
print("")
sys.exit(summary())
