"""
An INTERACTIVE console for the project panel.

WHY THIS EXISTS
---------------
`python scripts/panel.py` drew the panel and exited. The user's report, verbatim
(request 40):

    "پنلی که نوشته ای با دستور python panel.py فقط اجرا میشود و سپس بسته میشود
     و دستوری را نمی گیرد و اجرا نمی کند . پنل نباید اینطور باشد و باید لیستی
     از دستور مثل انتخاب نوع استفاده از هوش مصنوعی مثل api ها و local ها و
     دیگری مسائل را در بر بگیرد"

That is correct and it was a real design gap: a "panel" that cannot be talked to
is a banner. This module adds a menu loop -- pick an engine, inspect a provider,
read the guardrails -- while keeping every existing guarantee.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-----------------------------------------
It NEVER launches a Phase 4 run, and it never opens a network connection. The
project's standing rule is that no run starts without the user's explicit
approval, and a menu that could start one by mis-keying a digit would break it.
Choosing an engine therefore PRINTS the exact command and stops; the user runs
it themselves, having read it. This is a menu over *reads*, not a remote
control.

It also never prints key material. Everything it shows about credentials comes
from `credential_status()`, which reports presence and length only, and the
final text still passes through `redact()`.

DESIGN FOR TESTABILITY
----------------------
`dispatch()` is pure with respect to the terminal: it takes a command string and
a State, and returns (text, State, quit_flag). The loop that calls `input()` is
a thin shell around it. A menu whose logic only exists inside a `while True:`
reading stdin cannot be tested, and untested branches in this project have
already shipped wrong output once.

WINDOWS CMD
-----------
No curses, no termios, no ANSI cursor addressing -- `input()` and printing only,
because those are the parts of a console CMD is guaranteed to have. Colour and
box-drawing are already negotiated by `detect_caps()`; this module inherits that
decision rather than making a second one.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, TextIO, Tuple

from .providers import (PROVIDERS, ProviderError, credential_status,
                        get_provider, provider_names, redact, resolve_base_url)
from . import panel as _panel


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class State(object):
    """
    What the console remembers between commands.

    `engine` is the provider the user has SELECTED, which is not the same thing
    as a provider that is running: nothing runs from here. It defaults to
    `local` because the project's default engine is local and a menu that
    silently defaulted to a paid remote would be a trap.
    """

    __slots__ = ("engine", "width", "ascii_only", "no_colour", "allow_paid")

    def __init__(self, engine: str = "local", width: int = 78,
                 ascii_only: bool = False, no_colour: bool = False,
                 allow_paid: bool = False) -> None:
        self.engine = engine
        self.width = width
        self.ascii_only = ascii_only
        self.no_colour = no_colour
        self.allow_paid = allow_paid

    def style(self) -> "_panel.Style":
        caps = _panel.detect_caps(sys.stdout)
        return _panel.Style(
            unicode_ok=False if self.ascii_only else caps["unicode"],
            colour=False if self.no_colour else caps["colour"])

    def copy(self) -> "State":
        return State(self.engine, self.width, self.ascii_only,
                     self.no_colour, self.allow_paid)


# ---------------------------------------------------------------------------
# The menu
# ---------------------------------------------------------------------------
# Every entry is (key, aliases, title). `key` is what the menu prints; aliases
# let the user type a word instead of a digit, because remembering that "4" is
# guardrails is a worse interface than typing "guardrails".
MENU: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    ("1", ("panel", "p"), "Draw the full panel"),
    ("2", ("engine", "use", "e"), "Choose the engine: local model or an API provider"),
    ("3", ("providers", "list", "l"), "List every provider, with cost class and key state"),
    ("4", ("check", "c"), "Inspect ONE provider in full, and whether it is usable now"),
    ("5", ("keys", "k"), "Which API keys are set (lengths only, never values)"),
    ("6", ("local", "model", "m"), "Local model: the MEASURED numbers"),
    ("7", ("guardrails", "g"), "Guardrails, thresholds and the Phase 4 verdict"),
    ("8", ("run", "cmd"), "Print the exact run command for the selected engine"),
    ("9", ("setup", "s"), "How to set a key on Windows (set / setx)"),
    ("10", ("display", "d"), "Display: width, ASCII tier, colour"),
    ("11", ("json", "j"), "Machine-readable status as JSON"),
    ("0", ("quit", "q", "exit"), "Quit"),
)

_ALIAS: Dict[str, str] = {}
for _k, _aliases, _ in MENU:
    _ALIAS[_k] = _k
    for _a in _aliases:
        _ALIAS[_a] = _k


def normalise(raw: str) -> Optional[str]:
    """
    Map what the user typed onto a menu key, or None if it means nothing.

    Case and surrounding space are ignored. An empty line is NOT an error and
    NOT a command -- it redraws the menu, which is what pressing Enter at a
    prompt should do.
    """
    token = (raw or "").strip().lower()
    if not token:
        return "menu"
    # "engine groq" and "check openai" carry an argument; the verb decides.
    verb = token.split()[0]
    return _ALIAS.get(verb)


def argument_of(raw: str) -> str:
    """The rest of the line after the verb, stripped. '' when there is none."""
    parts = (raw or "").strip().split(None, 1)
    return parts[1].strip() if len(parts) > 1 else ""


def safe_base_url(name: str) -> Tuple[Optional[str], Optional[str]]:
    """
    The endpoint for `name`, or the reason there isn't one.

    Returns (url, None) on success and (None, reason) on refusal. `local`
    legitimately has no endpoint and yields (None, None) -- an absent URL and a
    refused URL are different facts and the caller must be able to tell them
    apart.

    WHY THIS WRAPPER EXISTS. MEASURED: `resolve_base_url("custom")` RAISES
    ProviderError, by design -- `custom` has no default endpoint because a
    default would send the user's prompt to a host they never named. That is
    correct behaviour in the provider layer and must not change. But the console
    called it bare, so selecting `custom` from the menu propagated the exception
    out of dispatch(). The dedicated suite caught exactly that, at
    tests/test_console.py line 238, on provider 11 of 14.

    Note also that ProviderError subclasses Exception, NOT ValueError (MEASURED:
    MRO is ProviderError -> Exception -> BaseException), so an `except
    ValueError` here would have looked like a guard and caught nothing.
    """
    try:
        return resolve_base_url(name), None
    except ProviderError as exc:
        # The provider layer's message is written for the user; keep its first
        # sentence, which is the actionable part, and drop the rationale.
        reason = str(exc).split(".")[0].strip()
        return None, reason or "no endpoint configured"


# ---------------------------------------------------------------------------
# Views. Each returns a list of lines; none of them touch the network.
# ---------------------------------------------------------------------------
def menu_text(state: State) -> List[str]:
    st = state.style()
    w = state.width
    out = [_panel._box_top(st, w, "PROJECT CONSOLE")]
    out.append(_panel._box_row(
        st, w, "selected engine: %s   %s" % (
            st.c("ok" if state.engine == "local" else "warn", state.engine),
            "(local, no network, no cost)" if state.engine == "local"
            else "(remote API -- your data leaves this machine)")))
    out.append(_panel._box_sep(st, w))
    # The colour tag is "title", not "key". MEASURED: panel._ANSI has no "key"
    # entry, and Style.c() returns the text UNCOLOURED for an unknown tag
    # instead of raising -- so a typo here would silently produce a menu with no
    # highlighting and nothing would ever report it. The real tags are reset,
    # dim, bold, frame, title, ok, warn, bad, free, paid, unk.
    for key, aliases, title in MENU:
        out.append(_panel._box_row(
            st, w, "  %s  %-11s %s" % (st.c("title", "%-3s" % key),
                                       aliases[0], title)))
    out.append(_panel._box_sep(st, w))
    out.append(_panel._box_row(
        st, w, "type a number or a word. nothing here starts a run or opens a"))
    out.append(_panel._box_row(
        st, w, "network connection -- commands are printed for you to run."))
    out.append(_panel._box_bottom(st, w))
    return out


def providers_text(state: State) -> List[str]:
    """
    Every provider, with the two facts that decide whether you can use it:
    is a key present, and is it going to bill you.
    """
    st = state.style()
    rows = {r["provider"]: r for r in credential_status()}
    out = ["", "  PROVIDERS (%d)  --  '*' marks the selected engine" % len(PROVIDERS), ""]
    out.append("  %-1s %-22s %-9s %-9s %s" %
               ("", "provider", "cost", "key", "wire dialect"))
    out.append("  " + "-" * (state.width - 4))
    for name in provider_names():
        spec = PROVIDERS[name]
        row = rows.get(name, {})
        free = spec.get("free_tier")
        cost = {True: "FREE", False: "PAID", None: "UNKNOWN"}[free]
        if spec.get("env_key") is None:
            keystate = "n/a"
        elif row.get("configured"):
            n = row.get("key_length")
            keystate = "set:%d" % n if isinstance(n, int) else "set"
        else:
            keystate = "-"
        mark = "*" if name == state.engine else " "
        colour = "ok" if free is True else ("warn" if free is None else "bad")
        out.append("  %s %-22s %-9s %-9s %s" %
                   (mark, name, st.c(colour, cost), keystate, spec.get("wire")))
    out.append("")
    out.append("  cost is the PROVIDER'S OWN DOCUMENTATION, not a quota. This")
    out.append("  project records no quota as fact: published figures disagree.")
    out.append("  UNKNOWN is treated as billable, so it needs --allow-paid.")
    out.append("")
    return out


def keys_text(state: State) -> List[str]:
    """
    Which environment variables are populated. Lengths only, by construction:
    `credential_status()` has no path to a key's value.
    """
    st = state.style()
    rows = credential_status()
    have = [r for r in rows if r.get("configured") and r.get("env_key")]
    lack = [r for r in rows if not r.get("configured") and r.get("env_key")]
    out = ["", "  API KEYS  --  presence and length only; values are never read here", ""]
    if have:
        out.append("  %s" % st.c("ok", "set:"))
        for r in have:
            n = r.get("key_length")
            out.append("    %-24s %s" % (r["env_key"],
                                         "%d chars" % n if isinstance(n, int) else "set"))
    else:
        out.append("  %s" % st.c("warn", "no API key is set. the local model needs none."))
    out.append("")
    out.append("  %s" % st.c("dim", "not set (%d):" % len(lack)))
    line = "    "
    for r in lack:
        if len(line) + len(r["env_key"]) + 2 > state.width - 2:
            out.append(line)
            line = "    "
        line += r["env_key"] + "  "
    if line.strip():
        out.append(line)
    out.append("")
    out.append("  menu 9 shows how to set one on Windows.")
    out.append("")
    return out


def engine_text(state: State, arg: str) -> Tuple[List[str], State]:
    """
    Select an engine. Returns the new State -- selection is the ONLY thing in
    this console that changes anything, and it changes nothing outside memory.
    """
    st = state.style()
    if not arg:
        out = ["", "  CHOOSE AN ENGINE", ""]
        out.append("  type:  engine <name>      e.g.  engine local")
        out.append("                                  engine google")
        out.append("")
        out.append("  local model")
        out.append("    local                  no network, no key, no cost.")
        out.append("                           MEASURED 3.62-4.38 tok/s, which")
        out.append("                           FAILS the approved speed bar.")
        out.append("")
        out.append("  documented free tier (%s)" % ", ".join(
            n for n in provider_names()
            if PROVIDERS[n].get("free_tier") is True and n != "local"))
        out.append("  everything else needs --allow-paid; see menu 3.")
        out.append("")
        return out, state

    name = arg.split()[0].strip().lower()
    if name not in PROVIDERS:
        near = [n for n in provider_names() if n.startswith(name[:3])]
        out = ["", "  %s no provider called %r." % (st.c("bad", "REFUSED:"), name)]
        if near:
            out.append("  did you mean: %s" % ", ".join(near))
        out.append("  menu 3 lists all %d." % len(PROVIDERS))
        out.append("")
        return out, state

    new = state.copy()
    new.engine = name
    spec = PROVIDERS[name]
    free = spec.get("free_tier")
    out = ["", "  engine selected: %s" % st.c("ok" if name == "local" else "warn", name), ""]
    out.append("  %-14s %s" % ("label", spec.get("label")))
    out.append("  %-14s %s" % ("wire dialect", spec.get("wire")))
    out.append("  %-14s %s" % ("cost class",
                               {True: "FREE TIER DOCUMENTED", False: "PAID",
                                None: "UNKNOWN -> treated as billable"}[free]))
    base, base_err = safe_base_url(name)
    out.append("  %-14s %s" % ("base url", base or (
        st.c("bad", "NONE -- " + base_err) if base_err else "-- none (local) --")))
    if name.startswith("agentrouter"):
        # The one mistake AgentRouter's own FAQ warns about, surfaced at the
        # moment of choosing rather than buried in a note nobody opens.
        out.append("")
        out.append("  %s AgentRouter has TWO base urls and they must not be" %
                   st.c("warn", "note:"))
        out.append("  mixed. this entry is the %s dialect. the other entry is" %
                   spec.get("wire"))
        out.append("  %s. both read AGENTROUTER_API_KEY." %
                   ("agentrouter-anthropic" if name == "agentrouter"
                    else "agentrouter"))
    if free is not True:
        out.append("")
        out.append("  %s this provider is billable as far as this project" %
                   st.c("warn", "warning:"))
        out.append("  knows. a real run refuses without --allow-paid.")
    out.append("")
    out.append("  menu 8 prints the exact command.")
    out.append("")
    return out, new


def run_command_text(state: State) -> List[str]:
    """
    The command the user should type -- printed, never executed.

    Two commands, not one: the run script and the readiness check, because
    checking first is free and a failed run after a model load is not.
    """
    st = state.style()
    name = state.engine
    spec = PROVIDERS[name]
    free = spec.get("free_tier")
    env_key = spec.get("env_key")

    out = ["", "  RUN COMMAND for engine '%s'" % name, ""]
    out.append("  %s" % st.c("dim", "1. check readiness (free, no network call):"))
    out.append("     python scripts\\panel.py --check %s%s" %
               (name, " --allow-paid" if free is not True else ""))
    out.append("")
    if env_key and name != "local":
        out.append("  %s" % st.c("dim", "2. set the key for this window:"))
        out.append("     set %s=your-key-here" % env_key)
        out.append("")
        step = "3"
    else:
        step = "2"
    out.append("  %s" % st.c("dim", "%s. run phase 4:" % step))
    flags = "--provider %s" % name
    if free is not True:
        flags += " --allow-paid"
    if name == "custom":
        flags += " --base-url http://localhost:8080/v1"
    out.append("     python scripts\\run_phase4.py %s" % flags)
    out.append("")
    out.append("  %s nothing above has been executed. the project's rule is" %
               st.c("warn", "note:"))
    out.append("  that no run starts without your explicit approval, so this")
    out.append("  console prints commands and stops.")
    if name != "local":
        out.append("")
        out.append("  %s a remote run cannot settle the hardware thresholds." %
                   st.c("warn", "and:"))
        out.append("  four of them go PENDING and the evidence is labelled")
        out.append("  MEASURED_REMOTE_API, so an API run cannot launder a")
        out.append("  local failure into a pass.")
    out.append("")
    return out


def setup_text(state: State) -> List[str]:
    """Windows key setup. `set` for one window, `setx` to persist."""
    st = state.style()
    name = state.engine
    env_key = PROVIDERS[name].get("env_key") or "GEMINI_API_KEY"
    out = ["", "  SETTING A KEY ON WINDOWS", ""]
    out.append("  this window only (gone when you close cmd):")
    out.append("     set %s=your-key-here" % env_key)
    out.append("")
    out.append("  permanently, for future windows:")
    out.append("     setx %s \"your-key-here\"" % env_key)
    out.append("")
    out.append("  %s setx does NOT affect the window you type it in." %
               st.c("warn", "trap:"))
    out.append("  open a NEW cmd window afterwards, or the panel will still")
    out.append("  say the key is missing and you will think setx failed.")
    out.append("")
    out.append("  %s never paste a key into a file in this repository." %
               st.c("warn", "and:"))
    out.append("  keys are read from the environment only. github's secret")
    out.append("  scanner already blocked one push of this project over a")
    out.append("  FAKE key in a test, which is the system working correctly.")
    out.append("")
    return out


def display_text(state: State, arg: str) -> Tuple[List[str], State]:
    """Change width / ASCII / colour. Refuses a width it cannot draw."""
    st = state.style()
    if not arg:
        out = ["", "  DISPLAY", ""]
        out.append("  current: width=%d ascii=%s colour=%s" %
                   (state.width, state.ascii_only, not state.no_colour))
        out.append("")
        out.append("  display width 100     set the width (20-200)")
        out.append("  display ascii         force the pure-ASCII tier")
        out.append("  display unicode       allow box-drawing again")
        out.append("  display colour        allow colour")
        out.append("  display mono          force colour off")
        out.append("")
        return out, state

    token = arg.split()[0].lower()
    new = state.copy()
    if token in ("ascii",):
        new.ascii_only = True
        msg = "ASCII tier forced"
    elif token in ("unicode", "utf8", "utf-8"):
        new.ascii_only = False
        msg = "box-drawing allowed (still subject to what the console supports)"
    elif token in ("colour", "color"):
        new.no_colour = False
        msg = "colour allowed"
    elif token in ("mono", "nocolour", "nocolor"):
        new.no_colour = True
        msg = "colour off"
    elif token == "width":
        rest = arg.split()[1:]
        if not rest:
            return (["", "  REFUSED: width needs a number, e.g. display width 100", ""],
                    state)
        try:
            n = int(rest[0])
        except ValueError:
            return (["", "  REFUSED: %r is not a number." % rest[0], ""], state)
        if not (20 <= n <= 200):
            return (["", "  REFUSED: width %d is outside 20-200. below 20 nothing"
                     % n, "  readable can be drawn; above 200 is not a console.", ""],
                    state)
        new.width = n
        msg = "width %d" % n
    else:
        try:
            n = int(token)
        except ValueError:
            return (["", "  REFUSED: %r is not a display option." % token, ""], state)
        if not (20 <= n <= 200):
            return (["", "  REFUSED: width %d is outside 20-200." % n, ""], state)
        new.width = n
        msg = "width %d" % n
    return ["", "  %s %s" % (st.c("ok", "ok:"), msg), ""], new


def check_text(state: State, arg: str) -> List[str]:
    """
    One provider in full. Mirrors `--check` but never exits the process, so a
    refusal does not kill the console the user is sitting in.
    """
    st = state.style()
    name = (arg or state.engine).split()[0].strip().lower() if (arg or state.engine) else ""
    try:
        spec = get_provider(name)
    except ProviderError as exc:
        return ["", "  %s %s" % (st.c("bad", "REFUSED:"), exc), ""]

    rows = {r["provider"]: r for r in credential_status()}
    row = rows.get(name, {})
    free = spec.get("free_tier")
    env_key = spec.get("env_key")

    out = ["", "  PROVIDER: %s" % name, ""]
    out.append("  %-16s %s" % ("label", spec.get("label")))
    out.append("  %-16s %s" % ("wire dialect", spec.get("wire")))
    out.append("  %-16s %s" % ("cost class",
                               {True: "FREE TIER DOCUMENTED", False: "PAID",
                                None: "UNKNOWN"}[free]))
    out.append("  %-16s %s" % ("cost note", spec.get("cost") or "-"))
    out.append("  %-16s %s" % ("env variable", env_key or "-- none needed --"))
    if env_key is None:
        keystate = st.c("ok", "no key required")
    elif row.get("configured"):
        n = row.get("key_length")
        keystate = st.c("ok", "set (%d chars)" % n if isinstance(n, int) else "set")
    else:
        keystate = st.c("bad", "NOT SET")
    out.append("  %-16s %s" % ("key state", keystate))
    _base, _base_err = safe_base_url(name)
    out.append("  %-16s %s" % ("base url", _base or (
        st.c("bad", "NONE -- " + _base_err) if _base_err else "-- none --")))
    out.append("  %-16s %s" % ("docs", spec.get("docs") or "-"))
    out.append("  %-16s %s" % ("quota", "UNKNOWN -- not recorded as fact"))
    note = spec.get("note")
    if note:
        out.append("")
        for line in _wrap(note, state.width - 6):
            out.append("  %s" % line)

    # Usable RIGHT NOW is a different question from "exists", and it is the one
    # the user actually has. Answer it explicitly.
    out.append("")
    blockers = []
    if env_key is not None and not row.get("configured"):
        blockers.append("%s is not set" % env_key)
    if row.get("needs_base_url"):
        blockers.append("needs --base-url")
    if free is not True and not state.allow_paid:
        blockers.append("billable, needs --allow-paid")
    if blockers:
        out.append("  %s %s" % (st.c("warn", "not usable right now:"),
                                "; ".join(blockers)))
    else:
        out.append("  %s" % st.c("ok", "usable right now"))
    out.append("")
    return out


def _wrap(text: str, width: int) -> List[str]:
    """Word wrap. Local because the panel's splitter is escape-aware and this
    text carries no escapes; reusing it would be misleading, not shorter."""
    words = str(text).split()
    lines, cur = [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w) if cur else w
    if cur:
        lines.append(cur)
    return lines


def json_text(state: State) -> List[str]:
    import json as _json
    payload = {
        "provider_count": len(PROVIDERS),
        "default_provider": "local",
        "selected_engine": state.engine,
        "providers": credential_status(),
        "quota_recorded": None,
        "note": ("free_tier reflects the provider's own documentation, not a "
                 "measured quota. No quota is recorded as a fact anywhere in "
                 "this project."),
    }
    return ["", _json.dumps(payload, indent=2, ensure_ascii=False), ""]


# ---------------------------------------------------------------------------
# The dispatcher -- pure with respect to the terminal
# ---------------------------------------------------------------------------
def dispatch(raw: str, state: State) -> Tuple[str, State, bool]:
    """
    Run one command.

    Returns (text_to_print, new_state, should_quit). Nothing here reads stdin,
    writes a file, or opens a socket, which is what makes the whole menu
    testable without a terminal.

    The returned text passes through `redact()` as defence in depth. Nothing on
    these paths handles a key's value, so redact() should be a no-op -- and a
    no-op that costs nothing is the right shape for a guard whose whole job is
    to be there on the day someone adds a path that does.
    """
    key = normalise(raw)
    arg = argument_of(raw)
    st = state.style()

    if key is None:
        verb = (raw or "").strip().split()[0] if (raw or "").strip() else ""
        lines = ["", "  %s %r is not a command. press Enter for the menu." %
                 (st.c("bad", "?"), verb[:32]), ""]
        return _finish(lines, state, False)

    if key == "0":
        return _finish(["", "  bye. the local model is still your default.", ""],
                       state, True)
    if key == "menu":
        return _finish(menu_text(state), state, False)
    if key == "1":
        return _finish(_panel.render(st, width=state.width).split("\n"),
                       state, False)
    if key == "2":
        lines, new = engine_text(state, arg)
        return _finish(lines, new, False)
    if key == "3":
        return _finish(providers_text(state), state, False)
    if key == "4":
        return _finish(check_text(state, arg), state, False)
    if key == "5":
        return _finish(keys_text(state), state, False)
    if key == "6":
        return _finish([""] + _panel.local_status_rows(st) + [""], state, False)
    if key == "7":
        return _finish([""] + _panel.guardrail_rows(st) + [""], state, False)
    if key == "8":
        return _finish(run_command_text(state), state, False)
    if key == "9":
        return _finish(setup_text(state), state, False)
    if key == "10":
        lines, new = display_text(state, arg)
        return _finish(lines, new, False)
    if key == "11":
        return _finish(json_text(state), state, False)

    # Unreachable while MENU and the branches above agree. If it is ever
    # reached, say so plainly instead of returning empty text that would look
    # like a command that did nothing.
    return _finish(["", "  INTERNAL: menu key %r has no handler." % key, ""],
                   state, False)


def _finish(lines: List[str], state: State, quit_flag: bool
            ) -> Tuple[str, State, bool]:
    return redact("\n".join(lines)), state, quit_flag


# ---------------------------------------------------------------------------
# The loop -- the only part that touches stdin
# ---------------------------------------------------------------------------
PROMPT = "marfin> "


def loop(state: Optional[State] = None,
         stdin: Optional[TextIO] = None,
         stdout: Optional[TextIO] = None,
         banner: bool = True) -> int:
    """
    Read commands until the user quits.

    REFUSES to start when stdin is not interactive. A menu loop reading a
    closed or piped stdin gets EOF on the first read; treating that as "quit"
    is fine, but printing a banner and a prompt first is noise in a pipeline,
    and an earlier draft of this function span on EOF because the read was
    inside a bare `while True`. `--once` exists for non-interactive use.
    """
    state = state or State()
    fin = stdin or sys.stdin
    fout = stdout or sys.stdout

    if banner:
        _write(fout, _panel.render(state.style(), width=state.width))
        _write(fout, "")
        _write(fout, redact("\n".join(menu_text(state))))

    while True:
        _write(fout, "")
        try:
            fout.write(PROMPT)
            fout.flush()
        except Exception:
            pass
        try:
            raw = fin.readline()
        except KeyboardInterrupt:
            _write(fout, "")
            _write(fout, "  interrupted. bye.")
            return 0
        if raw == "":                      # EOF: Ctrl+Z on Windows, Ctrl+D else
            _write(fout, "")
            _write(fout, "  end of input. bye.")
            return 0
        try:
            text, state, done = dispatch(raw.rstrip("\r\n"), state)
        except KeyboardInterrupt:
            _write(fout, "")
            _write(fout, "  interrupted. bye.")
            return 0
        except Exception as exc:           # never let one bad view kill the loop
            text = ("\n  INTERNAL ERROR in that command: %s: %s\n"
                    "  the console is still running; the rest of the menu is "
                    "unaffected.\n" % (type(exc).__name__, redact(str(exc))))
            done = False
        _write(fout, text)
        if done:
            return 0


def _write(stream: TextIO, text: str) -> None:
    """
    Write, surviving a console that cannot encode what we drew.

    A legacy Windows code page raises UnicodeEncodeError on box-drawing
    characters. Losing the whole console to that would be absurd, so replace
    the offending characters rather than the program.
    """
    try:
        stream.write(text + "\n")
    except UnicodeEncodeError:
        enc = getattr(stream, "encoding", None) or "ascii"
        stream.write(text.encode(enc, "replace").decode(enc, "replace") + "\n")
    try:
        stream.flush()
    except Exception:
        pass
