#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mutation battery for the LLM provider layer.

A passing suite proves nothing. test_llm_providers.py prints "195 passed, 0
failed", and the only way to find out whether those 195 assertions actually
DISCRIMINATE is to break the module deliberately and check that they notice.
Every battery in this project has found real gaps this way, and one of them
found a suite that could not fail at all.

WHAT MAKES THIS LAYER WORTH A BATTERY
-------------------------------------
Its two worst failure modes are silent:

  1. A credential reaches output. Nothing crashes. The user finds out when
     somebody else uses their key.
  2. A billable call is made that the user did not authorise. Nothing crashes.
     The user finds out on a statement -- and this user's recorded constraint is
     to spend nothing at all.

A mutant that survives here means one of those two is unguarded.

THREE FILES, AND WHY RESTORE IS HANDLED THE WAY IT IS
-----------------------------------------------------
This battery mutates providers.py, clients.py and panel.py. R23/D-0054 in this
project: `finally` does NOT run on SIGKILL, and a frozen sandbox once left
src/tools/selector.py mutated on disk, which then poisoned every later run. So:

  * originals are copied to a temp directory BEFORE anything is touched
  * only ONE file is mutated at a time, and it is restored immediately
  * the final state of all three files is compared against the originals and
    reported as an explicit True/False line that run_all.sh greps for
  * an INTEGRITY line names any file left modified, so a killed run is
    diagnosable rather than mysterious

Run: python3 tests/mutate_llm_providers.py
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LLM = os.path.join(ROOT, "src", "llm")

PROVIDERS_PY = os.path.join(LLM, "providers.py")
CLIENTS_PY = os.path.join(LLM, "clients.py")
PANEL_PY = os.path.join(LLM, "panel.py")
CONSOLE_PY = os.path.join(LLM, "console.py")

TESTS = os.path.join(HERE, "test_llm_providers.py")
CONSOLE_TESTS = os.path.join(HERE, "test_console.py")
PANEL_CLI = os.path.join(ROOT, "scripts", "panel.py")

# ---------------------------------------------------------------------------
# The mutations.
#
# Each is a defect a reasonable person could actually write: an inverted
# condition, a dropped guard, a widened default, a "simplification". Nothing
# here is a strawman -- several are mistakes I made in this very layer during
# development and then fixed.
#
# (file, description, find, replace)
# ---------------------------------------------------------------------------
# Mutations that CANNOT be killed because the change is semantically a no-op.
# The bar for an entry is not "I could not think of a test": it is "I PROVED the
# mutant behaves identically to the original", and the proof is recorded here.
# Each entry is also cross-checked at run time: if one of these is ever killed,
# the RECHECK line fires and the claim below must be re-examined, because either
# the module changed or the proof was wrong.
EQUIVALENT = {
    # PROVED 2026-08-27 by differential testing over 7 URLs, including the
    # crafted attack the description imagines ("https://evil.com/http://
    # localhost:8080/"): 0 behavioural differences. re.match() is already
    # anchored at the start of the string, so a leading "^" is redundant. The
    # description "evil.com passes" is FALSE -- evil.com is rejected by both
    # patterns, because .match() never scans forward. Note this would NOT be
    # equivalent under re.search(), so the equivalence depends on line 140
    # continuing to call .match().
    "loopback exemption anchors removed (evil.com passes)":
        "re.match() already anchors; 7 URLs, 0 differences",
    # PROVED 2026-08-27 by AST inspection of detect_caps(): the try body assigns
    # unicode_ok and the single handler assigns unicode_ok, so EVERY control
    # path overwrites the initial value before it is read. The initial
    # assignment is a dead store kept for readability, and flipping a dead
    # store cannot change behaviour. It becomes killable the moment a path
    # exists that does not reassign -- which is why the RECHECK exists.
    "unicode capability assumed rather than proven":
        "dead store: every path reassigns unicode_ok",
}


