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

os.environ.clear()
os.environ.update(_SAVED_ENV)
print("")
sys.exit(summary())
