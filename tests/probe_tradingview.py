"""
Adversarial probe of the TradingView display-only wall.

I am NOT trying to confirm it works. I am trying to find the way it is wrong --
the way a determined contributor, or a future me under deadline, gets a
TradingView price into a risk calculation anyway.

Run:  python3 tests/probe_tradingview.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from market import tradingview as tv


# The project's refusal convention, from tests/_harness.py. A crash is NOT a
# refusal: the first version of this probe caught only ValueError and therefore
# reported Python's own unexpected-keyword TypeError as a crash, which would have
# sent me hunting a defect that did not exist.
REFUSALS = (ValueError, TypeError, ZeroDivisionError)


def attempt(label, fn):
    """Report whether an attack was refused, and with what."""
    try:
        result = fn()
    except tv.TradingViewLicenceError as exc:
        print("  REFUSED (licence)  %-52s %s" % (label, str(exc).splitlines()[0][:70]))
        return "refused"
    except REFUSALS as exc:
        print("  REFUSED (%-9s %-52s %s"
              % (type(exc).__name__ + ")", label, str(exc)[:66]))
        return "refused"
    except Exception as exc:
        print("  !! CRASHED         %-52s %s: %s"
              % (label, type(exc).__name__, str(exc)[:60]))
        return "crashed"
    print("  ** ALLOWED         %-52s -> %r" % (label, result))
    return "allowed"


def main():
    print("=" * 78)
    print("PROBE: can TradingView content reach computation?")
    print("=" * 78)

    outcomes = []

    print("\n1. The direct approach -- just ask for a machine use.")
    for purpose in ("automated trading", "risk check", "order verification",
                    "price referencing", "feeding the LLM a quote"):
        outcomes.append(attempt("assert_display_only_use(%r)" % purpose,
                                lambda p=purpose: tv.assert_display_only_use(p)))

    print("\n2. Is there an override? A flag, a kwarg, an env var?")
    outcomes.append(attempt("purpose='' (empty reason)",
                            lambda: tv.assert_display_only_use("")))
    outcomes.append(attempt("purpose=None",
                            lambda: tv.assert_display_only_use(None)))

    def try_override():
        return tv.assert_display_only_use("automated trading", permit=True)
    outcomes.append(attempt("permit=True kwarg", try_override))

    print("\n3. Flip the module-level verdict.")

    def flip_flag():
        tv.MACHINE_USE_PERMITTED = True
        # Even if the module global is writable, does anything DEPEND on it in a
        # way that unlocks a use? Re-test the wall afterwards.
        try:
            tv.assert_display_only_use("automated trading")
        finally:
            tv.MACHINE_USE_PERMITTED = False
        return "wall opened after flipping flag"
    outcomes.append(attempt("set MACHINE_USE_PERMITTED = True", flip_flag))

    print("\n4. Edit a mechanism record to claim machine usability.")
    outcomes.append(attempt("MECHANISMS['webhooks'].usable_for_machine_data=True",
                            lambda: setattr(tv.MECHANISMS["webhooks"],
                                            "usable_for_machine_data", True)))
    outcomes.append(attempt("del MECHANISMS['webhooks'].usable_for_machine_data",
                            lambda: delattr(tv.MECHANISMS["webhooks"],
                                            "usable_for_machine_data")))
    outcomes.append(attempt("MECHANISMS['webhooks'].note = ''",
                            lambda: setattr(tv.MECHANISMS["webhooks"], "note", "")))

    print("\n5. Inject a brand-new permissive mechanism.")

    def inject_via_mapping():
        import operator
        operator.setitem(tv.MECHANISMS, "secret_api",
                         tv.Mechanism("secret_api", "Secret", True, "outbound",
                                      False, "note"))
        return "injected into MECHANISMS"
    outcomes.append(attempt("MECHANISMS['secret_api'] = ...", inject_via_mapping))

    def construct_permissive():
        return tv.Mechanism("my_api", "My API", True, "outbound",
                            usable_for_machine_data=True,
                            note="I decided it is fine")
    outcomes.append(attempt("Mechanism(usable_for_machine_data=True)",
                            construct_permissive))

    def construct_unexplained():
        return tv.Mechanism("vague", "Vague", True, "outbound", False, note="")
    outcomes.append(attempt("Mechanism(note='') unexplained refusal",
                            construct_unexplained))

    def reregister():
        return tv._add(tv.Mechanism("webhooks", "Webhooks v2", True, "outbound",
                                    False, "replaced"))
    outcomes.append(attempt("_add() re-register 'webhooks'", reregister))

    outcomes.append(attempt("_add('not a mechanism')",
                            lambda: tv._add({"key": "fake"})))

    print("\n6. Mutate the prohibited-use list out from under the check.")
    # NOTE ON HOW *NOT* TO TEST THIS. The first version called
    # PROHIBITED_USES.clear() and .append(). A tuple has no such methods, so both
    # raised AttributeError -- a CRASH under the project convention, and a test of
    # Python trivia rather than of this module. It is the same mistake Phase 3
    # made with mappingproxy.__setitem__. The behaviour that actually matters is
    # item assignment, which a tuple refuses with TypeError -- a real refusal.
    import operator

    def assign_prohibited():
        operator.setitem(tv.PROHIBITED_USES, 0, "totally fine actually")
        return "overwrote a prohibited use"
    outcomes.append(attempt("PROHIBITED_USES[0] = ...", assign_prohibited))

    def assign_permitted():
        operator.setitem(tv.PERMITTED_USES, 0, "automated trading")
        return "widened the permitted list"
    outcomes.append(attempt("PERMITTED_USES[0] = ...", assign_permitted))

    # Rebinding the module global IS possible in Python -- no object can prevent
    # it. What matters is whether it buys anything: the wall must not consult a
    # mutable list to decide.
    def empty_the_list_then_retry():
        saved = tv.PROHIBITED_USES
        tv.PROHIBITED_USES = ()
        try:
            tv.assert_display_only_use("automated trading")
        finally:
            tv.PROHIBITED_USES = saved
        return "wall opened after emptying PROHIBITED_USES"
    outcomes.append(attempt("PROHIBITED_USES = () then retry",
                            empty_the_list_then_retry))

    print("\n7. Unknown mechanism -- is silence treated as permission?")
    outcomes.append(attempt("get_mechanism('desktop_local_api')",
                            lambda: tv.get_mechanism("desktop_local_api")))

    print("\n8. Invariants that must hold.")
    ok = True
    n_usable = len(tv.machine_usable_mechanisms())
    print("  machine_usable_mechanisms() -> %d (must be 0)" % n_usable)
    ok = ok and n_usable == 0
    print("  MACHINE_USE_PERMITTED       -> %r (must be False)"
          % tv.MACHINE_USE_PERMITTED)
    ok = ok and tv.MACHINE_USE_PERMITTED is False
    s = tv.review_summary()
    print("  review_summary n_mechanisms -> %d, n_machine_usable -> %d"
          % (s["n_mechanisms"], s["n_machine_usable"]))
    ok = ok and s["n_machine_usable"] == 0
    print("  mechanisms registered       -> %s" % ", ".join(sorted(tv.MECHANISMS)))

    print("\n" + "=" * 78)
    allowed = outcomes.count("allowed")
    crashed = outcomes.count("crashed")
    print("attempts=%d refused=%d ALLOWED=%d CRASHED=%d  invariants=%s"
          % (len(outcomes), outcomes.count("refused"), allowed, crashed,
             "OK" if ok else "BROKEN"))
    if allowed or crashed or not ok:
        print("RESULT: the wall has holes. Fix before proceeding.")
        return 1
    print("RESULT: every attempt was refused, and refused as a refusal "
          "(not a crash).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