MUTATIONS = [
    # ---- providers.py: the cost classification -------------------------
    (PROVIDERS_PY, "deepseek's UNKNOWN cost reclassified as free",
     '"cost": "UNKNOWN; check the pricing page",\n        "docs": "https://api-docs.deepseek.com/quick_start/pricing",',
     '"cost": "free",\n        "docs": "https://api-docs.deepseek.com/quick_start/pricing",'),
    (PROVIDERS_PY, "deepseek's tri-state UNKNOWN collapsed to free",
     '"free_tier": None,\n        "cost": "UNKNOWN; check the pricing page",\n        "docs": "https://api-docs.deepseek.com/quick_start/pricing",',
     '"free_tier": True,\n        "cost": "UNKNOWN; check the pricing page",\n        "docs": "https://api-docs.deepseek.com/quick_start/pricing",'),

    # ---- providers.py: credential handling ------------------------------
    # A behavioural mutation, not a syntactic one. The first version of this
    # mutant produced a SyntaxError, which the oracles duly "killed" -- but
    # killing a SyntaxError proves only that Python can parse, not that any
    # assertion checks placeholder rejection. Every mutant in this battery is
    # verified to still PARSE before it is trusted.
    (PROVIDERS_PY, "placeholder keys accepted as real",
     'if low == bad or low.startswith(bad):', 'if False:'),
    (PROVIDERS_PY, "key shape check removed (empty/garbage accepted)",
     'if not _KEY_RE.match(key):', 'if False:'),

    # ---- providers.py: redaction, the property with no undo -------------
    (PROVIDERS_PY, "redaction returns its input untouched",
     'def redact(text: Any, *keys: Optional[str]) -> str:',
     'def redact(text: Any, *keys: Optional[str]) -> str:\n    return str(text)'),
    # Groq's prefix uses an UNDERSCORE (gsk_). A hyphen-only pattern once
    # passed a suite of hyphenated fakes and then leaked a live key, so the
    # underscore prefix gets its own mutant. The `find` string includes the
    # surrounding quote to stay unambiguous: bare "gsk" appears 4 times.
    (PROVIDERS_PY, "underscore separator dropped from the key regex (gsk_)",
     r'r"[-_][A-Za-z0-9_\-]{12,}"', r'r"[-][A-Za-z0-9_\-]{12,}"'),
    (PROVIDERS_PY, "google AIza keys no longer redacted",
     r'r"(?<![A-Za-z0-9])AIza[A-Za-z0-9_\-]{20,}"',
     r'r"(?<![A-Za-z0-9])AIzaDISABLED[A-Za-z0-9_\-]{20,}"'),
    (PROVIDERS_PY, "explicitly-passed keys no longer replaced",
     'out = out.replace(str(key), "[REDACTED-API-KEY]")',
     'pass  # out = out.replace(str(key), "[REDACTED-API-KEY]")'),
    (PROVIDERS_PY, "labelled-credential sweep removed",
     r'r"(?i)\b(api[-_]?key|authorization|bearer|x-api-key)"',
     r'r"(?i)\bZZNOMATCHZZ(api[-_]?key|authorization|bearer|x-api-key)"'),

    # ---- providers.py: endpoint safety ----------------------------------
    (PROVIDERS_PY, "custom provider gets a silent default endpoint",
     'if not url:\n        raise ProviderError(\n            "provider %r has no endpoint.',
     'if not url:\n        return "https://api.openai.com/v1"\n    if False:\n        raise ProviderError(\n            "provider %r has no endpoint.'),

    # ---- clients.py: the spend gate ------------------------------------
    (CLIENTS_PY, "spend gate never refuses a billable call",
     'if billable and not allow_paid:', 'if False:'),
    (CLIENTS_PY, "UNKNOWN cost treated as free by the gate",
     'billable = free is not True', 'billable = free is False'),
    (CLIENTS_PY, "loopback exemption widened to any host",
     '_LOCALHOST_RE.match(str(base_url).strip())', 'True'),
    (CLIENTS_PY, "loopback exemption anchors removed (evil.com passes)",
     'r"^https?://(localhost', 'r"https?://(localhost'),

    # ---- clients.py: the local model must never go on the wire ----------
    (CLIENTS_PY, "local model silently sent over HTTP",
     'if spec["wire"] == "local":', 'if False:'),

    # ---- clients.py: retries and the attempt count ----------------------
    (CLIENTS_PY, "a 400 is retried, burning quota for the same answer",
     'RETRY_STATUS = (408, 409, 425, 429, 500, 502, 503, 504)',
     'RETRY_STATUS = (400, 408, 409, 425, 429, 500, 502, 503, 504)'),
    (CLIENTS_PY, "retry exhaustion no longer reports the attempt count",
     'attempts, detail, hint))', '0, detail, hint))'),
    (CLIENTS_PY, "429 not retried at all",
     '429, 500', '499, 500'),

    # ---- clients.py: no answer must stay visible ------------------------
    (CLIENTS_PY, "zero choices graded as an empty answer",
     'no choices', 'DISABLED no choices'),

    # ---- clients.py: no model id is ever guessed ------------------------
    (CLIENTS_PY, "a default model id is invented",
     'model_id = (model_id or "").strip()\n    if not model_id:',
     'model_id = (model_id or "gpt-4o-mini").strip()\n    if not model_id:'),

    # ---- clients.py: wire details --------------------------------------
    (CLIENTS_PY, "google key moved into the query string",
     'x-goog-api-key', 'x-goog-api-key-DISABLED'),
    (CLIENTS_PY, "anthropic sent a Bearer token instead of x-api-key",
     'headers["x-api-key"] = key', 'headers["Authorization"] = "Bearer " + key'),
    (CLIENTS_PY, "anthropic thinking blocks concatenated into the answer",
     'if isinstance(b, dict) and b.get("type") == "text"]',
     'if isinstance(b, dict)]'),

    # ---- panel.py: the panel must never print key material -------------
    (PANEL_PY, "panel output no longer passed through redact",
     'return redact("\\n".join(L))', 'return "\\n".join(L)'),
    (PANEL_PY, "unicode capability assumed rather than proven",
     'unicode_ok = False\n    enc', 'unicode_ok = True\n    enc'),
    (PANEL_PY, "NO_COLOR ignored",
     'if str(env.get("NO_COLOR", "")).strip() != "":',
     'if False:'),
    (PANEL_PY, "colour written into a redirected file",
     'elif not tty:', 'elif False:'),
    (PANEL_PY, "box width off by one (the defect that already shipped)",
     'fill = max(0, width - 3 - len(label))',
     'fill = max(0, width - 4 - len(label))'),
    (PANEL_PY, "long rows truncated instead of wrapped",
     'def _split_visible(text: str, width: int) -> List[str]:',
     'def _split_visible(text: str, width: int) -> List[str]:\n    return [text[:width]]'),
    (PANEL_PY, "local model section removed from the panel",
     'for line in local_status_rows(style):', 'for line in []:'),
    # The verdict tally itself was WRONG in shipped code (it said "3 PENDING",
    # summing to 14 against 12 thresholds, and claimed MEASURED for a figure the
    # evidence file deliberately leaves null). Both halves are now mutated: an
    # inflated count, and a COMPUTED label downgraded to MEASURED.
    (PANEL_PY, "verdict tally inflated past the 12 approved thresholds",
     '"8 FAIL / 3 PASS / 1 PENDING of 12 (COMPUTED)"',
     '"8 FAIL / 3 PASS / 3 PENDING of 12 (COMPUTED)"'),
    (PANEL_PY, "a COMPUTED aggregate relabelled as MEASURED",
     '"8 FAIL / 3 PASS / 1 PENDING of 12 (COMPUTED)"',
     '"8 FAIL / 3 PASS / 1 PENDING of 12 (MEASURED)"'),
    (PANEL_PY, "local model failures reported as passes",
     'style.c("bad", pad("3.62-4.38 tok/s (min 8) FAIL", 34))',
     'style.c("ok", pad("3.62-4.38 tok/s PASS", 34))'),

    # ---- console.py: the interactive menu (added 2026-08-27) ------------
    # The console's failure modes are DIFFERENT from the provider layer's, and
    # that is the whole reason it gets its own mutants. A wrong number is not
    # the risk here. The risks are: a command that silently does nothing, a
    # refusal that changes state anyway, a loop that will not exit, and -- the
    # one that matters most -- a menu that starts a run. Each mutant below is
    # one of those four, and each was reachable by an ordinary mistake.

    # A refusal that half-applies. The user asks for an engine that does not
    # exist and the console selects it anyway; menu 8 then prints a run command
    # for a provider with no endpoint and no key.
    (CONSOLE_PY, "an unknown engine name is accepted and selected",
     'if name not in PROVIDERS:', 'if False:'),

    # Selection that does not select. The single most likely "it looks fine"
    # defect: the view renders, the warning prints, and the engine silently
    # stays local -- so menu 8 confidently prints the WRONG command.
    (CONSOLE_PY, "choosing an engine does not actually change it",
     'new.engine = name', 'new.engine = state.engine'),

    # The two-base-url trap goes unwarned. AgentRouter's own FAQ says mixing
    # them 404s; the warning at the moment of choosing is the whole mitigation.
    (CONSOLE_PY, "the AgentRouter two-base-url warning is suppressed",
     'if name.startswith("agentrouter"):', 'if False:'),

    # Defence in depth removed. Nothing on these paths handles a key value
    # TODAY, so a surviving mutant here is not automatically a leak -- it is
    # notice that the guard is untested and will not be there on the day
    # someone adds a path that does.
    (CONSOLE_PY, "dispatch output no longer passes through redact",
     'return redact("\\n".join(lines)), state, quit_flag',
     'return "\\n".join(lines), state, quit_flag'),

    # The loop stops terminating on EOF. This is the mutant the SIGALRM harness
    # in test_console.py exists for: without the alarm it would HANG the run
    # rather than fail it, and a hung run in this sandbox has needed a reset.
    (CONSOLE_PY, "EOF no longer ends the session (spins forever)",
     'if raw == "":', 'if False:'),

    # One bad view kills the whole console instead of being reported.
    # `SystemExit` and not an invented name: a name that does not exist would
    # raise NameError when the handler is reached, and the oracles would "kill"
    # a mutant that never actually tested containment. SystemExit is a real
    # class that BaseException-derives and that no view raises, so the handler
    # becomes unreachable while the module stays importable and valid.
    (CONSOLE_PY, "an exception in one view is no longer contained",
     'except Exception as exc:           # never let one bad view kill the loop',
     'except SystemExit as exc:          # mutant: containment removed'),

    # An unrecognised command is silently ignored, which looks exactly like a
    # command that ran and did nothing -- the precise defect the user reported.
    (CONSOLE_PY, "an unknown command is silently ignored",
     'if key is None:', 'if False and key is None:'),

    # The cost blocker disappears from the readiness view (menu 4), so a
    # billable provider with a key set reads as "usable right now". The spend
    # gate in clients.py still refuses the actual call, but the console would be
    # telling the user something untrue about a provider whose quota is UNKNOWN.
    # Description corrected 2026-08-27: this line is in check_text(), not in the
    # run view -- the first wording named the wrong function, and a mutant
    # described wrongly sends the next reader to the wrong place.
    (CONSOLE_PY, "the cost blocker is dropped from the readiness view",
     'if free is not True and not state.allow_paid:',
     'if False and not state.allow_paid:'),
]


