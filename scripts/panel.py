#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The project panel: what is configured, what it costs, what is still failing.

WHY THIS FILE EXISTS
--------------------
`scripts/run_phase4.py --help` tells the user "Run scripts/panel.py to see them
all" when describing --provider. That promise was written before this file was,
which made it a dangling reference -- a small lie in the help text of the one
command the user is expected to run. This file is that promise kept.

WHAT IT DOES AND DELIBERATELY DOES NOT DO
-----------------------------------------
It reads. It opens no socket, spends no quota, and writes no file. Every number
it prints comes from `src/llm/panel.py`, which in turn reads
`credential_status()` -- presence and length of keys, never the keys. So this
command is safe to run at any time, including on a metered connection, and its
output is safe to screenshot.

It is NOT a launcher. It will not start a run, because this project's rule is
that no run starts without the user's explicit approval, and a panel that could
be one keystroke from a 3.6-hour CPU burn would be a trap.

EXIT CODES
----------
  0  the panel rendered (or the requested provider is ready)
  1  a refusal the user can act on -- unknown provider name, --check on a
     provider with no key set, --check on a paid provider without --allow-paid
  3  an internal error, i.e. a bug in this project rather than a user mistake.
     Kept distinct because a traceback dressed as a refusal wasted real time
     earlier in this project (a missing `import re` read as "the tool declined").
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "src"))
sys.path.insert(0, _HERE)


def _hint_id(hint):
    """
    Split a MODEL_HINTS entry into (copyable id or None, prose to show).

    DEFECT FOUND BY MEASUREMENT 2026-08-27, in this file: MODEL_HINTS values are
    prose, not bare ids -- 'e.g. gpt-4o-mini (UNVERIFIED hint; check the models
    list)'. Interpolating one straight into an example command produced

        --model-id e.g. gpt-4o-mini (UNVERIFIED hint; check the models list)

    which is a copy-paste trap: the shell breaks on the parentheses and the
    model id becomes 'e.g.'. On a free tier that failure can cost a quota
    request to discover. So the bare id is extracted for the command line and
    the prose is shown separately as what it is -- guidance, not a value.

    Three providers (custom, openrouter, together) deliberately have no example
    id because the id itself decides the endpoint or the price. Those return
    None and the command shows a <model-id> placeholder the user must replace.
    """
    import re
    text = str(hint or "").strip()
    if not text:
        return None, ""
    m = re.match(r"^e\.g\.\s+([A-Za-z0-9._:\-/]+)\s*(?:\(.*\))?\s*$", text)
    if m:
        return m.group(1), text
    return None, text


def _die_internal(exc: BaseException) -> int:
    """
    A bug, reported as a bug.

    The message says INTERNAL ERROR so it can never be mistaken for one of the
    project's deliberate refusals. Both look like a line of red text on the
    console; only the wording separates them.
    """
    sys.stderr.write("INTERNAL ERROR (%s): %s\n"
                     % (type(exc).__name__, exc))
    sys.stderr.write("This is a defect in the project, not a mistake in your "
                     "command. Please report it with the line above.\n")
    return 3


