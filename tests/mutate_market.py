"""
Mutation battery for the Phase 3A market-data layer (src/market/quotes.py).

WHY THIS FILE EXISTS SEPARATELY FROM mutate_rag.py
--------------------------------------------------
mutate_rag.py runs test_rag.py as its oracle. A quotes.py mutation applied under
that battery would be tested by a suite that barely imports quotes.py, so nearly
every one would survive for the uninteresting reason that the wrong suite was
watching. This battery's oracle is test_market.py AND probe_quotes.py, together:

  - test_market.py asserts the contract, including the POSITIVE cases (a valid
    quote must still construct). Mutations that make the module refuse
    everything die here and only here.
  - probe_quotes.py asserts that 49 pathological inputs are refused. Mutations
    that make the module accept garbage die here and only here.

Running just one would let half the mutation classes through. That is not a
hypothetical: `last=0.0` and `last=inf` were ACCEPTED by Quote for the whole
session in which the adversarial probe reported 45/45 refused, because the probe
only tried the pathologies I thought of first.

WHAT A SURVIVOR MEANS
---------------------
A survivor is a finding about the TESTS, not the code: the seeded defect is real
and nothing noticed. A SKIP is worse than a survivor, because it looks like a
non-event -- in this project a SKIP has already concealed a live survivor. Both
are failures and both set a non-zero exit.

A NOTE ON WRITING THE MUTATIONS THEMSELVES
------------------------------------------
Five times in this project I have seeded a mutation that changed nothing and
then read its survival as a test gap. The last one was
`usable_for_machine_data=bool([])`, written believing it was an obfuscated True.
`bool([])` is False -- so the "mutation" was the original behaviour and it
"survived" trivially. Every replacement below was checked for being a genuine
behavioural change before it was added, and the ones that merely LOOK dangerous
are called out in comments.

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

# The two oracles. Order matters only for readability of the output.
ORACLES = ("test_market.py", "probe_quotes.py")


def module_path(module):
    return os.path.join(SRC_ROOT, module)


# Mutations that cannot be killed because another layer independently enforces
# the same thing. Documented individually so that "survived: 0" keeps meaning
# something and nobody learns to skim past a nonzero count.
EQUIVALENT = {
    "market/quotes.py: purpose need not be stated":
        "the else-branch of assert_usable_for catches it anyway. MEASURED by "
        "applying the mutation by hand: purpose='' / None / 0 still raise "
        "MarketDataError(\"unknown purpose ''; allowed: live_order, ...\") "
        "instead of \"purpose must be a non-empty string\". Only the message "
        "changes, so no test can distinguish them without asserting message "
        "text -- and the explicit guard exists to give a caller who passed "
        "nothing a diagnosis rather than a vocabulary list",
}

# (module, description, find, replace)
MUTATIONS = [
    # --- the licence gate: the whole point of the provider registry ---------
    ("market/quotes.py", "a provider can be enabled despite a prohibited licence",
     "        if enabled and permits_machine_use is not True:",
     "        if False:"),
    ("market/quotes.py", "assert_provider_usable no longer refuses PROHIBITED",
     "    if p.permits_machine_use is False:",
     "    if False:"),
    # This mutation SKIPPED on 2026-08-14 and the skip was the finding, not the
    # mutation: its find-string was `if p.permits_machine_use is None:` on one
    # line, and when the USER_ACCEPTED_RISK route was added the guard became a
    # two-line condition. MEASURED with `grep -Fc`: the old string occurs ZERO
    # times, so this entry had quietly stopped testing anything while still
    # printing a line. Re-pointed at the code as it now reads.
    ("market/quotes.py", "assert_provider_usable treats UNVERIFIED as permitted",
     '    if p.permits_machine_use is None \\\n'
     '            and p.activation_basis != "USER_ACCEPTED_RISK":',
     "    if False:"),
    ("market/quotes.py", "a registered-but-disabled provider is usable",
     "    if not p.enabled:",
     "    if False:"),
    ("market/quotes.py", "UNKNOWN collapses into False (tri-state destroyed)",
     "        if permits_machine_use not in (True, False, None):",
     "        permits_machine_use = bool(permits_machine_use)\n"
     "        if permits_machine_use not in (True, False, None):"),
    ("market/quotes.py", "a provider need not record its licence terms",
     "        if not licence_note:",
     "        if False:"),
    ("market/quotes.py", "a reviewed provider entry can be silently overwritten",
     "    if p.key in _PROVIDERS:",
     "    if False:"),
    ("market/quotes.py", "register_provider accepts any object",
     "    if not isinstance(p, Provider):",
     "    if False:"),
    ("market/quotes.py", "TradingView downgraded from PROHIBITED to UNKNOWN",
     "    permits_machine_use=False,         # checked, and forbidden",
     "    permits_machine_use=None,"),
    ("market/quotes.py", "Twelve Data promoted from UNVERIFIED to permitted",
     "    permits_machine_use=None,          # category yes, tier UNVERIFIED",
     "    permits_machine_use=True,"),
    ("market/quotes.py", "fetch_quote silently returns nothing instead of refusing",
     '    raise NotImplementedError(\n'
     '        "no market-data provider is licensed for machine use yet. "',
     '    return None\n'
     '    raise NotImplementedError(\n'
     '        "no market-data provider is licensed for machine use yet. "'),

    # --- numeric pathologies: each guard removed independently -------------
    # These four are the reason the battery exists. Two of them (inf, zero) were
    # ABSENT from the code until a boundary probe found them by hand, so they are
    # exactly the class of defect that ships looking correct.
    ("market/quotes.py", "NaN prices are accepted again",
     "            if value != value:            # NaN",
     "            if False:"),
    ("market/quotes.py", "infinite prices are accepted again",
     '            if value in (float("inf"), float("-inf")):',
     "            if False:"),
    ("market/quotes.py", "zero prices are accepted again",
     "            if value == 0:",
     "            if False:"),
    ("market/quotes.py", "negative prices are accepted again",
     "            if value < 0:",
     "            if False:"),
    ("market/quotes.py", "a crossed quote (bid > ask) is accepted",
     "        if (bid is not None and ask is not None) and bid > ask:",
     "        if False:"),
    # A bool IS an int in Python, so dropping the bool exclusion makes
    # last=True a valid price of 1.0. Genuinely different behaviour.
    ("market/quotes.py", "True is accepted as a price of 1.0",
     "            if not isinstance(value, (int, float)) or isinstance(value, bool):",
     "            if not isinstance(value, (int, float)):"),
    ("market/quotes.py", "a quote with no bid, ask or last is accepted",
     "        if bid is None and ask is None and last is None:",
     "        if False:"),

    # --- the SS.5.5 mandatory fields ---------------------------------------
    ("market/quotes.py", "an unattributed price is accepted (no provider)",
     "        if not provider or not isinstance(provider, str):",
     "        if False:"),
    ("market/quotes.py", "a price with no exchange is accepted",
     "        if not exchange:",
     "        if False:"),
    ("market/quotes.py", "a price with no currency is accepted",
     "        if not currency:",
     "        if False:"),
    ("market/quotes.py", "an undated price is accepted",
     "        if timestamp is None:",
     "        if False:"),
    ("market/quotes.py", "a naive timestamp needs no timezone",
     "        if not timezone:",
     "        if False:"),
    ("market/quotes.py", "closed vocabularies are no longer closed",
     "            if value not in allowed:",
     "            if False:"),
    ("market/quotes.py", "any trust level is accepted",
     "        if trust_level not in TRUST_LEVELS:",
     "        if False:"),
    ("market/quotes.py", "retrieved_at is left unset when not supplied",
     "        self.retrieved_at = retrieved_at or _utc_now()",
     "        self.retrieved_at = retrieved_at"),
    # Dropping ONE field from _FIELDS: to_dict() and the 21-field assertion
    # must notice. Chosen deliberately as a dangerous one.
    ("market/quotes.py", "adjustment_status drops out of the field set",
     '               "adjustment_status", "corporate_action_status", "licence",',
     '               "corporate_action_status", "licence",'),

    # --- immutability: evidence that can be edited is not evidence ----------
    ("market/quotes.py", "quotes become mutable after construction",
     '    def __setattr__(self, name, value):\n'
     '        if getattr(self, "_frozen", False):\n'
     '            raise MarketDataError(\n'
     '                "quotes are immutable: refusing to set %r on %s/%s. A price "',
     '    def __setattr__(self, name, value):\n'
     '        if False:\n'
     '            raise MarketDataError(\n'
     '                "quotes are immutable: refusing to set %r on %s/%s. A price "'),
    ("market/quotes.py", "quote fields become deletable",
     '    def __delattr__(self, name):\n'
     '        raise MarketDataError("quotes are immutable: refusing to delete %r"\n'
     '                              % (name,))',
     '    def __delattr__(self, name):\n'
     '        object.__delattr__(self, name)'),
    ("market/quotes.py", "provider terms become editable at runtime",
     '    def __setattr__(self, name, value):\n'
     '        if getattr(self, "_frozen", False):\n'
     '            raise MarketDataError(\n'
     '                "provider terms are immutable: refusing to set %r on %r. One "',
     '    def __setattr__(self, name, value):\n'
     '        if False:\n'
     '            raise MarketDataError(\n'
     '                "provider terms are immutable: refusing to set %r on %r. One "'),
    ("market/quotes.py", "provider terms become deletable",
     '    def __delattr__(self, name):\n'
     '        raise MarketDataError("provider terms are immutable: refusing to delete "\n'
     '                              "%r on %r" % (name, self.key))',
     '    def __delattr__(self, name):\n'
     '        object.__delattr__(self, name)'),
    # PROVIDERS stops being a read-only view, so a caller can inject an
    # unreviewed provider straight into the registry.
    ("market/quotes.py", "the provider registry is exposed as a mutable dict",
     "PROVIDERS: Mapping[str, Provider] = MappingProxyType(_PROVIDERS)",
     "PROVIDERS: Mapping[str, Provider] = _PROVIDERS"),

    # --- SS.7.1 Level 3: weak origins, and staleness -----------------------
    ("market/quotes.py", "screenshot values stop being weak",
     "        return self.origin in WEAK_ORIGINS",
     "        return False"),
    ("market/quotes.py", "USER_SUPPLIED drops out of the weak set",
     'WEAK_ORIGINS = ("VISUALLY_EXTRACTED", "USER_SUPPLIED", "UNKNOWN")',
     'WEAK_ORIGINS = ("VISUALLY_EXTRACTED", "UNKNOWN")'),
    ("market/quotes.py", "VISUALLY_EXTRACTED drops out of the weak set",
     'WEAK_ORIGINS = ("VISUALLY_EXTRACTED", "USER_SUPPLIED", "UNKNOWN")',
     'WEAK_ORIGINS = ("USER_SUPPLIED", "UNKNOWN")'),
    # is_live requires BOTH conditions. Weakening it to either one is the
    # classic "delayed quote used as live" defect.
    ("market/quotes.py", "is_live accepts a realtime feed of a CLOSED market",
     '        return self.delay_status == "REALTIME" and self.market_status == "OPEN"',
     '        return self.delay_status == "REALTIME"'),
    ("market/quotes.py", "is_live accepts any quote from an open market",
     '        return self.delay_status == "REALTIME" and self.market_status == "OPEN"',
     '        return self.market_status == "OPEN"'),
    ("market/quotes.py", "a stale quote may price a live order",
     "            if not self.is_live:",
     "            if False:"),
    # The two `if self.is_weak:` blocks are distinguished by their following
    # line -- a bare `if self.is_weak:` would match twice and SKIP, and a SKIP
    # in this project has already hidden a live survivor.
    ("market/quotes.py", "a screenshot value may price a live order",
     '        if purpose == "live_order":\n            if self.is_weak:',
     '        if purpose == "live_order":\n            if False:'),
    ("market/quotes.py",
     "a screenshot value may be sole evidence for a material calculation",
     '        elif purpose == "material_calculation":\n            if self.is_weak:',
     '        elif purpose == "material_calculation":\n            if False:'),
    ("market/quotes.py", "an unrecognised purpose is assumed permitted",
     '        else:\n'
     '            raise MarketDataError(\n'
     '                "unknown purpose %r; allowed: live_order, material_calculation, "',
     '        else:\n'
     '            return\n'
     '            raise MarketDataError(\n'
     '                "unknown purpose %r; allowed: live_order, material_calculation, "'),
    ("market/quotes.py", "purpose need not be stated",
     "        if not purpose or not isinstance(purpose, str):",
     "        if False:"),
    # quote_from_user_input must not launder a hand-typed number into a
    # trusted provider value. Two independent ways to do that.
    ("market/quotes.py", "user input is laundered into a PROVIDER_API value",
     '        origin="USER_SUPPLIED", bid=bid, ask=ask, last=last,',
     '        origin="PROVIDER_API", bid=bid, ask=ask, last=last,'),
    ("market/quotes.py", "user input is granted exchange-level trust",
     '        corporate_action_status="UNKNOWN", trust_level="UNVERIFIED",',
     '        corporate_action_status="UNKNOWN", trust_level="EXCHANGE",'),
    ("market/quotes.py", "user input defaults to REALTIME instead of UNKNOWN",
     '                          delay_status="UNKNOWN", market_status="UNKNOWN",',
     '                          delay_status="REALTIME", market_status="OPEN",'),

    # --- reporting: a manifest that miscounts hides the finding ------------
    ("market/quotes.py", "enabled_providers reports every provider as enabled",
     "    return [p for p in PROVIDERS.values() if p.enabled]",
     "    return list(PROVIDERS.values())"),
    ("market/quotes.py", "manifest miscounts prohibited providers",
     "            \"n_prohibited\": sum(1 for p in PROVIDERS.values()\n"
     "                                if p.permits_machine_use is False),",
     "            \"n_prohibited\": 0,"),

    # --- the USER_ACCEPTED_RISK activation route (added 2026-08-14) ---------
    # Every mutation below targets code written TODAY, on the day the first real
    # provider was switched on. Without these the new guards have zero mutation
    # coverage, which in this project means untested: the guards are exactly the
    # kind that pass a refusal-only suite while doing nothing.
    #
    # The order of the two licence checks is itself the design, so it is
    # mutated: a PROHIBITION consented away is a breach of someone else's
    # contract, not an accepted risk.
    ("market/quotes.py",
     "a PROHIBITED provider may be enabled by accepting the risk",
     "            if permits_machine_use is False:",
     "            if False:"),
    ("market/quotes.py",
     "assert_provider_usable checks the UNKNOWN case before the PROHIBITION",
     '    p = get_provider(key)\n'
     '    if p.permits_machine_use is False:\n'
     '        raise MarketDataError(\n'
     '            "provider %r PROHIBITS machine use: %s" % (key, p.status))\n'
     '    if p.permits_machine_use is None \\\n'
     '            and p.activation_basis != "USER_ACCEPTED_RISK":',
     '    p = get_provider(key)\n'
     '    if p.permits_machine_use is None \\\n'
     '            and p.activation_basis != "USER_ACCEPTED_RISK":'),
    # The escape hatch itself: if any basis unlocks the gate, then the vocabulary
    # is decoration and LICENCE_EXPLICIT could be typed in with nothing read.
    ("market/quotes.py", "any activation_basis unlocks an unlicensed provider",
     '            if activation_basis != "USER_ACCEPTED_RISK":',
     "            if activation_basis is None and False:"),
    ("market/quotes.py",
     "an enabled provider need not record WHY it is on",
     "        if enabled and activation_basis is None:",
     "        if False:"),
    ("market/quotes.py",
     "a disabled provider may carry a leftover activation basis",
     "        if not enabled and activation_basis is not None:",
     "        if False:"),
    ("market/quotes.py", "an accepted risk may be an empty list",
     "            if not accepted_risks:",
     "            if False:"),
    ("market/quotes.py", "an accepted risk needs no owner and no date",
     "            if not decided_by or not decided_on:",
     "            if False:"),
    # `or` instead of `and` still looks like a guard and still refuses SOME
    # inputs -- the failure mode a refusal-only assertion cannot see.
    ("market/quotes.py", "an accepted risk needs only ONE of owner or date",
     "            if not decided_by or not decided_on:",
     "            if not decided_by and not decided_on:"),
    ("market/quotes.py",
     "activation_basis accepts any string, not just the vocabulary",
     "        if activation_basis is not None and activation_basis not in ACTIVATION_BASES:",
     "        if False:"),
    # accepted_risks is stored as a tuple on purpose: a frozen object that hands
    # out a mutable list lets the record be edited after it was approved.
    ("market/quotes.py", "accepted_risks is stored as a mutable list",
     "        self.accepted_risks = tuple(accepted_risks or ())",
     "        self.accepted_risks = list(accepted_risks or ())"),
    ("market/quotes.py",
     "user_accepted_risk_providers cannot see the weakly-authorized ones",
     '    return [p for p in PROVIDERS.values()\n'
     '            if p.enabled and p.activation_basis == "USER_ACCEPTED_RISK"]',
     "    return []"),

    # --- the MEASURED free-tier limits (regulatory, not cosmetic) -----------
    # "Realtime and 15-minute delayed US market data is regulated by the stock
    # exchanges, FINRA, and the SEC" -- premium-only. A tier gate that passes
    # everything produces a quote labelled REALTIME that is end-of-day data.
    ("market/quotes.py", "the free tier is allowed to supply any delay_status",
     "    if delay_status not in allowed:",
     "    if False:"),
    ("market/quotes.py", "an unknown provider key silently permits every tier",
     '    if delay_status not in DELAY_STATUS:',
     '    if False and delay_status not in DELAY_STATUS:'),
    ("market/quotes.py", "the free tier is silently widened to REALTIME",
     '        "permitted_delay_status": ("END_OF_DAY", "UNKNOWN"),',
     '        "permitted_delay_status": ("END_OF_DAY", "UNKNOWN", "REALTIME",\n'
     '                                  "DELAYED"),'),
    ("market/quotes.py", "the measured daily request budget is inflated",
     '        "requests_per_day": 25,',
     '        "requests_per_day": 2500,'),

    # --- the LATENT DEFECT found by enabling the first provider -------------
    # MEASURED on 2026-08-14: this gate read `origin` only, so all six trust
    # levels passed, including UNVERIFIED, which rag.documents defines as "never
    # citable as fact". It was unreachable while every provider was disabled.
    # These mutations restore the defect on purpose, so that its absence is a
    # tested property rather than a fix nobody watches.
    ("market/quotes.py",
     "an UNVERIFIED quote is again sole evidence for a material calculation",
     "            if TRUST_LEVELS.get(self.trust_level, 0) <= 0:",
     "            if False:"),
    ("market/quotes.py", "the trust gate is off by one and admits UNVERIFIED",
     "            if TRUST_LEVELS.get(self.trust_level, 0) <= 0:",
     "            if TRUST_LEVELS.get(self.trust_level, 0) < 0:"),
    # A missing trust level scoring as permitted is the fail-open direction: an
    # unrecognised label would be treated better than one known to be weak.
    ("market/quotes.py", "an unrecognised trust level defaults to permitted",
     "            if TRUST_LEVELS.get(self.trust_level, 0) <= 0:",
     "            if TRUST_LEVELS.get(self.trust_level, 100) <= 0:"),
    ("market/quotes.py", "the trust gate reads the origin instead of the trust",
     "            if TRUST_LEVELS.get(self.trust_level, 0) <= 0:",
     "            if self.origin in WEAK_ORIGINS:"),
]


def run_oracle(name):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = SRC_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, name)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = proc.stdout.decode("utf-8", "replace")
    ok = proc.returncode == 0
    # probe_quotes.py exits 0 when everything was refused, but an ALLOWED or
    # CRASHED line is a failure even so. Belt and braces: a probe that starts
    # allowing things must not read as a passing oracle.
    if "** ALLOWED" in out or "!! CRASHED" in out:
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


def main():
    clear_pycache()

    ok, out = run_tests()
    if not ok:
        print("ABORT: an oracle fails BEFORE any mutation is applied.")
        print(out[-3000:])
        return 1
    print("baseline: both oracles pass (%s), %d mutations to apply\n"
          % (", ".join(ORACLES), len(MUTATIONS)))

    backup = tempfile.mkdtemp(prefix="market_orig_")
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
                # This check exists because I have written one five times.
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
