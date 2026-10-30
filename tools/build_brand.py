#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_brand.py -- the single source of the Andarz (اندرز) brand assets (D-0143).

    python3 tools/build_brand.py            # rewrite assets/brand/*.svg
    python3 tools/build_brand.py --check    # exit 1 if any committed file differs

Every asset is hand-designed geometry written out here: no raster, no font, no
<text> element in a logo or mark. Both wordmarks -- Latin "Andarz" and Persian
«اندرز» -- are monoline strokes drawn on a grid, so they cannot depend on a font
being installed and carry no font licence. The palette is the owner's
(colorhunt 09251c-a55704-f3d2af-f8eadc).

The mark: an "A" drawn as a rising peak with a lamp-like dot in its counter --
"andarz" is counsel/advice, and the dot is the point of insight under the
trend. Two strokes and a circle, so it stays legible at 16 px.
tests/test_d0143.py checks the committed files equal this output (no drift),
that no logo or mark contains <text>, <image> or a data: URL, and that only
palette colours appear.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "brand")

GREEN = "#09251C"     # deep green
AMBER = "#A55704"     # amber
SAND = "#F3D2AF"      # sand
CREAM = "#F8EADC"     # cream
PALETTE = (GREEN, AMBER, SAND, CREAM)

# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------


def _ell(cx, cy, rx, ry):
    return ("M%g %g A%g %g 0 1 0 %g %g A%g %g 0 1 0 %g %g"
            % (cx - rx, cy, rx, ry, cx + rx, cy, rx, ry, cx - rx, cy))


def _shift(d, dx):
    """Shift an absolute M/L/Q/A path horizontally by dx."""
    out, toks, i = [], d.replace(",", " ").split(), 0
    while i < len(toks):
        t = toks[i]
        cmd, rest = t[0], t[1:]
        if cmd in "MLQ":
            nums = [rest] if rest else []
            j = i + 1
            need = 2 if cmd in "ML" else 4
            while len(nums) < need:
                nums.append(toks[j])
                j += 1
            vals = [float(v) for v in nums]
            for k in range(0, len(vals), 2):
                vals[k] += dx
            out.append(cmd + " ".join("%g" % v for v in vals))
            i = j
        elif cmd == "A":
            nums = [rest] if rest else []
            j = i + 1
            while len(nums) < 7:
                nums.append(toks[j])
                j += 1
            vals = [float(v) for v in nums]
            vals[5] += dx
            out.append("A" + " ".join("%g" % v for v in vals))
            i = j
        else:
            out.append(t)
            i += 1
    return " ".join(out)


#: Latin glyphs, baseline y=0, x from 0. (path, advance width). Stroke 6, round caps.
_LATIN = {
    "A": ("M0 0 L13 -34 L26 0 M6 -13 L20 -13", 26),
    "n": ("M0 -24 L0 0 M0 -13 Q0 -24 9 -24 Q18 -24 18 -13 L18 0", 18),
    "d": (_ell(9, -12, 9, 12) + " M18 -35 L18 0", 18),
    "a": (_ell(9, -12, 9, 12) + " M18 -24 L18 0", 18),
    "r": ("M0 -24 L0 0 M0 -12 Q0 -24 12 -24", 12),
    "z": ("M0 -24 L16 -24 L0 0 L16 0", 16),
}
_LATIN_GAP = 7


def latin_wordmark(text="Andarz"):
    """(path d, width) of the Latin wordmark, x from 0, baseline 0."""
    x, parts = 0.0, []
    for ch in text:
        d, w = _LATIN[ch]
        parts.append(_shift(d, x))
        x += w + _LATIN_GAP
    return " ".join(parts), x - _LATIN_GAP