def _detail(provider: str, allow_paid: bool) -> int:
    """
    One provider, in full, with the exact command to use it.

    `--check` answers a narrower question than the panel does: not "what exists"
    but "can I run this right now, and would it cost me anything". It therefore
    refuses in the same three ways a real run would refuse, so the user finds
    out here rather than after a model download or a queue wait.
    """
    from llm.providers import (ProviderError, get_api_key, get_provider,
                               credential_status, resolve_base_url)
    from llm import clients as LC

    try:
        spec = get_provider(provider)
    except ProviderError as exc:
        sys.stderr.write("REFUSED: %s\n" % exc)
        return 1

    rows = {r["provider"]: r for r in credential_status()}
    row = rows.get(provider, {})

    # VERIFIED against providers.py before printing, after four defects in this
    # very function were caught by reading the registry instead of trusting
    # memory: there is no `limits_url` field (the field is `docs`),
    # `needs_base_url` is computed by credential_status() and is NOT on the
    # spec, and `key_length` is None -- not 0 -- for a provider that needs no
    # key, which made "%d" a crash on the likeliest first command, --check local.
    print("")
    print("provider      : %s" % provider)
    print("label         : %s" % spec.get("label", "?"))
    print("wire dialect  : %s" % spec.get("wire", "?"))
    free = spec.get("free_tier")
    print("cost class    : %s" % ({True: "FREE TIER DOCUMENTED",
                                  False: "PAID",
                                  None: "UNKNOWN"}[free]))
    print("cost note     : %s" % (spec.get("cost") or "-"))
    env_key = spec.get("env_key")
    print("env variable  : %s" % (env_key or "-- none needed --"))
    if env_key is None:
        key_state = "no key required"
    elif row.get("configured"):
        n = row.get("key_length")
        key_state = ("set (%d chars)" % n) if isinstance(n, int) else "set"
    else:
        key_state = "NOT SET"
    print("key state     : %s" % key_state)
    print("docs / limits : %s" % (spec.get("docs") or "-"))
    print("quota         : UNKNOWN -- this project records no third-party quota "
          "as a fact.")
    print("                Published free-tier figures disagreed when checked, "
          "so read")
    print("                the page above rather than trusting a number here.")
    if spec.get("note"):
        print("note          : %s" % spec["note"])
    print("")

    # Resolve BEFORE gating. The loopback exemption is a decision about the
    # RESOLVED url; gating first made a localhost `custom` provider look
    # billable earlier in this project.
    try:
        endpoint = resolve_base_url(provider, None)
    except ProviderError as exc:
        print("endpoint      : REFUSED -- %s" % exc)
        print("")
        print("Cannot check readiness without an endpoint. Pass --base-url on "
              "the run command.")
        return 1
    print("endpoint      : %s" % (endpoint or "-- local, no endpoint --"))

    ready = True
    try:
        gate = LC.spend_gate(provider, allow_paid=allow_paid, base_url=endpoint)
        if gate.get("local_endpoint"):
            print("spend gate    : PASS -- endpoint is loopback, nothing is "
                  "billed")
        elif gate.get("billable"):
            print("spend gate    : PASS -- --allow-paid was given; a real run "
                  "MAY BE BILLED")
        else:
            print("spend gate    : PASS -- documented free tier, no "
                  "--allow-paid needed")
    except ProviderError as exc:
        print("spend gate    : REFUSED -- %s" % exc)
        ready = False

    if spec.get("env_key"):
        try:
            get_api_key(provider)
            print("credential    : PASS -- usable key found in the environment")
        except ProviderError as exc:
            print("credential    : REFUSED -- %s" % exc)
            ready = False
    else:
        print("credential    : PASS -- no key required")

    hint_id, hint_prose = _hint_id(LC.MODEL_HINTS.get(provider))
    print("")
    if hint_prose:
        print("A model id is REQUIRED and is never chosen for you. Guidance "
              "below is an")
        print("UNVERIFIED hint, not a measured fact -- provider catalogues "
              "change:")
        print("    %s" % hint_prose)
    if provider == "local":
        print("Example run (the default path, no network, no cost):")
        print("    python scripts/run_phase4.py --model "
              "C:\\models\\Qwen3.5-4B-Q5_K_M.gguf \\")
        print("        --arms plain --out results\\phase4_plain.json")
    else:
        extra = " --allow-paid" if free is not True else ""
        # needs_base_url is computed by credential_status(), not stored on the
        # spec. Reading it from the spec silently produced False for `custom`,
        # the one provider that actually requires --base-url.
        base = " --base-url https://..." if row.get("needs_base_url") else ""
        print("Example run:")
        print("    python scripts/run_phase4.py --provider %s --model-id %s%s%s \\"
              % (provider, hint_id or "<MODEL-ID>", base, extra))
        print("        --arms plain --out results\\phase4_%s.json" % provider)
        print("")
        print("A remote run measures ANSWER QUALITY only. It measures nothing "
              "about")
        print("your CPU, so the four hardware thresholds stay PENDING and the "
              "result")
        print("file is labelled MEASURED_REMOTE_API, never MEASURED.")
    print("")

    if not ready:
        print("VERDICT: NOT READY -- see the REFUSED lines above.")
        return 1
    print("VERDICT: READY.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Show the project panel: providers, local model state, "
                    "and guardrails. Reads only -- opens no network "
                    "connection, spends no quota, writes no file.")
    ap.add_argument("--width", type=int, default=None,
                    help="panel width in columns (default: 78, or the "
                         "terminal width when it is narrower)")
    ap.add_argument("--ascii", action="store_true",
                    help="force the pure-ASCII tier, for a legacy code page")
    ap.add_argument("--no-colour", "--no-color", dest="no_colour",
                    action="store_true",
                    help="force colour off (NO_COLOR is honoured too)")
    ap.add_argument("--check", metavar="PROVIDER", default=None,
                    help="check one provider's readiness instead of drawing "
                         "the panel; exits 1 if it is not usable right now")
    ap.add_argument("--allow-paid", action="store_true",
                    help="with --check, accept that the provider is paid or "
                         "of unknown cost")
    ap.add_argument("--json", action="store_true",
                    help="print provider readiness as JSON (no key material; "
                         "lengths only) instead of the panel")
    args = ap.parse_args(argv)

    try:
        from llm import panel as P
        from llm.providers import PROVIDERS, credential_status
    except Exception as exc:                     # pragma: no cover
        return _die_internal(exc)

    try:
        if args.check:
            return _detail(args.check.strip(), args.allow_paid)

        if args.json:
            # credential_status() reports presence and length only; there is no
            # code path from here to a key's value.
            payload = {
                "provider_count": len(PROVIDERS),
                "default_provider": "local",
                "providers": credential_status(),
                "quota_recorded": None,
                "note": ("free_tier reflects the provider's own documentation, "
                         "not a measured quota. No quota is recorded as a "
                         "fact anywhere in this project."),
            }
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        width = args.width
        if width is None:
            try:
                cols = os.get_terminal_size().columns
            except Exception:
                cols = P.PANEL_WIDTH
            width = min(P.PANEL_WIDTH, max(40, cols))
        if width < 20:
            sys.stderr.write("REFUSED: --width %d is too narrow to render "
                             "anything readable (minimum 20).\n" % width)
            return 1

        if args.ascii or args.no_colour:
            caps = P.detect_caps(sys.stdout)
            style = P.Style(unicode_ok=False if args.ascii else caps["unicode"],
                            colour=False if args.no_colour else caps["colour"])
            text = P.render(style, width=width)
            try:
                sys.stdout.write(text + "\n")
            except UnicodeEncodeError:
                enc = getattr(sys.stdout, "encoding", None) or "ascii"
                sys.stdout.write(
                    text.encode(enc, "replace").decode(enc, "replace") + "\n")
        else:
            P.print_panel(sys.stdout, width=width)
        return 0
    except SystemExit:
        raise
    except Exception as exc:
        return _die_internal(exc)


if __name__ == "__main__":
    sys.exit(main())
