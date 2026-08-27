#!/usr/bin/env python3
"""
Assertions for the INTERACTIVE console (src/llm/console.py).

Why this file is separate from test_llm_providers.py: that suite tests a set of
pure functions over a registry. This one tests a state machine, and the two
failure modes are different. A menu's characteristic bug is not a wrong number,
it is a command that silently does nothing, or a refusal that changes state
anyway, or a loop that will not exit.

WHAT IS PINNED HERE, AND WHY EACH ONE EARNS ITS PLACE
-----------------------------------------------------
1. Every advertised command is REACHABLE and produces output. A menu entry that
   dispatches to nothing is the exact defect the user reported in the previous
   design ("دستوری را نمی گیرد و اجرا نمی کند"), so it is checked per entry
   rather than in aggregate.
2. A REFUSAL DOES NOT MUTATE STATE. `display width 5` must refuse AND leave the
   width alone. Half-applied refusals are how a console ends up in a state its
   own menu cannot describe.
3. NOTHING STARTS A RUN. The project rule is that no run begins without explicit
   approval. `dispatch()` is checked to contain no subprocess/exec/socket path,
   by AST, not by reading it and hoping.
4. NO KEY MATERIAL, ever, from any command -- with a non-vacuity proof that the
   leak test can actually fail.
5. THE LOOP TERMINATES. On quit, on EOF, and after a staged exception. Each is
   run under SIGALRM so a hang FAILS instead of freezing the sandbox (the
   project has frozen it twice before; that is a standing constraint).

Run:  python3 tests/test_console.py
"""
from __future__ import annotations

import ast
import io
import os
import signal
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from _harness import check, check_true, check_raises, section, summary  # noqa: E402

from llm import console as K                                            # noqa: E402
from llm import panel as P                                              # noqa: E402
from llm import providers as PR                                         # noqa: E402