def persian_wordmark():
    """
    «اندرز», drawn left to right as it appears: ز ر دـ ـن ا (alef and reh do not join
    to the left; initial noon joins final dal). Baseline 0, x from 0. Returns
    (stroke path, [dot centres], width).
    """
    zx, rx, dl = 6, 26, 40
    dv, nx, ax = 56, 68, 84
    d = " ".join([
        "M%d -7 Q%d 6 %d 13" % (zx + 5, zx + 5, zx - 6),        # zain body
        "M%d -7 Q%d 6 %d 13" % (rx + 5, rx + 5, rx - 6),        # reh
        "M%d -19 L%d 0 L%d 0" % (dv - 7, dv, dl),               # dal: head stroke, baseline tail
        "M%d -12 L%d 0 L%d 0" % (nx, nx, dv),                   # initial noon tooth, joined to dal
        "M%d -33 L%d 0" % (ax, ax),                             # alef
    ])
    dots = [(zx + 5, -18), (nx, -23)]
    return d, dots, ax + 3


def _stroke(d, colour, w=6):
    return ('<path d="%s" fill="none" stroke="%s" stroke-width="%g" stroke-linecap="round" '
            'stroke-linejoin="round"/>' % (d, colour, w))


def mark_group(tile, peak, dot, size=64, x=0, y=0, stroke=7.5):
    """The mark on a 64-unit grid. tile=None for the bare (monochrome) mark."""
    s = size / 64.0
    g = ['<g transform="translate(%g %g) scale(%g)">' % (x, y, s)]
    if tile:
        g.append('<rect width="64" height="64" rx="15" fill="%s"/>' % tile)
    g.append('<path d="M15 47 L32 15 L49 47" fill="none" stroke="%s" stroke-width="%g" '
             'stroke-linecap="round" stroke-linejoin="round"/>' % (peak, stroke))
    g.append('<circle cx="32" cy="39" r="4.6" fill="%s"/>' % dot)
    g.append("</g>")
    return "".join(g)


def _svg(w, h, body, title, desc=""):
    d = '<desc id="d">%s</desc>' % desc if desc else ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %g %g" width="%g" height="%g" '
            'role="img" aria-labelledby="t%s"><title id="t">%s</title>%s%s</svg>\n'
            % (w, h, w, h, " d" if desc else "", title, d, body))


MARK_SCHEMES = {
    # name: (tile, peak, dot)   -- used on:
    "mark": (GREEN, SAND, AMBER),          # default app icon (dark tile)
    "mark-light": (CREAM, GREEN, AMBER),   # on dark backgrounds, where a dark tile would vanish
    "mark-mono": (None, GREEN, GREEN),     # one colour, no tile (print, stamps)
}

LOGO_SCHEMES = {
    # name: (mark scheme, latin colour, persian colour, background or None)
    "logo": ("mark", GREEN, AMBER, None),            # light backgrounds (default)
    "logo-dark": ("mark-light", CREAM, SAND, None),  # dark backgrounds
    "logo-mono": ("mark-mono", GREEN, GREEN, None),
}


def mark_svg(name):
    tile, peak, dot = MARK_SCHEMES[name]
    return _svg(64, 64, mark_group(tile, peak, dot), "Andarz")


def favicon_svg():
    # 16 px is 4 device pixels per 16 grid units: a slightly heavier peak and dot.
    return _svg(64, 64, mark_group(GREEN, SAND, AMBER, stroke=9) .replace('r="4.6"', 'r="5.6"'), "Andarz")


def logo_svg(name):
    mk, lat, per, bg = LOGO_SCHEMES[name]
    tile, peak, dot = MARK_SCHEMES[mk]
    ld, lw = latin_wordmark()
    pd, dots, pw = persian_wordmark()
    W, H = 104 + lw + 10, 112
    body = [mark_group(tile, peak, dot, size=72, x=8, y=20)]
    body.append('<g transform="translate(100 58)">%s</g>' % _stroke(ld, lat, 6))
    px = 100 + lw - pw * 0.78
    pgrp = _stroke(pd, per, 6) + "".join('<circle cx="%g" cy="%g" r="3.8" fill="%s"/>' % (cx, cy, per)
                                          for cx, cy in dots)
    body.append('<g transform="translate(%g 92) scale(0.78)">%s</g>' % (px, pgrp))
    if bg:
        body.insert(0, '<rect width="%g" height="%g" rx="18" fill="%s"/>' % (W, H, bg))
    return _svg(W, H, "".join(body), "Andarz — اندرز",
                "Andarz (Persian: اندرز, counsel): local, bilingual financial assistant")


