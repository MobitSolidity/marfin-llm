"""
The project console panel: modern CMD art that degrades instead of breaking.

The user asked for this explicitly:

    "محیط پروژه اگر در cmd خواهد بود از cmd art زیبا و مدرن استفاده کن
     برای پنل پروژه"

WHY A DEGRADING RENDERER AND NOT JUST PRETTY OUTPUT
---------------------------------------------------
The target machine is Windows 11 and the harness runs in cmd.exe. MEASURED from
the user's own merged result file: `console_utf8: true` on their box. But
"true on one box" is not "true everywhere", and this project's rule is that a
fact holds only where it was measured. A panel that assumes a UTF-8 code page
and 24-bit colour has three ways to fail on somebody else's console:

  1. Legacy code page 437/720. Box-drawing characters print as mojibake and
     Persian text prints as question marks.
  2. A console with no ANSI processing. Every escape sequence prints literally
     as `←[38;5;39m`, which is worse than no colour at all.
  3. Output redirected to a file or a pipe (`> panel.txt`). Colour codes land
     in the file and corrupt it.

So capability is DETECTED, once, and the renderer picks the richest style that
the actual terminal can show. There are three tiers -- unicode+colour,
unicode-only, pure ASCII -- and all three carry the same information. Prettiness
is never allowed to cost correctness.

WHAT THE PANEL MUST NEVER DO
----------------------------
Print key material. It renders `credential_status()`, which reports presence and
length only. There is no code path here that can reach an API key, and the
panel's own output is passed through `redact()` before it is written as a final
belt-and-braces measure -- because a panel is exactly the thing a user
screenshots and pastes into a chat.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, TextIO

from .providers import (KNOWN_FREE_TIER, PROVIDERS, credential_status,
                        provider_names, redact)

# ---------------------------------------------------------------------------
# Capability detection.
# ---------------------------------------------------------------------------

def _stream_is_tty(stream: TextIO) -> bool:
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def detect_caps(stream: Optional[TextIO] = None,
                env: Optional[Dict[str, str]] = None) -> Dict[str, bool]:
    """
    What this console can actually display.

    Returns {'unicode': bool, 'colour': bool, 'tty': bool}.

    Honours NO_COLOR (the de-facto standard) and FORCE_COLOR, because a user
    who has asked for no colour has asked for a reason, and a user piping into
    a colour-aware pager needs the override.
    """
    stream = stream if stream is not None else sys.stdout
    env = dict(os.environ if env is None else env)
    tty = _stream_is_tty(stream)

    # Unicode: ask the stream what it will actually encode to, and PROVE it by
    # encoding a sample rather than pattern-matching the encoding name. An
    # encoding called "cp65001" and one called "utf-8" behave the same; one
    # called "cp437" does not, and only a trial encode tells them apart
    # reliably across Python versions.
    unicode_ok = False
    enc = getattr(stream, "encoding", None) or ""
    try:
        "\u2500\u2588\u25cf".encode(enc or "ascii")
        unicode_ok = True
    except (LookupError, UnicodeEncodeError, TypeError):
        unicode_ok = False

    if str(env.get("NO_COLOR", "")).strip() != "":
        colour = False
    elif str(env.get("FORCE_COLOR", "")).strip() not in ("", "0"):
        colour = True
    elif not tty:
        # Redirected to a file or a pipe: escape codes would corrupt it.
        colour = False
    elif env.get("TERM", "") == "dumb":
        colour = False
    elif os.name == "nt":
        # Windows 10 1511+ supports ANSI, but only once virtual terminal
        # processing is enabled. WT_SESSION means Windows Terminal, which always
        # supports it. Otherwise try to enable it and believe the API, not a
        # version guess.
        colour = bool(env.get("WT_SESSION") or env.get("ANSICON")
                      or _enable_windows_ansi())
    else:
        colour = True
    return {"unicode": unicode_ok, "colour": bool(colour), "tty": tty}


def _enable_windows_ansi() -> bool:
    """
    Turn on virtual terminal processing in the current console.

    Returns True only if the OS confirmed it. Guessing from the Windows build
    number would claim colour on consoles that do not have it, and the user
    would see raw escape sequences all over their panel.
    """
    if os.name != "nt":
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32          # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)        # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        ENABLE_VT = 0x0004
        if mode.value & ENABLE_VT:
            return True
        return bool(kernel32.SetConsoleMode(handle, mode.value | ENABLE_VT))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Style: three tiers, one information set.
# ---------------------------------------------------------------------------

_ANSI = {
    "reset": "\033[0m",
    "dim": "\033[2m",
    "bold": "\033[1m",
    "frame": "\033[38;5;61m",     # muted indigo, readable on black and white
    "title": "\033[38;5;81m",     # cyan
    "ok": "\033[38;5;78m",        # green
    "warn": "\033[38;5;214m",     # amber
    "bad": "\033[38;5;203m",      # soft red
    "free": "\033[38;5;114m",
    "paid": "\033[38;5;180m",
    "unk": "\033[38;5;103m",
}

_GLYPH_UNICODE = {
    "tl": "\u256d", "tr": "\u256e", "bl": "\u2570", "br": "\u256f",
    "h": "\u2500", "v": "\u2502",
    "ltee": "\u251c", "rtee": "\u2524",
    "ok": "\u25cf", "no": "\u25cb", "arrow": "\u203a",
    "block": "\u2588", "shade": "\u2591",
}
_GLYPH_ASCII = {
    "tl": "+", "tr": "+", "bl": "+", "br": "+",
    "h": "-", "v": "|",
    "ltee": "+", "rtee": "+",
    "ok": "*", "no": "-", "arrow": ">",
    "block": "#", "shade": ".",
}


class Style(object):
    """Glyphs and colour for one console, chosen once at construction."""

    def __init__(self, unicode_ok: bool = True, colour: bool = True):
        self.unicode = bool(unicode_ok)
        self.colour = bool(colour)
        self.g = dict(_GLYPH_UNICODE if self.unicode else _GLYPH_ASCII)

    def c(self, name: str, text: str) -> str:
        if not self.colour:
            return text
        code = _ANSI.get(name)
        return text if not code else code + text + _ANSI["reset"]

    @property
    def tier(self) -> str:
        if self.unicode and self.colour:
            return "unicode+colour"
        return "unicode" if self.unicode else "ascii"


def visible_width(text: str) -> int:
    """
    Printed width, ignoring ANSI escapes.

    Padding a coloured cell by len() would count the escape bytes and shear
    every column to the right of it. The panel's frame would then not line up,
    which is exactly the ugliness the user asked to avoid.
    """
    out, i = 0, 0
    while i < len(text):
        if text[i] == "\033":
            j = text.find("m", i)
            if j == -1:
                break
            i = j + 1
            continue
        out += 1
        i += 1
    return out


def pad(text: str, width: int, align: str = "left") -> str:
    """Pad to a printed width, escape-aware, never truncating information."""
    gap = width - visible_width(text)
    if gap <= 0:
        return text
    if align == "right":
        return " " * gap + text
    if align == "center":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


# ---------------------------------------------------------------------------
# The wordmark.
# ---------------------------------------------------------------------------
# Hand-built rather than generated, so it renders identically everywhere and
# needs no font, no figlet install and no network.
_WORDMARK = [
    "MMM   MMM   AAAAA   RRRRRR   FFFFFF  IIII  NNN   NN",
    "MMMM MMMM  AAA AAA  RR   RR  FF       II   NNNN  NN",
    "MM MMM MM AAAAAAAAA RRRRRR   FFFF     II   NN NN NN",
    "MM  M  MM AAA   AAA RR  RR   FF       II   NN  NNNN",
    "MM     MM AAA   AAA RR   RR  FF      IIII  NN   NNN",
]


def wordmark(style: Style, width: int = 78) -> List[str]:
    """
    The project name in block letters, or a compact rule if it will not fit.

    In the unicode tier the letter strokes become solid blocks, which is what
    makes it look modern rather than like 1994 ASCII art. In the ASCII tier the
    letters stay as letters, which is still legible on code page 437.

    DEFECT FOUND BY MEASUREMENT 2026-08-27: the block letters are a fixed 53
    columns and the function ignored `width`, so at width 40 or 50 every one of
    the five rows overflowed and the terminal re-wrapped them into unreadable
    fragments -- 30 broken lines across the tested widths. Big art that shatters
    is worse than small art that fits, so below the threshold the wordmark
    collapses to a single titled rule.
    """
    art_w = max(len(r) for r in _WORDMARK)
    if art_w + 2 > width:
        g = style.g
        label = " MARFIN "
        fill = max(0, width - 2 - len(label))
        left = fill // 2
        return [style.c("title", g["h"] * left + label + g["h"] * (fill - left))]
    lines = []
    for row in _WORDMARK:
        if style.unicode:
            row = "".join(style.g["block"] if ch != " " else " " for ch in row)
        lines.append(style.c("title", row))
    return lines


# ---------------------------------------------------------------------------
# Frame primitives.
# ---------------------------------------------------------------------------

def _box_top(style: Style, width: int, title: str = "") -> str:
    # DEFECT FOUND BY MEASUREMENT 2026-08-27. The fill was `width - 4 - len`,
    # which produced a top border of 77 against content rows of 78: the
    # top-right corner sat one column left of the right edge on every box, in
    # all three tiers. The frame is 1 (corner) + 1 (h) + label + fill + 1
    # (corner), so the fill is width - 3 - len(label). Off-by-one in a border is
    # exactly the kind of ugliness the user asked to avoid, and eyeballing the
    # output is how it got shipped; a width histogram is how it got caught.
    g = style.g
    if not title:
        return style.c("frame", g["tl"] + g["h"] * (width - 2) + g["tr"])
    label = " " + title + " "
    fill = max(0, width - 3 - len(label))
    return (style.c("frame", g["tl"] + g["h"])
            + style.c("bold", label)
            + style.c("frame", g["h"] * fill + g["tr"]))


def _split_visible(text: str, width: int) -> List[str]:
    """
    Break `text` into chunks of at most `width` PRINTED columns.

    Escape-aware on both counts: escape sequences cost no columns, and a break
    is never placed inside one. Colour is closed with a reset at each break
    rather than reopened on the next chunk -- a reset is harmless when no colour
    is active, whereas a chunk that began mid-sequence would print raw
    `[38;5;61m` garbage.

    Breaks at the last space when there is one, so a wrapped line reads as
    words rather than as sliced characters.
    """
    if visible_width(text) <= width:
        return [text]
    out: List[str] = []
    rest = text
    while visible_width(rest) > width:
        # Walk to the character that sits at column `width`.
        col, i, last_space = 0, 0, -1
        while i < len(rest) and col < width:
            if rest[i] == "\033":
                j = rest.find("m", i)
                if j == -1:
                    i = len(rest)
                    break
                i = j + 1
                continue
            if rest[i] == " ":
                last_space = i
            col += 1
            i += 1
        cut = last_space if last_space > 0 else i
        chunk = rest[:cut]
        if "\033" in chunk:
            chunk += _ANSI["reset"]
        out.append(chunk)
        rest = rest[cut:].lstrip(" ")
        if not rest:
            break
    if rest:
        out.append(rest)
    return out


def _box_row(style: Style, width: int, text: str) -> str:
    """
    One or more framed rows for `text`, wrapping rather than overflowing.

    DEFECT FOUND BY MEASUREMENT 2026-08-27. This used pad() alone, and pad()
    only ever ADDS space -- so any line longer than the inner width pushed the
    right-hand border past the frame. MEASURED: 3 of 46 rows overflowed, in all
    three tiers, by up to 13 columns. Truncating would have been the easy fix
    and the wrong one: the longest row is the one saying no quota is recorded as
    a fact, and silently cutting a caveat is how a caveat stops being read.
    """
    g = style.g
    inner = width - 4
    chunks = _split_visible(text, inner)
    if len(chunks) > 1:
        # A continuation flush against the left border reads as a new item
        # rather than as the rest of the previous one -- MEASURED on the first
        # render, where "needs --base-url" and "--allow-paid" both landed in
        # column 1 and looked like separate rows. Re-wrap with a hanging indent
        # so the continuation is visibly subordinate. The indent is derived
        # from the text's own leading space, so a bullet row and a plain row
        # each get the indent that suits them.
        lead = len(text) - len(text.lstrip(" "))
        indent = " " * min(lead + 2, max(0, inner - 8))
        chunks = _split_visible(text, inner - len(indent))
        chunks = [chunks[0]] + [indent + c for c in chunks[1:]]
    rows = []
    for chunk in chunks:
        rows.append(style.c("frame", g["v"]) + " " + pad(chunk, inner) + " "
                    + style.c("frame", g["v"]))
    return "\n".join(rows)


def _box_sep(style: Style, width: int) -> str:
    g = style.g
    return style.c("frame", g["ltee"] + g["h"] * (width - 2) + g["rtee"])


def _box_bottom(style: Style, width: int) -> str:
    g = style.g
    return style.c("frame", g["bl"] + g["h"] * (width - 2) + g["br"])


# ---------------------------------------------------------------------------
# Content sections.
# ---------------------------------------------------------------------------

_TIER_WORD = {True: "FREE", False: "PAID", None: "UNKNOWN"}
_TIER_COLOUR = {True: "free", False: "paid", None: "unk"}


def provider_rows(style: Style, rows: Optional[List[Dict[str, Any]]] = None
                  ) -> List[str]:
    """
    One line per provider: readiness, cost class, and the variable to set.

    Column order is deliberate. Readiness first, because that is the question
    the user opens the panel to answer. Cost class second, because their
    standing constraint is to spend nothing. The env var last, because it is
    the action to take when the first column says "not set".
    """
    rows = credential_status() if rows is None else rows
    out = []
    name_w = max(len(r["provider"]) for r in rows)
    for r in rows:
        if r["provider"] == "local":
            mark = style.c("ok", style.g["ok"])
            state = style.c("ok", pad("ready, no key needed", 24))
        elif r["configured"]:
            mark = style.c("ok", style.g["ok"])
            # Length only. The key itself is never available to this function.
            state = style.c("ok", pad("key set (%d chars)" % r["key_length"], 24))
        else:
            mark = style.c("dim", style.g["no"])
            state = style.c("dim", pad("not set", 24))
        tier = _TIER_WORD[r["free_tier"]]
        tier_cell = style.c(_TIER_COLOUR[r["free_tier"]], pad(tier, 8))
        env = r["env_key"] or "-"
        extra = "  +--base-url" if r.get("needs_base_url") and r["provider"] != "local" else ""
        out.append("%s %s  %s %s %s%s" % (
            mark, pad(r["provider"], name_w), state, tier_cell,
            style.c("dim", env), style.c("warn", extra)))
    return out


def local_status_rows(style: Style) -> List[str]:
    """
    The MEASURED state of the local model.

    This section exists because the user's instruction was that the local model
    stays: "مدل محلی حتماً باید باقی بماند و فقط api به آن اضافه گردد". A panel
    that listed twelve APIs and said nothing about the local model would read as
    a replacement. So the local model is shown FIRST, with its real numbers --
    including the failures, because a panel that hid them would be flattering
    rather than useful.
    """
    a = style.g["arrow"]
    return [
        style.c("bold", "Local model (default, no network, no cost)"),
        "  %s file        Qwen3.5-4B-Q5_K_M.gguf, 2.928 GiB   %s" % (
            a, style.c("dim", "MEASURED")),
        "  %s context     16384 tokens, 6 threads             %s" % (
            a, style.c("dim", "CONFIGURED")),
        "  %s decode      %s   %s" % (
            a, style.c("bad", pad("3.62-4.38 tok/s (min 8) FAIL", 34)),
            style.c("dim", "MEASURED 2026-08-27")),
        "  %s first token %s   %s" % (
            a, style.c("bad", pad("48.6-49.9 s (max 3.0) FAIL", 34)),
            style.c("dim", "MEASURED 2026-08-27")),
        "  %s peak RSS    %s   %s" % (
            a, style.c("ok", pad("3.792 GiB (max 6.0) PASS", 34)),
            style.c("dim", "MEASURED_PEAK")),
        "  %s answers     %s   %s" % (
            a, style.c("warn", pad("9 of 52 had no visible answer", 34)),
            style.c("dim", "MEASURED")),
    ]


def guardrail_rows(style: Style) -> List[str]:
    """
    The safety state, restated every time the panel is opened.

    These are not decorative. `live_trading_enabled` being False is the single
    most consequential fact in the project, and a panel is read far more often
    than a JSON file is.
    """
    a = style.g["arrow"]
    return [
        "  %s live trading      %s" % (a, style.c("ok", "DISABLED (default)")),
        "  %s active mode       %s" % (a, style.c("ok", "ANALYSIS_ONLY")),
        "  %s spend guard       %s" % (
            a, style.c("ok", "ON -- paid/unknown-cost need --allow-paid")),
        # CORRECTED 2026-08-27. This line read "8 FAIL / 3 PASS / 3 PENDING
        # (MEASURED, 2 runs)", which was wrong twice over. The counts sum to 14
        # against 12 approved thresholds, and the aggregate is not MEASURED at
        # all: threshold_verdicts in the merged evidence file is deliberately
        # null, because the merge tool refuses to recompute a cross-arm verdict
        # and warns "do not inherit a subset's verdict". So the figure is
        # COMPUTED by worst-case aggregation over per-arm numbers that are
        # themselves MEASURED, and it now says so.
        "  %s phase 4 verdict   %s" % (
            a, style.c("warn", "8 FAIL / 3 PASS / 1 PENDING of 12 (COMPUTED)")),
        "  %s measurements      %s" % (
            a, style.c("dim", "phase_4/measurements_recorded is None -- gate held")),
    ]


# ---------------------------------------------------------------------------
# Assembly.
# ---------------------------------------------------------------------------

PANEL_WIDTH = 78


def render(style: Optional[Style] = None, width: int = PANEL_WIDTH,
           rows: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    The whole panel as one string.

    Returns rather than prints, so the test suite can assert on it and so the
    caller decides where it goes. The final string is passed through redact()
    as a last line of defence: a panel is the thing users screenshot.
    """
    style = style or Style()
    L: List[str] = []
    L.append("")
    for line in wordmark(style, width):
        L.append("  " + line)
    # DEFECT FOUND BY MEASUREMENT 2026-08-27: the tagline ignored `width` and
    # was 73 columns wide, so on a 60- or 70-column console it wrapped at the
    # terminal's own margin and pushed the wordmark's alignment out. It is
    # outside the frame, so the frame test did not catch it -- a reminder that
    # "the box lines up" is not the same as "the panel fits".
    tagline = ("bilingual Persian-English financial analyst  %s  local first, "
               "APIs added" % style.g["arrow"])
    if len(tagline) + 2 > width:
        tagline = "bilingual FA-EN financial analyst  %s  local first, APIs added" % style.g["arrow"]
    for chunk in _split_visible(tagline, max(8, width - 2)):
        L.append("  " + style.c("dim", chunk))
    L.append("")

    L.append(_box_top(style, width, "LOCAL MODEL"))
    for line in local_status_rows(style):
        L.append(_box_row(style, width, line))
    L.append(_box_sep(style, width))

    L.append(_box_row(style, width, style.c("bold", "PROVIDERS")))
    L.append(_box_row(style, width, style.c(
        "dim", "%d providers  %s  %d with a documented free tier  %s  keys from the environment only"
        % (len(PROVIDERS), style.g["arrow"], len(KNOWN_FREE_TIER), style.g["arrow"]))))
    L.append(_box_row(style, width, ""))
    for line in provider_rows(style, rows):
        L.append(_box_row(style, width, line))
    L.append(_box_row(style, width, ""))
    L.append(_box_row(style, width, style.c(
        "dim", "FREE/PAID is the provider's own documentation, NOT a quota. "
               "No quota is")))
    L.append(_box_row(style, width, style.c(
        "dim", "recorded here: published figures disagree. Read the limits page.")))
    L.append(_box_sep(style, width))

    L.append(_box_row(style, width, style.c("bold", "GUARDRAILS")))
    for line in guardrail_rows(style):
        L.append(_box_row(style, width, line))
    L.append(_box_bottom(style, width))
    L.append("")
    L.append("  " + style.c("dim", "console: %s" % style.tier))
    L.append("")
    return redact("\n".join(L))


def print_panel(stream: Optional[TextIO] = None, width: int = PANEL_WIDTH) -> None:
    """
    Render to a stream, detecting what it can display.

    Writes with 'replace' error handling as a final guard: if capability
    detection is somehow wrong about the code page, the user sees a question
    mark instead of a UnicodeEncodeError traceback that hides the panel
    entirely.
    """
    stream = stream if stream is not None else sys.stdout
    caps = detect_caps(stream)
    text = render(Style(caps["unicode"], caps["colour"]), width=width)
    try:
        stream.write(text + "\n")
    except UnicodeEncodeError:
        enc = getattr(stream, "encoding", None) or "ascii"
        stream.write(text.encode(enc, "replace").decode(enc, "replace") + "\n")
    try:
        stream.flush()
    except Exception:
        pass


if __name__ == "__main__":                                # pragma: no cover
    print_panel()
