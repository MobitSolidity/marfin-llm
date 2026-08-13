"""
Mutation battery for the webhook receiver (src/market/webhooks.py).

WHY THIS BATTERY EXISTS AT ALL
------------------------------
Because in this module, a passing test suite has already been proven worthless
twice. The adversarial sweep passed COMPLETELY -- around forty attacks, every one
refused, the clean delivery accepted, no secret in the durable file -- while two
serious defects were live:

  * ValidatedEvent validated NOTHING, so a hand-built event carrying
    {"action": "buy"} reached the durable JSONL file.
  * The instruction blocklist held "disable_risk" and "enable_live" and let
    "disable_risk_checks" and "enable_live_trading" straight through.

Neither was found by a test failing. Both were found by deliberately attacking
the CLEAN passes. A mutation battery is the systematic version of that: it breaks
the module on purpose and asks whether anything notices.

THE TWO ORACLES, AND WHY BOTH
-----------------------------
  - probe_webhooks.py kills mutations that make the receiver ACCEPT what it must
    refuse: 111 attacks plus 53 structural claims.
  - test_webhooks.py kills mutations that make the receiver REFUSE EVERYTHING,
    or refuse for the WRONG REASON, or lose the order of checks.

Running only the probe would let "refuse every delivery" through -- a receiver
that rejects all traffic passes every adversarial probe perfectly and is useless.
Running only the suite would let "accept anything" through in the paths the suite
happens not to construct.

THE MUTATION CLASSES HERE, AND WHAT EACH ONE IS FOR
---------------------------------------------------
1. GUARD REMOVAL (`if X:` -> `if False:`). The blunt instrument: does anything
   notice when a check stops running?

2. ORDER-OF-CHECKS. Reordering is the mutation class this module needs most,
   because the order IS the design: signature before parsing, size before
   hashing, instructions before schema, everything before the acknowledgement. A
   reordered receiver still refuses the same set of deliveries -- so only a test
   that asserts WHICH guard answered can tell. That is precisely the assertion
   most test suites omit.

3. THRESHOLD WEAKENING. Age, size, skew. A threshold moved deep inside its own
   boundary is a mutation that dies for the wrong reason; the CSV battery taught
   this (step*0.5 -> step*0.001 survived because the fixtures were 60s apart).
   So each threshold here is loosened by orders of magnitude.

4. VOCABULARY EROSION. Removing entries from INSTRUCTION_KEYS /
   INSTRUCTION_TOKENS / ALLOWED_TIMEFRAMES, and -- the one that matters most --
   changing WEBHOOK_ORIGIN back to "WEBHOOK", the actual measured defect.

5. FAIL-OPEN INVERSIONS. `return` instead of `raise`, and the specific inversion
   that makes an absent signature acceptable. These are the mutations that turn a
   guard into a comment.

WHAT A SURVIVOR MEANS
---------------------
A survivor is a finding about the TESTS, not the code: the seeded defect is real
and nothing noticed. A SKIP is worse, because it reads as a non-event -- in this
project a SKIP has already concealed a live survivor. Both are failures and both
set a non-zero exit.

Stdlib only.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC_ROOT = os.path.join(ROOT, "src")

ORACLES = ("test_webhooks.py", "probe_webhooks.py")


def run_oracle(name):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = SRC_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, name)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.stdout.decode("utf-8", "replace")
    ok = proc.returncode == 0
    # Belt and braces: a probe that starts allowing things, crashing, or letting
    # the wrong guard answer must not read as a passing oracle even if some
    # future edit breaks its exit code.
    for marker in ("** ALLOWED", "!! CRASHED", "** WRONG EXC",
                   "** WRONG GUARD", "** DEFECT"):
        if marker in out:
            ok = False
    return ok, out


def run_tests():
    """Both oracles must pass. Either one failing kills the mutation."""
    for name in ORACLES:
        ok, out = run_oracle(name)
        if not ok:
            return False, "%s FAILED\n%s" % (name, out[-2000:])
    return True, ""


def clear_pycache():
    for dirpath, dirnames, _ in os.walk(ROOT):
        for d in list(dirnames):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)


def module_path(module):
    return os.path.join(SRC_ROOT, module)


# Mutations that cannot be killed because another layer independently enforces
# the same thing. Starts EMPTY on purpose: an equivalence claim is a claim I
# would rather be forced to defend mutation by mutation than have sitting here
# unexamined, since it dissolves silently the moment the surrounding code moves.
#: Mutations that CANNOT be killed because they do not change behaviour on any
#: reachable input. Each entry is a claim that had to be MEASURED before it was
#: allowed here, because "equivalent" is the easiest place in this file to hide a
#: real survivor: writing a description here silences the exit code.
#:
#: The bar for an entry is: I attempted to reach the guard and FAILED, and the
#: attempt is recorded. A guard I merely could not think of an input for does not
#: qualify.
EQUIVALENT = {
    "market/webhooks.py: a record containing a newline is written anyway":
        # MEASURED, eight routes attempted against
        #   json.dumps(record, sort_keys=True, default=str)
        # which is the module's only serialisation call (line 1024, no indent=):
        #   value "x\ny"      -> '{"a": "x\\ny"}'      raw newline: False
        #   KEY   "k\ney"     -> '{"k\\ney": "v"}'     raw newline: False
        #   carriage return   -> '{"a": "x\\ry"}'      raw newline: False
        #   U+2028 LINE SEP   -> '{"a": "x\\u2028y"}'  raw newline: False
        #   U+0085 NEL        -> '{"a": "x\\u0085y"}'  raw newline: False
        #   nested dict/list  -> escaped at any depth  raw newline: False
        #   non-str + default=str (__str__ returns "x\ny") -> escaped
        #   lone surrogate    -> '{"a": "x\\ud800y"}'  raw newline: False
        # The only json.dumps setting that emits newlines is indent=, and the
        # call site does not pass it. So the guard is unreachable TODAY and no
        # test can kill the mutant.
        #
        # It stays in the module regardless, and that is not sentiment: the queue
        # file's whole format is one JSON object per line, so a reader splits on
        # newlines. If anyone ever adds indent= for readability, or swaps the
        # serialiser, a single record would silently become several malformed
        # ones. The guard costs one comparison per write to make that failure
        # loud. What the tests assert instead is the invariant it protects --
        # that the format really is one line per record -- which IS reachable.
        "unreachable via json.dumps: all 8 newline routes escape; "
        "defence-in-depth against a future indent= or serialiser change",
}

M = "market/webhooks.py"

# (module, description, find, replace)
MUTATIONS = [
    # =====================================================================
    # 1. TRANSPORT AND AUTHENTICATION -- guard removal
    # =====================================================================
    (M, "http:// deliveries are accepted",
     '    if low.startswith("http://"):',
     "    if False:"),
    (M, "a non-https scheme falls through instead of refusing",
     '    if low.startswith("https://"):\n        return',
     '    if True:\n        return'),
    (M, "any HTTP method is accepted",
     '    if not isinstance(method, str) or method.strip().upper() != "POST":',
     "    if False:"),
    (M, "a missing shared secret is treated as 'no auth needed'",
     "    if not secret:",
     "    if False:"),
    (M, "a missing signature header is accepted",
     "    if not provided:",
     "    if False:"),
    # The single most dangerous mutation in this file: a leaked or absent
    # signature becomes acceptable, and the receiver cannot tell who sent what.
    (M, "the signature comparison always succeeds",
     "    if not hmac.compare_digest(expected, got):",
     "    if False:"),
    (M, "the signature comparison becomes non-constant-time ==",
     "    if not hmac.compare_digest(expected, got):",
     "    if expected != got and False:"),
    # Signing a re-serialization instead of the raw body. This FAILS on valid
    # payloads (key order and spacing differ) and can be made to pass on
    # modified ones -- the classic webhook signature defect.
    (M, "the signature is computed over a RE-SERIALIZED parse, not raw bytes",
     '    expected = hmac.new(secret.encode("utf-8"), bytes(body),',
     '    expected = hmac.new(secret.encode("utf-8"),\n'
     "                        json.dumps(json.loads("
     'bytes(body).decode("utf-8"))).encode("utf-8"),'),
    (M, "any content type is accepted",
     "    if base not in ALLOWED_CONTENT_TYPES:",
     "    if False:"),
    (M, "the body size limit is removed",
     "    if n > MAX_BODY_BYTES:",
     "    if False:"),
    (M, "the source allowlist is ignored",
     "    if not allowlist:",
     "    if True:"),

    # =====================================================================
    # 2. THRESHOLD WEAKENING -- loosened by orders of magnitude, so a
    #    fixture near the boundary cannot pass for the wrong reason
    # =====================================================================
    (M, "the body size cap becomes 64 MB",
     "MAX_BODY_BYTES = 64 * 1024",
     "MAX_BODY_BYTES = 64 * 1024 * 1024"),
    (M, "the maximum event age becomes a week",
     "MAX_EVENT_AGE_SECONDS = 300",
     "MAX_EVENT_AGE_SECONDS = 604800"),
    (M, "the clock-skew tolerance becomes a day (future events accepted)",
     "MAX_CLOCK_SKEW_SECONDS = 60",
     "MAX_CLOCK_SKEW_SECONDS = 86400"),
    (M, "the stale-event check is removed",
     "    if age > MAX_EVENT_AGE_SECONDS:",
     "    if False:"),
    (M, "the future-event check is removed",
     "    if age < -MAX_CLOCK_SKEW_SECONDS:",
     "    if False:"),

    # =====================================================================
    # 3. THE SEVEN PROHIBITIONS -- vocabulary erosion
    # =====================================================================
    (M, "the instruction parser is disabled entirely",
     "    if found:",
     "    if False:"),
    (M, "the instruction parser stops walking NESTED objects",
     "                walk(value, here)",
     "                pass"),
    (M, "the instruction parser stops walking LISTS",
     "        elif isinstance(node, (list, tuple)):",
     "        elif False:"),
    # The exact-match/token split is the fix for a MEASURED defect. Removing
    # either layer must be noticed, or the fix was decoration.
    (M, "the TOKEN layer is removed (compound keys get through again)",
     "                    for tok in key_tokens(key):",
     "                    for tok in ():"),
    (M, "token matching becomes SUBSTRING matching (false positives return)",
     '    return tuple(t for t in _TOKEN_SPLIT.split(str(key).strip().lower()) if t)',
     '    return (str(key).strip().lower(),) + tuple(\n'
     '        t for t in _TOKEN_SPLIT.split(str(key).strip().lower()) if t)'),
    (M, "'action' stops being an instruction token",
     '    "action": "authorize trades",\n    "side": "authorize trades",\n'
     '    "qty": "authorize trades",\n    "quantity": "authorize trades",\n'
     '    "buy": "authorize trades",',
     '    "side": "authorize trades",\n'
     '    "qty": "authorize trades",\n    "quantity": "authorize trades",\n'
     '    "buy": "authorize trades",'),
    (M, "'account' stops being an instruction token",
     '    "account": "select an account",\n    "broker": "select an account",',
     '    "broker": "select an account",'),
    # This mutation removes the TOKEN and the exact key that masks it. MEASURED:
    # with only the token removed, "disable_risk_checks" was still caught by the
    # EXACT map, so the mutation was not discriminating and survived for the
    # wrong reason. The tests now use "disable_all_guards", whose only dangerous
    # token is "disable" and which is in no exact map.
    (M, "'disable' stops being an instruction token",
     '    "disable": "disable risk controls",',
     ''),
    (M, "'live' stops being an instruction token",
     '    "live": "change policies",\n    "policy": "change policies",',
     '    "policy": "change policies",'),
    # MEASURED: "shell_cmd" tokenises to ('shell', 'cmd'), so removing only the
    # "shell" token left "cmd" to catch it -- the mutation survived because
    # another token masked it, not because nothing noticed. The tests now use
    # "shell_target", whose only dangerous token is "shell".
    (M, "'shell' stops being an instruction token",
     '    "shell": "execute shell commands",\n    "cmd": "execute shell commands",',
     '    "cmd": "execute shell commands",'),
    (M, "instructions are STRIPPED instead of refused",
     "    if found:\n        # Report ALL of them",
     "    if False:\n        # Report ALL of them"),
    (M, "only the FIRST offending key is reported",
     '               ", ".join("%s (-> cannot %s)" % (p, w) for p, w in found),',
     '               ", ".join("%s (-> cannot %s)" % (p, w) for p, w in found[:1]),'),

    # =====================================================================
    # 4. THE ACCEPTANCE CRITERION -- "Webhooks cannot authorize trades"
    # =====================================================================
    (M, "a webhook becomes usable for a LIVE ORDER",
     '        if purpose in ("live_order", "paper_order", "submit_order",\n'
     '                       "order_preview", "position_sizing"):',
     "        if False:"),
    (M, "order_preview quietly drops off the refused list",
     '        if purpose in ("live_order", "paper_order", "submit_order",\n'
     '                       "order_preview", "position_sizing"):',
     '        if purpose in ("live_order", "paper_order", "submit_order",\n'
     '                       "position_sizing"):'),
    (M, "a webhook becomes usable as a PRICE source",
     '        if purpose == "material_calculation":',
     "        if False:"),
    (M, "an UNKNOWN purpose is assumed permitted (fail-open)",
     '        raise WebhookError(\n'
     '            "unknown purpose %r; allowed: notify, display, audit, "',
     '        return\n'
     '        raise WebhookError(\n'
     '            "unknown purpose %r; allowed: notify, display, audit, "'),
    (M, "the event becomes MUTABLE after validation",
     '        if getattr(self, "_frozen", False):',
     "        if False:"),
    (M, "a side field is added to the event (something to act on)",
     '    _FIELDS = ("event_id", "alert_id", "symbol", "exchange", "timeframe",',
     '    _FIELDS = ("side", "event_id", "alert_id", "symbol", "exchange", "timeframe",'),

    # =====================================================================
    # 5. THE ORIGIN LABEL -- the exact measured defect, re-seeded
    # =====================================================================
    (M, "the origin label goes back to the out-of-vocabulary 'WEBHOOK'",
     'WEBHOOK_ORIGIN = "UNKNOWN"',
     'WEBHOOK_ORIGIN = "WEBHOOK"'),
    (M, "the origin label becomes a STRONG origin",
     'WEBHOOK_ORIGIN = "UNKNOWN"',
     'WEBHOOK_ORIGIN = "PROVIDER_API"'),
    (M, "the import-time vocabulary guard is removed",
     "if WEBHOOK_ORIGIN not in VALUE_ORIGINS:      # pragma: no cover - import guard",
     "if False:"),
    (M, "the import-time weak-origin guard is removed",
     "if WEBHOOK_ORIGIN not in WEAK_ORIGINS:       # pragma: no cover - import guard",
     "if False:"),

    # =====================================================================
    # 6. ValidatedEvent's OWN VALIDATION -- DEFECT 2, re-seeded field by field
    #    Each is removed individually: a single combined removal could be
    #    caught by any one surviving guard, leaving the rest unexercised.
    # =====================================================================
    (M, "the event stops validating its event_id",
     '        _require_id({"event_id": event_id}, "event_id", "event_id")',
     "        pass"),
    (M, "the event stops validating its alert_id",
     '        _require_id({"alert_id": alert_id}, "alert_id", "alert id")',
     "        pass"),
    (M, "the event stops validating its timeframe",
     '        _require_str({"timeframe": timeframe}, "timeframe", "timeframe",\n'
     '                     allowed=ALLOWED_TIMEFRAMES)',
     "        pass"),
    (M, "the event accepts a timezone-NAIVE timestamp",
     "            if value.tzinfo is None:",
     "            if False:"),
    (M, "the event accepts a non-datetime timestamp",
     "            if not isinstance(value, datetime.datetime):",
     "            if False:"),
    (M, "the event accepts a negative n_bytes",
     "        if not isinstance(n_bytes, int) or isinstance(n_bytes, bool) \\\n"
     "                or n_bytes <= 0:",
     "        if False:"),
    (M, "the event accepts a bogus body digest",
     "        if not isinstance(body_sha256, str) \\\n"
     '                or not re.match(r"^[0-9a-f]{64}$", body_sha256):',
     "        if False:"),
    # The bypass that actually reached the durable file.
    (M, "an INSTRUCTION can enter through the leftovers dict again",
     "        assert_no_instructions(dict(extra or {}))",
     "        pass"),

    # =====================================================================
    # 7. SCHEMA
    # =====================================================================
    (M, "required string fields stop being required",
     "    if value is None or not isinstance(value, str) or not value.strip():",
     "    if False:"),
    (M, "the id character set is no longer restricted (path traversal)",
     "    if not _ID_SAFE.match(text):",
     "    if False:"),
    (M, "the id pattern allows slashes and dots",
     '_ID_SAFE = re.compile(r"^[A-Za-z0-9._:\\-]{1,128}$")',
     '_ID_SAFE = re.compile(r"^.{1,128}$")'),
    (M, "the free-text length cap is removed",
     "    if len(text) > maxlen:",
     "    if False:"),
    (M, "a vocabulary-restricted field accepts anything",
     "    if allowed is not None and text not in allowed:",
     "    if False:"),
    (M, "a JSON array body is accepted as a payload",
     "    if not isinstance(data, dict):",
     "    if False:"),
    (M, "a non-UTF-8 body is no longer refused",
     "    except UnicodeDecodeError as exc:",
     "    except KeyboardInterrupt as exc:"),
    (M, "an unexpected timeframe joins the allowed set",
     'ALLOWED_TIMEFRAMES = ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w")',
     'ALLOWED_TIMEFRAMES = ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "3h")'),
    (M, "the expected-alert-id check is removed",
     "    if expected_alert_ids and alert_id not in tuple(expected_alert_ids):",
     "    if False:"),
    (M, "the expected-symbol check is removed",
     "    if expected_symbols and symbol not in tuple(expected_symbols):",
     "    if False:"),
    (M, "the expected-exchange check is removed",
     "    if expected_exchanges and exchange not in tuple(expected_exchanges):",
     "    if False:"),

    # =====================================================================
    # 8. TIMESTAMPS
    # =====================================================================
    (M, "a naive timestamp is assumed UTC instead of refused",
     "    if ts.tzinfo is None:",
     "    if False:"),
    (M, "an epoch NUMBER is accepted as a timestamp",
     "    if not isinstance(raw, str):",
     "    if False:"),
    (M, "a missing timestamp is accepted",
     "    if raw is None:",
     "    if False:"),

    # =====================================================================
    # 9. DUPLICATE / REPLAY / DURABILITY
    # =====================================================================
    (M, "the duplicate check in receive() is removed",
     "    if queue.has_seen(event_id):",
     "    if False:"),
    (M, "the duplicate check in append() is removed too",
     "        if event.event_id in self._seen:",
     "        if False:"),
    # Replay state that does not outlive the process re-opens the whole window
    # on every restart, which is invisible until someone restarts the service.
    (M, "the seen-set is no longer loaded from disk (replay after restart)",
     "        self._seen = {}          # event_id -> received_at ISO string\n"
     "        self._load_seen()",
     "        self._seen = {}          # event_id -> received_at ISO string"),
    (M, "the queue no longer fsyncs before acknowledging",
     "            os.fsync(fh.fileno())",
     "            pass"),
    (M, "an unvalidated object can be queued",
     "        if not isinstance(event, ValidatedEvent):",
     "        if False:"),
    (M, "a record containing a newline is written anyway",
     '        if "\\n" in line:',
     "        if False:"),

    # =====================================================================
    # 10. SECRET REDACTION -- a secret in a durable file cannot be unwritten
    # =====================================================================
    (M, "header redaction is removed entirely",
     "        if low in _SECRET_HEADERS or any(low.endswith(s)\n"
     "                                        for s in _SECRET_HEADER_SUFFIXES):",
     "        if False:"),
    (M, "redaction keeps a PREFIX of the secret",
     '            out[str(name)] = "[REDACTED]"',
     '            out[str(name)] = "[REDACTED:%s]" % (str(value)[:8],)'),
    (M, "the authorization header stops being secret-shaped",
     '_SECRET_HEADERS = ("authorization", "x-signature", "x-hub-signature",',
     '_SECRET_HEADERS = ("x-signature", "x-hub-signature",'),
    (M, "the suffix rule is removed (x-custom-token leaks)",
     '_SECRET_HEADER_SUFFIXES = ("-signature", "-secret", "-token", "-key",\n'
     '                           "-password", "-auth")',
     '_SECRET_HEADER_SUFFIXES = ()'),
    (M, "the queue stops re-redacting before writing",
     '        record["headers"] = redact_headers(record.get("headers", {}))',
     "        pass"),

    # =====================================================================
    # 11. ORDER OF CHECKS -- the mutation class that a set-of-refusals test
    #     cannot see at all. Each of these still refuses the same deliveries.
    # =====================================================================
    # The body is parsed BEFORE the signature is verified: a receiver that does
    # this has run a JSON parser over unauthenticated bytes.
    (M, "the body is PARSED BEFORE the signature is verified",
     "    verify_signature(body, provided, secret)\n"
     "    assert_source_allowed(source_ip, allowlist)\n"
     "\n"
     "    payload = parse_body(body)",
     "    payload = parse_body(body)\n"
     "    verify_signature(body, provided, secret)\n"
     "    assert_source_allowed(source_ip, allowlist)"),
    # Size is checked AFTER the signature: hashing 64 MB in order to then reject
    # it for being 64 MB is the denial-of-service.
    (M, "the size limit is checked AFTER the signature is computed",
     "    assert_https(url)\n"
     "    assert_content_type(headers)\n"
     "    n_bytes = assert_size(body)",
     "    assert_https(url)\n"
     "    assert_content_type(headers)"),
    # Schema before instructions: an instruction-bearing payload then gets
    # refused as a malformed alert, and the sender never learns the real reason.
    (M, "the schema is validated BEFORE instruction keys are refused",
     "    assert_no_instructions(payload)\n"
     "\n"
     '    event_id = _require_id(payload, "event_id", "event id")',
     '    event_id = _require_id(payload, "event_id", "event id")\n'
     "    assert_no_instructions(payload)"),
    # The age check stops running while the event is still queued: a stale or
    # future-dated replay is then persisted and acknowledged.
    (M, "the event is queued even though the age check no longer runs",
     "    age = assert_age(fired_at, now=now)",
     "    age = (now - fired_at).total_seconds()"),
]


def main():
    clear_pycache()

    ok, out = run_tests()
    if not ok:
        print("ABORT: an oracle fails BEFORE any mutation is applied.")
        print(out[-3000:])
        return 1
    print("baseline: both oracles pass (%s), %d mutations to apply\n"
          % (", ".join(ORACLES), len(MUTATIONS)))

    backup = tempfile.mkdtemp(prefix="wh_orig_")
    _backed_up = {}
    for module in sorted({m for (m, _, _, _) in MUTATIONS}):
        flat = module.replace("/", "__")
        shutil.copy2(module_path(module), os.path.join(backup, flat))
        _backed_up[flat] = module_path(module)

    killed = survived = skipped = equivalent = 0
    survivors, skips, unexpected_kills = [], [], []
    try:
        for i, (module, desc, find, repl) in enumerate(MUTATIONS, 1):
            path = module_path(module)
            with open(path, "r", encoding="utf-8") as fh:
                original = fh.read()
            if find not in original:
                skipped += 1
                skips.append("%s: %s" % (module, desc))
                print("  %2d. SKIP     %-58s (pattern absent)" % (i, desc[:58]))
                continue
            if original.count(find) > 1:
                skipped += 1
                skips.append("%s: %s (ambiguous)" % (module, desc))
                print("  %2d. SKIP     %-58s (ambiguous)" % (i, desc[:58]))
                continue
            mutated = original.replace(find, repl, 1)
            if mutated == original:
                # A no-op "mutation" is not a finding, it is a bug in this file.
                skipped += 1
                skips.append("%s: %s (NO-OP: find == replace)" % (module, desc))
                print("  %2d. SKIP     %-58s (NO-OP, fix the mutation)"
                      % (i, desc[:58]))
                continue
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(mutated)
                passed, _ = run_tests()
                key = "%s: %s" % (module, desc)
                if passed and key in EQUIVALENT:
                    equivalent += 1
                    print("  %2d. equiv    %-58s (%s)"
                          % (i, desc[:58], EQUIVALENT[key][:40]))
                elif passed:
                    survived += 1
                    survivors.append(key)
                    print("  %2d. SURVIVED %-58s <-- NOT TESTED" % (i, desc[:58]))
                else:
                    killed += 1
                    if key in EQUIVALENT:
                        unexpected_kills.append(key)
                    print("  %2d. killed   %s" % (i, desc[:58]))
            finally:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(original)
    finally:
        for name, dest in _backed_up.items():
            shutil.copy2(os.path.join(backup, name), dest)
        shutil.rmtree(backup, ignore_errors=True)

    intact, _ = run_tests()
    print("\n" + "=" * 78)
    print("  seeded:     %d" % len(MUTATIONS))
    print("  killed:     %d" % killed)
    print("  equivalent: %d (documented redundant guards)" % equivalent)
    print("  survived:   %d" % survived)
    print("  skipped:    %d" % skipped)
    print("  source restored and oracles green: %s" % intact)
    for s in survivors:
        print("  SURVIVOR: %s" % s)
    for s in skips:
        print("  SKIPPED:  %s" % s)
    for s in unexpected_kills:
        print("  RECHECK:  %s was listed as equivalent but was KILLED" % s)
    print("=" * 78)
    return 0 if (survived == 0 and skipped == 0 and not unexpected_kills
                 and intact) else 1


if __name__ == "__main__":
    sys.exit(main())