def _read(path):
    return io.open(path, encoding="utf-8").read()


def _write(path, text):
    io.open(path, "w", encoding="utf-8").write(text)


# Seconds any single oracle may take. MEASURED on unmutated source: the
# provider suite ~0.5 s, the console suite ~0.8 s, each panel invocation
# ~0.3 s. 60 s is roughly 70x the slowest, so it cannot fire on a merely slow
# machine -- only on a mutant that does not terminate.
ORACLE_TIMEOUT = 60

# Set when any oracle is killed by the timeout, so the summary can say so.
_TIMED_OUT = []


def _oracle_ok(argv, env, timeout=ORACLE_TIMEOUT):
    """
    Run one oracle. True if it exited 0 within `timeout`.

    WHY THE TIMEOUT IS NOT OPTIONAL. Added 2026-08-27 after this battery HUNG.
    MEASURED: with the console mutant `if raw == "":` -> `if False:` applied,
    the console's read loop never sees EOF, so the console suite ran forever;
    subprocess.run() had no timeout, so the battery waited forever with a
    mutated console.py on disk. The outer tool killed the whole process tree at
    120 s, `finally` did not run (R23/D-0054: it does not run on SIGKILL), and
    src/llm/console.py was left MUTATED -- exactly the failure this project has
    already been burned by once in src/tools/selector.py.

    A timeout here counts as a KILL, not as an error. That is the correct
    reading: a mutant that makes an oracle hang has changed observable
    behaviour, and "the test suite no longer finishes" is the suite noticing.
    Treating it as a battery failure instead would let a non-terminating mutant
    abort the run and be reported as nothing at all.
    """
    try:
        p = subprocess.run(argv, cwd=ROOT, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        _TIMED_OUT.append(os.path.basename(argv[1] if len(argv) > 1 else argv[0]))
        return False
    return p.returncode == 0


def run_oracles():
    """
    True if BOTH oracles pass.

    Two oracles, and the pairing is required rather than tidy:

      * test_llm_providers.py catches mutations that make the layer ACCEPT
        something it should refuse (a paid call, a placeholder key, a leak).
      * scripts/panel.py --check catches mutations that make it refuse or crash
        on everything, which a suite full of check_raises() assertions would
        happily report as success.

    A mutation that deletes a guard tends to be caught by the first; a mutation
    that breaks rendering or resolution tends to be caught only by the second.
    """
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # Oracle 1: the assertion suite.
    if not _oracle_ok([sys.executable, TESTS], env):
        return False
    # Oracle 1b: the console suite. Added 2026-08-27 with console.py. It is a
    # SEPARATE oracle rather than an extension of the first because it is the
    # only one that exercises the menu state machine -- reachability of every
    # advertised command, refusals that must not half-apply, and a loop that
    # must terminate. Without it, every console mutant below would survive
    # trivially and the survivors would say nothing about the console.
    if os.path.exists(CONSOLE_TESTS):
        if not _oracle_ok([sys.executable, CONSOLE_TESTS], env):
            return False
    # Oracle 2: the entry point must still work end to end for the default
    # provider and must still refuse a paid one.
    if not _oracle_ok([sys.executable, PANEL_CLI, "--check", "local"], env):
        return False
    env2 = dict(env)
    env2.pop("OPENAI_API_KEY", None)
    # NOTE the inversion: here a returncode of 0 is the FAILURE, because a paid
    # provider with no key must not report READY. A timeout is still a kill.
    if _oracle_ok([sys.executable, PANEL_CLI, "--check", "openai"], env2):
        return False
    # Oracle 3: the panel must render in the tier a legacy console gets. Piped
    # stdout is not a tty, so this still takes the one-shot draw path and does
    # NOT open the interactive console -- which is exactly the backward
    # compatibility that --once was added to preserve.
    return _oracle_ok([sys.executable, PANEL_CLI, "--ascii", "--no-colour"],
                      env)


def main():
    targets = sorted({m[0] for m in MUTATIONS})
    originals = {}
    backdir = tempfile.mkdtemp(prefix="llm_mut_")
    for path in targets:
        originals[path] = _read(path)
        shutil.copy(path, os.path.join(backdir, os.path.basename(path)))

    print("=" * 74)
    print("LLM PROVIDER LAYER MUTATION BATTERY")
    print("=" * 74)
    print("  backups: %s" % backdir)

    # If the oracles do not pass on unmutated source, every "killed" below is
    # meaningless -- it would just be reporting the pre-existing failure.
    if not run_oracles():
        print("ABORT: oracles fail on unmutated source. Nothing was mutated.")
        return 1

    killed = survived = skipped = equivalent = 0
    survivors, skips, unexpected_kills = [], [], []
    try:
        for path, desc, find, repl in MUTATIONS:
            src = originals[path]
            if find not in src:
                # A SKIP is WORSE than a survivor: it counts in "seeded" and so
                # looks like a non-event, while testing nothing at all. One skip
                # in this project once hid two real survivors.
                print("  SKIP      %-58s (pattern not found)" % desc)
                skipped += 1
                skips.append(desc)
                continue
            _write(path, src.replace(find, repl, 1))
            try:
                if run_oracles():
                    if desc in EQUIVALENT:
                        # Not a gap: a proved no-op. Counted separately so it
                        # can never be mistaken for untested behaviour.
                        print("  equiv     %-58s (%s)"
                              % (desc[:58], EQUIVALENT[desc][:44]))
                        equivalent += 1
                    else:
                        print("  SURVIVED  %s" % desc)
                        survived += 1
                        survivors.append(desc)
                else:
                    print("  killed    %s" % desc)
                    killed += 1
                    if desc in EQUIVALENT:
                        # The equivalence claim is now FALSE. Either the module
                        # changed or the proof was wrong; either way this must
                        # be re-examined, so it fails the battery.
                        unexpected_kills.append(desc)
            finally:
                _write(path, src)
    finally:
        for path, text in originals.items():
            _write(path, text)

    dirty = [os.path.basename(p) for p in targets
             if _read(p) != originals[p]]
    intact = not dirty
    green = run_oracles()

    print("-" * 74)
    print("  seeded:     %d" % len(MUTATIONS))
    print("  killed:     %d" % killed)
    print("  equivalent: %d (proved no-ops, see EQUIVALENT)" % equivalent)
    print("  survived:   %d" % survived)
    print("  skipped:    %d" % skipped)
    for s in survivors:
        print("  SURVIVOR: %s" % s)
    for s in skips:
        print("  SKIPPED:  %s" % s)
    for s in unexpected_kills:
        print("  RECHECK:  %s was listed as equivalent but was KILLED" % s)
    # A timeout is counted as a kill, but it must never be SILENT: "killed by
    # hanging" and "killed by an assertion" are different facts, and only the
    # first one tells you a mutant can make the tooling itself stop finishing.
    if _TIMED_OUT:
        seen = sorted(set(_TIMED_OUT))
        print("  TIMEOUT:  %d oracle run(s) hit the %ds limit and were counted"
              " as kills (%s)" % (len(_TIMED_OUT), ORACLE_TIMEOUT,
                                  ", ".join(seen)))
    if dirty:
        print("  INTEGRITY: files left modified: %s" % ", ".join(dirty))
    print("  source restored and oracles green: %s"
          % bool(intact and green))
    print("=" * 74)
    if intact:
        shutil.rmtree(backdir, ignore_errors=True)
    else:
        print("  backups kept at %s -- restore them before trusting a run"
              % backdir)
    return 0 if (survived == 0 and skipped == 0 and not unexpected_kills
                 and intact and green) else 1


if __name__ == "__main__":
    sys.exit(main())