# ---------------------------------------------------------------------------
# Fake keys. Same discipline as the provider suite: assembled, prefixed, and
# never a realistic opaque run, so GitHub's secret scanner has nothing to flag.
# ---------------------------------------------------------------------------
FAKE = "sk-con-" + "0123456789abcdef" + "0123456789abcdef"
_WATCHED = ("AGENTROUTER_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY",
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
_SAVED = {k: os.environ.get(k) for k in _WATCHED}


def set_fake_keys():
    for k in _WATCHED:
        os.environ[k] = FAKE


def restore_keys():
    """The sandbox exports a REAL OPENAI_API_KEY; clobbering it would corrupt
    the process this suite runs in."""
    for k, v in _SAVED.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def check_is(name, got, want, method=""):
    """
    Exact equality for NON-NUMERIC values.

    Why this exists locally instead of in _harness.py: the shared `check()` is
    numeric -- it calls float(got) and then `abs(got - want)`. Handed the string
    "3" it does not report a mismatch, it dies with

        TypeError: unsupported operand type(s) for -: 'float' and 'str'

    MEASURED: that is exactly what the first run of this suite did, at line 132.
    The existing project pattern for a string is `check_true(got == want, ...)`,
    which passes and fails correctly but prints only "condition false" -- so on
    the day it breaks you learn that something is wrong and nothing about what.
    This wrapper keeps the shared harness untouched (17 other suites depend on
    it) while still naming the actual value in the failure line.
    """
    if got == want and type(got) is type(want):
        check_true(name, True, method)
    else:
        # Routed through check_true so the pass/fail counters stay authoritative
        # and this helper cannot invent a tally of its own.
        check_true("%s -- got %r want %r" % (name, got, want), False, method)


def run_loop(script, state=None, banner=False, limit=10):
    """
    Drive the loop with canned stdin under a hard alarm.

    The alarm is the point. A menu loop that fails to terminate would otherwise
    hang the test run, and a hung run in this sandbox has historically needed a
    reset. TimeoutError propagates and the assertion fails, which is correct.
    """
    def _boom(*_a):
        raise TimeoutError("the loop did not terminate")
    old = signal.signal(signal.SIGALRM, _boom)
    signal.alarm(limit)
    try:
        out = io.StringIO()
        rc = K.loop(state or K.State(), stdin=io.StringIO(script),
                    stdout=out, banner=banner)
        return rc, out.getvalue()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


# ===========================================================================
section("menu integrity")
# ===========================================================================

check("menu entries", len(K.MENU), 12, method="(C) census, 11 actions + quit")

_keys = [k for k, _, _ in K.MENU]
check_true("menu keys are unique", len(_keys) == len(set(_keys)),
           "(C) a duplicate key makes one entry unreachable")

_all_aliases = []
for _k, _a, _ in K.MENU:
    _all_aliases.extend(_a)
check_true("aliases are unique across the whole menu (%d)" % len(_all_aliases),
           len(_all_aliases) == len(set(_all_aliases)),
           "(C) a shared alias silently routes to whichever came first")

check_true("no alias collides with a menu key",
           not (set(_all_aliases) & set(_keys)),
           "(C) 'l' must not also mean menu entry l")

check_true("every entry has a non-empty title",
           all(t.strip() for _, _, t in K.MENU),
           "(C) a blank title is an invisible command")

# Non-vacuity: the alias table must actually be populated, or the uniqueness
# checks above would pass over an empty set and prove nothing.
check_true("the alias table is populated (%d entries)" % len(K._ALIAS),
           len(K._ALIAS) >= len(K.MENU) * 2,
           "(C) guards the uniqueness assertions against an empty sample")


# ===========================================================================
section("normalise: what the user typed -> a menu key")
# ===========================================================================

check_is("a digit maps to itself", K.normalise("3"), "3", method="(D)")
check_is("a word maps to its key", K.normalise("providers"), "3", method="(D)")
check_is("case is ignored", K.normalise("PROVIDERS"), "3", method="(D)")
check_is("surrounding space is ignored", K.normalise("  3  "), "3", method="(D)")
check_is("empty means redraw the menu", K.normalise(""), "menu", method="(D)")
check_is("whitespace only means redraw", K.normalise("   \t "), "menu",
      method="(D)")
check_true("nonsense maps to nothing", K.normalise("zzz") is None, "(D)")
check_is("a verb with an argument maps on the verb",
      K.normalise("engine google"), "2", method="(D)")
check_is("argument_of returns the rest", K.argument_of("engine google"),
      "google", method="(D)")
check_is("argument_of is empty when there is none", K.argument_of("engine"),
      "", method="(D)")
check_is("argument_of keeps multi-word arguments",
      K.argument_of("display width 100"), "width 100", method="(D)")


# ===========================================================================
section("every advertised command is reachable and produces output")
# ===========================================================================

# The defect the user reported was a panel that "does not take a command and
# does not run it". So each menu entry is dispatched INDIVIDUALLY, and the bar
# is not "no exception" but "produced real text".
_dead = []
_thin = []
for _k, _aliases, _title in K.MENU:
    for _token in (_k,) + _aliases:
        try:
            _txt, _st, _done = K.dispatch(_token, K.State())
        except Exception as _exc:                              # noqa: BLE001
            _dead.append((_token, type(_exc).__name__))
            continue
        if _k == "0":
            continue                       # quit is allowed to be terse
        if len(_txt.strip()) < 20:
            _thin.append((_token, len(_txt.strip())))
check_true("no advertised command raises (%s)" % (_dead[:3] or "none"),
           not _dead, "(C) every key and alias, dispatched individually")
check_true("no advertised command returns empty text (%s)" % (_thin[:3] or "none"),
           not _thin,
           "(C) the reported defect was a command that does nothing")

check_true("an unknown command is refused, not ignored",
           "not a command" in K.dispatch("zzz", K.State())[0],
           "(C) silence would look like a command that ran")

check_true("quit reports quit", K.dispatch("0", K.State())[2] is True, "(D)")
check_true("every other command does NOT report quit",
           not any(K.dispatch(k, K.State())[2]
                   for k, _, _ in K.MENU if k != "0"),
           "(C) an accidental quit flag would close the console mid-session")


# ===========================================================================
section("engine selection")
# ===========================================================================

check_is("the default engine is local", K.State().engine, "local",
      method="(C) the project default; a remote default would be a trap")

_txt, _st, _ = K.dispatch("engine google", K.State())
check_is("selecting a provider selects it", _st.engine, "google", method="(D)")

_txt, _st2, _ = K.dispatch("engine nosuchprovider", K.State())
check_is("an unknown engine leaves the selection alone", _st2.engine, "local",
      method="(C) a refusal must not half-apply")
check_true("an unknown engine is refused in words",
           "no provider called" in _txt, "(C)")

_txt, _st3, _ = K.dispatch("engine", K.State())
check_is("bare 'engine' does not change the engine", _st3.engine, "local",
      method="(C) listing the options is not choosing one")
check_true("bare 'engine' lists the options",
           "CHOOSE AN ENGINE" in _txt, "(C)")

# Every provider in the registry must be selectable. A menu that can list a
# provider but not select it is worse than not listing it.
_unselectable = []
for _name in PR.provider_names():
    _t, _s, _ = K.dispatch("engine " + _name, K.State())
    if _s.engine != _name:
        _unselectable.append(_name)
check_true("every registered provider is selectable (%s)"
           % (_unselectable or "all %d ok" % len(PR.PROVIDERS)),
           not _unselectable, "(C) list and select must agree")

# The billable warning must track the tri-state, not the provider's name.
_missing_warning = []
for _name in PR.provider_names():
    _t, _, _ = K.dispatch("engine " + _name, K.State())
    _free = PR.PROVIDERS[_name].get("free_tier") is True
    _warned = "--allow-paid" in _t
    if _free and _warned:
        _missing_warning.append((_name, "warned about a FREE provider"))
    if not _free and not _warned:
        _missing_warning.append((_name, "no warning on a BILLABLE provider"))
check_true("the billable warning tracks free_tier exactly (%s)"
           % (_missing_warning[:2] or "none"),
           not _missing_warning,
           "(C) UNKNOWN counts as billable; being wrong here costs money")


# ===========================================================================
section("AgentRouter: the two-base-url trap its own FAQ warns about")
# ===========================================================================

check_true("both AgentRouter entries exist",
           "agentrouter" in PR.PROVIDERS
           and "agentrouter-anthropic" in PR.PROVIDERS, "(C)")

check_is("the OpenAI dialect keeps /v1",
      PR.PROVIDERS["agentrouter"]["base_url"],
      "https://co.agentrouter.org/v1",
      method="(V) portal FAQ: '/v1 required'")
check_is("the Anthropic dialect has NO /v1",
      PR.PROVIDERS["agentrouter-anthropic"]["base_url"],
      "https://co.agentrouter.org",
      method="(V) portal FAQ: 'no /v1' -- appending it 404s")
check_true("the two base urls actually differ",
           PR.PROVIDERS["agentrouter"]["base_url"]
           != PR.PROVIDERS["agentrouter-anthropic"]["base_url"],
           "(C) if they were equal, one entry would be pointless")

check_true("neither AgentRouter entry claims a free tier",
           PR.PROVIDERS["agentrouter"]["free_tier"] is None
           and PR.PROVIDERS["agentrouter-anthropic"]["free_tier"] is None,
           "(C) sign-up credit advertised on affiliate pages is not a free "
           "tier, and the portal publishes no quota")
check_true("AgentRouter is absent from KNOWN_FREE_TIER",
           not any(n.startswith("agentrouter") for n in PR.KNOWN_FREE_TIER),
           "(C) a false free claim would defeat the spend gate")

for _n in ("agentrouter", "agentrouter-anthropic"):
    _t, _, _ = K.dispatch("engine " + _n, K.State())
    check_true("selecting %s warns about the two base urls" % _n,
               "TWO base urls" in _t,
               "(C) surfaced at the moment of choosing, not buried in a note")
    _other = ("agentrouter-anthropic" if _n == "agentrouter" else "agentrouter")
    check_true("selecting %s names the other entry" % _n, _other in _t,
               "(C) the user needs to know where the other dialect lives")
    check_true("selecting %s names the shared env var" % _n,
               "AGENTROUTER_API_KEY" in _t,
               "(C) one key meters both, per the portal")


# ===========================================================================
section("display options refuse without half-applying")
# ===========================================================================

_base = K.State()
check("a valid width is applied",
      K.dispatch("display width 100", _base)[1].width, 100, method="(D)")

for _cmd in ("display width 5", "display width 999", "display width abc",
             "display width", "display bogus"):
    _t, _s, _ = K.dispatch(_cmd, _base)
    check("%r leaves the width at %d" % (_cmd, _base.width),
          _s.width, _base.width,
          method="(C) a refusal must not change anything")
    check_true("%r says why" % _cmd, "REFUSED" in _t, "(C) actionable")

check_true("display ascii sets the ascii tier",
           K.dispatch("display ascii", _base)[1].ascii_only is True, "(D)")
check_true("display unicode clears it",
           K.dispatch("display unicode",
                      K.State(ascii_only=True))[1].ascii_only is False, "(D)")
check_true("display mono turns colour off",
           K.dispatch("display mono", _base)[1].no_colour is True, "(D)")
check_true("display colour turns it back on",
           K.dispatch("display colour",
                      K.State(no_colour=True))[1].no_colour is False, "(D)")

# The State the console hands back must never be the same object it was given,
# or a refusal could mutate the caller's state through an alias.
_st_in = K.State()
_t, _st_out, _ = K.dispatch("display width 100", _st_in)
check_true("a state change returns a NEW State object",
           _st_out is not _st_in,
           "(C) mutating in place would make refusals unrecoverable")
check("the original state is untouched", _st_in.width, 78,
      method="(C) proves the copy is real, not just a different name")


# ===========================================================================
section("nothing in the console starts a run or opens a socket")
# ===========================================================================

# By AST, not by reading the file and trusting my own summary of it. The rule
# it enforces: no run may start without the user's explicit approval, so a menu
# that could launch one by mis-keying a digit is a defect regardless of intent.
_src = io.open(os.path.join(os.path.dirname(__file__), "..", "src", "llm",
                            "console.py"), encoding="utf-8").read()
_tree = ast.parse(_src)
_FORBIDDEN = ("subprocess", "socket", "urllib", "http", "requests", "shutil",
              "multiprocessing", "asyncio", "ctypes")
_imported = set()
for _node in ast.walk(_tree):
    if isinstance(_node, ast.Import):
        for _a in _node.names:
            _imported.add(_a.name.split(".")[0])
    elif isinstance(_node, ast.ImportFrom) and _node.module:
        _imported.add(_node.module.split(".")[0])
_bad_imports = sorted(_imported & set(_FORBIDDEN))
check_true("the console imports nothing that can run or connect (%s)"
           % (_bad_imports or "clean; imports: %s" % sorted(_imported)),
           not _bad_imports,
           "(C) AST, not a reading of the source")

_CALLS = ("system", "popen", "spawn", "execv", "execve", "fork", "urlopen",
          "Popen", "run", "call", "check_output")
_bad_calls = []
for _node in ast.walk(_tree):
    if isinstance(_node, ast.Call):
        _f = _node.func
        _name = getattr(_f, "attr", None) or getattr(_f, "id", None)
        if _name in ("system", "popen", "execv", "execve", "fork", "urlopen",
                     "Popen", "check_output", "spawnv"):
            _bad_calls.append(_name)
check_true("the console makes no exec/connect call (%s)"
           % (sorted(set(_bad_calls)) or "none"),
           not _bad_calls, "(C) AST over every Call node")

# Non-vacuity: prove the AST walk is actually looking at something.
check_true("the AST walk saw a non-trivial module (%d nodes)"
           % sum(1 for _ in ast.walk(_tree)),
           sum(1 for _ in ast.walk(_tree)) > 500,
           "(C) an empty parse would pass both checks above vacuously")

# The run-command view must PRINT a command, and must say it did not run it.
_t, _, _ = K.dispatch("8", K.State())
check_true("the run view prints a run_phase4 command",
           "run_phase4.py" in _t, "(C) the user needs the exact command")
check_true("the run view says nothing was executed",
           "has been executed" in _t or "not been executed" in _t
           or "prints commands" in _t,
           "(C) an ambiguous view invites the user to assume it ran")
check_true("the run view restates the approval rule",
           "explicit approval" in _t, "(C) the standing project constraint")

# A remote engine must not be allowed to look like it settles the hardware bar.
_t_remote, _, _ = K.dispatch("8", K.State(engine="google"))
check_true("a remote engine's run view warns it cannot settle the thresholds",
           "PENDING" in _t_remote and "MEASURED_REMOTE_API" in _t_remote,
           "(C) an API run must not launder a local hardware failure")
_t_local, _, _ = K.dispatch("8", K.State(engine="local"))
check_true("the local run view carries no such warning",
           "MEASURED_REMOTE_API" not in _t_local,
           "(C) non-vacuity: proves the warning is conditional, not boilerplate")


# ===========================================================================
section("no command leaks key material")
# ===========================================================================

set_fake_keys()

_COMMANDS = [""] + [k for k, _, _ in K.MENU] + [
    "engine google", "engine agentrouter", "engine agentrouter-anthropic",
    "engine openai", "check google", "check agentrouter", "check openai",
    "check local", "keys", "json", "display width 100", "zzz"]

_leaked = []
_frag = []
_st = K.State()
for _cmd in _COMMANDS:
    _txt, _st, _ = K.dispatch(_cmd, _st)
    if FAKE in _txt:
        _leaked.append(_cmd)
    elif FAKE[:14] in _txt or FAKE[-14:] in _txt:
        _frag.append(_cmd)
check_true("no command prints a key (%s)" % (_leaked or "none"), not _leaked,
           "(C) %d commands, with 5 keys set" % len(_COMMANDS))
check_true("no command prints a 14-char key fragment (%s)" % (_frag or "none"),
           not _frag, "(C) a prefix is enough to confirm a guess")

# NON-VACUITY. If redact() were removed, would anything be caught? The console's
# views legitimately never handle a key's value, so the honest proof is that
# redact() -- the guard dispatch() ends with -- does scrub, and that dispatch()
# really routes through it.
_real_redact = K.redact
try:
    K.redact = lambda text, *keys: text
    _t_unguarded, _, _ = K.dispatch("5", K.State())
    _guard_reached = True
finally:
    K.redact = _real_redact
check_true("redact was restored after the probe", K.redact is _real_redact,
           "(C) a leaked monkeypatch would silently disarm every later check")
check_true("dispatch routes its output through redact",
           "redact(" in _src and "_finish" in _src,
           "(C) defence in depth: nothing reaches it today, by design")

# BEHAVIOURAL proof that dispatch really calls redact, not merely that the
# source mentions it. MEASURED: the mutation battery seeded "dispatch output no
# longer passes through redact" and it SURVIVED, because the assertion above
# reads the source text and the mutant left the word "redact" elsewhere in the
# file. A source-text check cannot distinguish "calls it" from "mentions it".
#
# So: stage a key into a view's own output and require dispatch to scrub it.
# `providers_text` is patched to emit a key-shaped string; if dispatch pipes its
# lines through redact, the marker cannot reach the caller.
_STAGED = "sk-staged-" + "0123456789abcdef" + "0123456789abcdef"
_orig_providers_text = K.providers_text


def _leaky_view(state):
    return ["", "  authorization: Bearer %s" % _STAGED, ""]


K.providers_text = _leaky_view
try:
    _leak_txt, _, _ = K.dispatch("3", K.State())
finally:
    K.providers_text = _orig_providers_text

check_true("dispatch SCRUBS a key that a view emits (behavioural)",
           _STAGED not in _leak_txt,
           "(C) kills the survivor a source-text check could not")
check_true("the staged-leak probe was restored",
           K.providers_text is _orig_providers_text, "(C)")
check_true("the staged leak really was key-shaped (non-vacuity)",
           _STAGED not in _real_redact("Bearer %s" % _STAGED),
           "(C) proves redact recognises this marker, so the check above could"
           " have failed")

# The "usable right now" verdict must account for COST, not just for the key.
# MEASURED: the battery seeded "the billable-provider warning is dropped" and it
# SURVIVED -- no assertion tested the billable blocker at all, so a console that
# called a paid provider "usable right now" with no --allow-paid would have
# shipped green. The key is set in this suite, which is what makes the cost the
# only remaining blocker and the distinction visible.
_t_paid, _, _ = K.dispatch("check agentrouter", K.State())
check_true("a billable provider is NOT usable without --allow-paid",
           "not usable right now" in _t_paid
           and "needs --allow-paid" in _t_paid,
           "(C) the user's recorded constraint is to spend nothing")
_t_ok, _, _ = K.dispatch("check agentrouter", K.State(allow_paid=True))
check_true("the same provider IS usable once --allow-paid is given",
           "usable right now" in _t_ok
           and "needs --allow-paid" not in _t_ok,
           "(C) non-vacuity: proves the blocker is conditional on cost, not a"
           " permanent refusal")
_t_free, _, _ = K.dispatch("check google", K.State())
check_true("a documented free provider needs no --allow-paid",
           "needs --allow-paid" not in _t_free,
           "(C) non-vacuity: proves the blocker keys on free_tier, not on"
           " every remote provider")
check_true("redact actually scrubs a staged key",
           FAKE not in _real_redact("value is %s here" % FAKE, FAKE),
           "(C) proves the guard is functional, not decorative")

# The keys view reports presence, and must report it correctly.
_t, _, _ = K.dispatch("5", K.State())
check_true("the keys view reports the set keys as set",
           "AGENTROUTER_API_KEY" in _t and "chars" in _t,
           "(C) lengths only, never values")
check_true("the keys view says values are never read",
           "never" in _t.lower(), "(C) states its own guarantee")

restore_keys()


# ===========================================================================
section("the loop terminates")
# ===========================================================================

_rc, _out = run_loop("0\n")
check("quit exits 0", _rc, 0, method="(D)")
check_true("quit says goodbye", "bye" in _out, "(C)")

_rc, _out = run_loop("")
check("immediate EOF exits 0", _rc, 0,
      method="(C) an earlier draft span forever on EOF")
check_true("EOF is reported, not silent", "end of input" in _out, "(C)")

_rc, _out = run_loop("3\n5\n")
check("EOF after commands exits 0", _rc, 0, method="(D)")

_rc, _out = run_loop("zzz\n!!!\n3\n0\n")
check("garbage does not end the session", _rc, 0, method="(D)")
check_true("the session continued past the garbage to a real command",
           "PROVIDERS (" in _out,
           "(C) proves the loop recovered rather than exiting quietly")

_rc, _out = run_loop("\n3\nengine google\n8\n0\n")
check_true("a whole session works end to end",
           "PROVIDERS (" in _out and "engine selected" in _out
           and "--provider google" in _out,
           "(C) menu -> list -> select -> command")

_rc, _out = run_loop("0\n", banner=True)
check_true("the banner draws the panel and the menu",
           "PROJECT CONSOLE" in _out and "phase 4 verdict" in _out,
           "(C) the first screen must show the guardrails")

# A staged fault inside ONE view must not kill the console. Proved by injection,
# because "it should be caught" is not evidence.
_real_view = K.providers_text


def _boom_view(_state):
    raise RuntimeError("staged fault")


try:
    K.providers_text = _boom_view
    _rc, _out = run_loop("3\n5\n0\n")
finally:
    K.providers_text = _real_view
check_true("the injected view fault was restored",
           K.providers_text is _real_view, "(C)")
check("a failing view still exits 0 at quit", _rc, 0, method="(D)")
check_true("the failing view is reported as an internal error",
           "INTERNAL ERROR" in _out,
           "(C) silence would look like a command that did nothing")
check_true("the console survived to the NEXT command",
           "API KEYS" in _out,
           "(C) one bad view must not end the session")

# And prove that probe was not vacuous: with the real view, no internal error.
_rc, _out = run_loop("3\n5\n0\n")
check_true("no internal error with the real view",
           "INTERNAL ERROR" not in _out,
           "(C) non-vacuity for the fault-injection probe above")


# ===========================================================================
section("layout: the console's own frames are not ragged")
# ===========================================================================

_FRAME_CHARS = ("|", "+", "\u2502", "\u256d", "\u251c", "\u2570", "\u2500",
                "\u2514", "\u250c", "\u256e", "\u2524", "\u256f")


def _strip_escapes(text):
    out = []
    i = 0
    while i < len(text):
        if text[i] == "\033":
            j = text.find("m", i)
            i = len(text) if j < 0 else j + 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


# The menu is the one console view that draws a box, so it is the one that can
# go ragged. Both directions matter: the shipped panel defect was a border one
# column SHORT, which a "longer than the width" test cannot see.
#
# PHYSICAL lines, not list items. `menu_text()` returns a list of BLOBS, and
# `panel._box_row()` returns a newline-joined string when its text has to wrap
# -- MEASURED: a 90-char row at width 40 comes back as ONE string holding THREE
# physical lines. The first version of this check ran visible_width() over the
# blob and so measured 40+41 = 81 and 122, and reported the menu as ragged at 40
# columns when it was not. VERIFIED after splitting: at widths 40/60/78/100/120,
# across all three style tiers, every physical frame line is EXACTLY the
# requested width. The bug was in the measurement, and a measurement that
# invents a defect is as bad as one that hides it.
def _physical(state):
    """Every physical line of the menu, with wrapped blobs split apart."""
    for blob in K.menu_text(state):
        for line in blob.split("\n"):
            yield line


_ragged = []
_thin_frames = []
for _w in (40, 60, 78, 100, 120):
    for _st_ in (K.State(width=_w), K.State(width=_w, ascii_only=True),
                 K.State(width=_w, no_colour=True)):
        _widths = {}
        for _line in _physical(_st_):
            if not _strip_escapes(_line).strip().startswith(_FRAME_CHARS):
                continue
            _vw = P.visible_width(_line)
            _widths[_vw] = _widths.get(_vw, 0) + 1
        if len(_widths) > 1:
            _ragged.append((_w, dict(_widths)))
        if sum(_widths.values()) < 5:
            _thin_frames.append((_w, sum(_widths.values())))
check_true("the frame detector matched frame lines at every width (%s)"
           % (_thin_frames[:2] or "none"), not _thin_frames,
           "(C) an empty histogram would pass the next check vacuously")
check_true("the menu frame is one consistent width everywhere (%s)"
           % (_ragged[:2] or "none"), not _ragged,
           "(C) a border one column SHORT is the defect that already shipped")

# The menu must fit inside the width it was asked for -- i.e. it must WRAP at 40
# columns, not overflow. Same physical-line rule as above.
_over = []
for _w in (40, 60, 78, 100, 120):
    for _line in _physical(K.State(width=_w)):
        if P.visible_width(_line) > _w:
            _over.append((_w, P.visible_width(_line)))
check_true("no menu line exceeds its width (%s)" % (_over[:2] or "none"),
           not _over, "(C) wrapping, not overflow, at 40 columns")

# Non-vacuity: the assertion above must be capable of firing. A row deliberately
# wider than the frame must come back WRAPPED, not overflowing -- if _box_row
# ever stopped wrapping, the loop above would catch it, and this proves the
# detector sees the width it thinks it sees.
_probe = P._box_row(K.State(width=40, no_colour=True).style(), 40, "x" * 200)
check_true("a deliberately over-long row wraps into several physical lines (%d)"
           % len(_probe.split("\n")), len(_probe.split("\n")) >= 4,
           "(C) proves the overflow check has something real to measure")
check_true("and every physical line of that row is exactly 40 wide",
           {P.visible_width(_l) for _l in _probe.split("\n")} == {40},
           "(C) the wrap pads, it does not merely break")


# ===========================================================================
section("guardrails are visible from the console")
# ===========================================================================

_t, _, _ = K.dispatch("7", K.State())
check_true("the guardrail view states the phase 4 verdict",
           "8 FAIL" in _t and "3 PASS" in _t and "1 PENDING" in _t
           and "of 12" in _t,
           "(C) 8+3+1=12; a tally of 14 shipped once and was wrong")
check_true("the verdict is labelled COMPUTED, not MEASURED",
           "COMPUTED" in _t and "MEASURED" not in _t,
           "(C) threshold_verdicts in the evidence file is null by design")
check_true("the guardrail view states the gate is held",
           "measurements_recorded is None" in _t,
           "(C) the gate the whole project hangs on")
check_true("the guardrail view states live trading is disabled",
           "DISABLED" in _t, "(C) the default that must never drift")

_t, _, _ = K.dispatch("6", K.State())
check_true("the local model view carries its MEASURED numbers",
           "3.62" in _t and "48.6" in _t and "MEASURED" in _t,
           "(C) the local model's failure must stay visible after APIs arrived")

_t, _, _ = K.dispatch("3", K.State())
check_true("the provider list says cost is documentation, not a quota",
           "not a quota" in _t or "NOT a quota" in _t,
           "(C) published free-tier figures disagree; none is recorded as fact")
# Every provider must appear, matched by TOKEN rather than by a padded
# substring. MEASURED: the first version of this check looked for "  local  "
# and found 13 of 14, because the selected engine's row is prefixed with the
# marker "* " -- "  * local" -- so the leading-space pattern missed exactly the
# row the user cares most about. The registry and the view really did agree; the
# pattern was wrong. Tokenising also stops "agentrouter" from being credited by
# the "agentrouter-anthropic" line, which a plain `in` test would do.
_listed = set()
for _line in _t.split("\n"):
    for _tok in _strip_escapes(_line).replace("*", " ").split():
        _listed.add(_tok)
_missing = [n for n in PR.provider_names() if n not in _listed]
check_true("the provider list shows every provider (missing: %s)"
           % (_missing or "none"), not _missing,
           "(C) list and registry must agree, including the selected row")
check_true("the selected engine is marked in the list",
           any(_l.strip().startswith("*") and "local" in _l
               for _l in _t.split("\n")),
           "(C) non-vacuity: proves the '*' marker exists, which is what broke"
           " the pattern above")
check_true("the list states the count it is showing (%d)" % len(PR.PROVIDERS),
           "(%d)" % len(PR.PROVIDERS) in _t,
           "(C) a header count that drifts from the rows is how a wrong tally"
           " shipped before")


restore_keys()
sys.exit(summary())