def banner_svg():
    ld, lw = latin_wordmark()
    pd, dots, pw = persian_wordmark()
    per = _stroke(pd, SAND, 6) + "".join('<circle cx="%g" cy="%g" r="3.8" fill="%s"/>' % (cx, cy, SAND)
                                          for cx, cy in dots)
    chips = []
    x = 252
    for label_d, w in ((("Crypto",), 104), (("Forex",), 96), (("US stocks",), 128), (("Macro",), 96),
                       (("85 tools",), 116)):
        chips.append('<g transform="translate(%d 238)"><rect width="%d" height="30" rx="15" fill="%s" '
                     'fill-opacity="0.9" stroke="%s" stroke-opacity="0.55"/>'
                     '<text x="%d" y="20" text-anchor="middle" class="t chip">%s</text></g>'
                     % (x, w, GREEN, SAND, w // 2, label_d[0]))
        x += w + 10
    style = (
        "<style>"
        ".t{font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif}"
        ".chip{font-size:15px;font-weight:600;fill:%s}"
        ".sub{font-size:21px;fill:%s}"
        ".mono{font-family:Consolas,'DejaVu Sans Mono',monospace;font-size:17px;fill:%s}"
        ".line{stroke-dasharray:1500;animation:draw 3s ease-out .3s both}"
        ".fade{animation:in .9s ease-out both}"
        ".d1{animation-delay:.2s}.d2{animation-delay:.7s}.d3{animation-delay:1.2s}.d4{animation-delay:1.7s}"
        ".cur{animation:blink 1s steps(1) infinite}"
        ".pulse{animation:pulse 2.4s ease-in-out infinite;transform-origin:1068px 104px}"
        "@keyframes draw{from{stroke-dashoffset:1500}to{stroke-dashoffset:0}}"
        "@keyframes in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}"
        "@keyframes blink{50%%{opacity:0}}"
        "@keyframes pulse{0%%,100%%{opacity:.9}50%%{opacity:.3}}"
        "@media (prefers-reduced-motion:reduce){.line,.fade,.cur,.pulse{animation:none}}"
        "</style>" % (CREAM, SAND, SAND))
    trend = "M0 322 L130 314 L240 318 L340 306 L440 310 L540 300 L640 302 L740 284 L850 262 L940 200 L1010 148 L1068 104 L1200 74"
    body = [
        style,
        '<rect width="1200" height="340" rx="26" fill="%s"/>' % GREEN,
        '<path d="%s L1200 340 L0 340 Z" fill="%s" fill-opacity="0.10" class="fade d3"/>' % (trend, AMBER),
        '<path class="line" d="%s" fill="none" stroke="%s" stroke-width="4" stroke-linejoin="round" '
        'stroke-linecap="round"/>' % (trend, AMBER),
        '<circle class="pulse" cx="1068" cy="104" r="9" fill="%s"/>' % SAND,
        mark_group(GREEN, SAND, AMBER, size=150, x=60, y=56).replace(
            '<rect width="64" height="64" rx="15" fill="%s"/>' % GREEN,
            '<rect width="64" height="64" rx="15" fill="%s" stroke="%s" stroke-opacity="0.45" stroke-width="1"/>'
            % (GREEN, SAND)),
        '<g class="fade d1" transform="translate(252 122) scale(1.55)">%s</g>' % _stroke(ld, CREAM, 6),
        '<g class="fade d2" transform="translate(%g 126) scale(1.2)">%s</g>' % (252 + lw * 1.55 + 26, per),
        '<text x="252" y="188" class="t sub fade d2">Local · bilingual · evidence-first financial assistant</text>',
        "".join(chips).replace("<g ", '<g class="fade d3" ', 1) if False else
        '<g class="fade d3">%s</g>' % "".join(chips),
        '<text x="252" y="306" class="mono fade d4">$ python scripts/ui.py<tspan class="cur" fill="%s"> ▌</tspan>'
        '</text>' % AMBER,
    ]
    return _svg(1200, 340, "".join(body), "Andarz — اندرز",
                "Andarz: local, bilingual (Persian-English) financial assistant: crypto, forex, US stocks and "
                "macro data, 85 deterministic tools, local model by default.")


def terminal_svg():
    lines = [
        (70, '<tspan fill="%s">C:\\&gt;</tspan> git clone https://github.com/MobitSolidity/marfin-llm.git' % SAND, CREAM),
        (96, '<tspan fill="%s">C:\\&gt;</tspan> cd marfin-llm' % SAND, CREAM),
        (122, '<tspan fill="%s">C:\\marfin-llm&gt;</tspan> bash tests/run_all.sh' % SAND, CREAM),
        (148, "  ... no model and no network needed", SAND),
        (174, "  ALL GREEN", "#7FC8A0"),
        (200, '<tspan fill="%s">C:\\marfin-llm&gt;</tspan> python scripts\\ui.py --model C:\\models\\Qwen3.5-4B-Q4_K_M.gguf'
         % SAND, CREAM),
        (226, "  Andarz UI: http://127.0.0.1:8765/   (Ctrl+C to stop)", "#E7A35C"),
        (252, '<tspan fill="%s">C:\\marfin-llm&gt;</tspan><tspan class="cur" fill="%s"> ▌</tspan>' % (SAND, SAND), CREAM),
    ]
    style = ("<style>.m{font-family:Consolas,'DejaVu Sans Mono',monospace;font-size:15px}"
             ".l{animation:show .01s linear both}"
             + "".join(".l%d{animation-delay:%.1fs}" % (i + 1, 0.4 + 0.8 * i) for i in range(len(lines)))
             + ".cur{animation:blink 1s steps(1) infinite}"
             "@keyframes show{from{opacity:0}to{opacity:1}}@keyframes blink{50%{opacity:0}}"
             "@media (prefers-reduced-motion:reduce){.l,.cur{animation:none}}</style>")
    body = [style, '<rect width="860" height="300" rx="14" fill="%s"/>' % GREEN,
            '<rect width="860" height="36" rx="14" fill="#123A2C"/><rect y="22" width="860" height="14" fill="#123A2C"/>',
            '<circle cx="22" cy="18" r="6" fill="%s"/><circle cx="42" cy="18" r="6" fill="%s"/>'
            '<circle cx="62" cy="18" r="6" fill="%s"/>' % (AMBER, SAND, CREAM),
            '<text x="430" y="23" text-anchor="middle" class="m" font-size="13" fill="%s">cmd — Andarz</text>' % SAND,
            '<g class="m">']
    for i, (y, t, c) in enumerate(lines, 1):
        body.append('<text x="22" y="%d" class="l l%d" fill="%s">%s</text>' % (y, i, c, t))
    body.append("</g>")
    return _svg(860, 300, "".join(body), "Andarz quick start",
                "A terminal session: clone, run the tests, start the local web UI on 127.0.0.1:8765.")


def build():
    files = {"%s.svg" % n: mark_svg(n) for n in MARK_SCHEMES}
    files.update({"%s.svg" % n: logo_svg(n) for n in LOGO_SCHEMES})
    files["favicon.svg"] = favicon_svg()
    files["banner.svg"] = banner_svg()
    files["terminal.svg"] = terminal_svg()
    return files


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    files = build()
    if "--check" in argv:
        bad = [n for n, s in files.items()
               if not os.path.exists(os.path.join(OUT, n))
               or open(os.path.join(OUT, n), encoding="utf-8").read() != s]
        for n in bad:
            print("DRIFT: assets/brand/%s differs from tools/build_brand.py" % n)
        return 1 if bad else 0
    os.makedirs(OUT, exist_ok=True)
    for n, s in sorted(files.items()):
        with open(os.path.join(OUT, n), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(s)
        print("wrote assets/brand/%s" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
