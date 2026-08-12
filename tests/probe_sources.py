"""
Adversarial probe of src/rag/sources.py -- a module that has never executed.

I am NOT trying to confirm it works. I am trying to find the way it is wrong,
because every module in this phase that I probed adversarially had a defect,
and an untested guard is exactly what the last twelve mutation survivors were.

Each probe states what would be WRONG, not what should be right.
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def show(label, fn):
    try:
        print("  %-52s -> %r" % (label, fn()))
    except Exception as e:  # noqa: BLE001
        print("  %-52s -> RAISED %s: %s" % (label, type(e).__name__, e))


def main():
    print("[import]")
    try:
        from rag import sources as S
    except Exception:  # noqa: BLE001
        print("  IMPORT FAILED -- the module has never been executed:")
        traceback.print_exc()
        return 1
    print("  imported OK")

    print("\n[registry shape]")
    show("len(SOURCES)", lambda: len(S.SOURCES))
    show("sorted keys", lambda: sorted(S.SOURCES))
    show("n enabled", lambda: len(S.enabled_sources()))
    show("n descoped", lambda: len(S.descoped_sources()))
    show("key matches dict key for all",
         lambda: all(k == v.key for k, v in S.SOURCES.items()))
    show("every source has a doc_url or a descope_reason",
         lambda: [s.key for s in S.SOURCES.values()
                  if not s.doc_url and not s.descope_reason])
    show("authority of sec_edgar_xbrl",
         lambda: S.SOURCES["sec_edgar_xbrl"].authority)
    show("authority of tsetmc", lambda: S.SOURCES["tsetmc"].authority)

    print("\n[check_access -- must REFUSE, matching the MEASURED HTTP codes]")
    show("edgar xbrl, no UA           (MEASURED 403)",
         lambda: S.check_access("sec_edgar_xbrl"))
    show("edgar xbrl, UA without '@'  (MEASURED 403)",
         lambda: S.check_access("sec_edgar_xbrl", user_agent="marfin-llm/0.1"))
    show("edgar xbrl, UA with contact (MEASURED 200)",
         lambda: S.check_access("sec_edgar_xbrl",
                                user_agent="marfin-llm/0.1 (me@example.com)").key)
    show("edgar submissions, empty-string UA",
         lambda: S.check_access("sec_edgar_submissions", user_agent=""))
    show("fred, no key                (MEASURED 400)",
         lambda: S.check_access("fred"))
    show("fred, empty-string key",
         lambda: S.check_access("fred", api_key=""))
    show("fred, whitespace-only key",
         lambda: S.check_access("fred", api_key="   "))
    show("fred, with key", lambda: S.check_access("fred", api_key="k").key)
    show("codal (descoped)", lambda: S.check_access("codal"))
    show("tsetmc (descoped)", lambda: S.check_access("tsetmc"))
    show("unregistered key", lambda: S.check_access("bloomberg"))
    show("get_source(unregistered)", lambda: S.get_source("bloomberg"))
    show("get_source(None)", lambda: S.get_source(None))

    print("\n[does a descoped source leak through the OTHER doors?]")
    show("codal in enabled_sources",
         lambda: any(s.key == "codal" for s in S.enabled_sources()))
    show("manifest lists codal at all",
         lambda: any(d["key"] == "codal" for d in S.manifest()["sources"]))
    show("manifest counts add to len(SOURCES)",
         lambda: (S.manifest()["n_enabled"] + S.manifest()["n_descoped"],
                  len(S.SOURCES)))

    print("\n[construction guards]")
    show("bad trust level refused",
         lambda: S.Source("x", "X", "u", "NOT_A_LEVEL"))
    show("Source has no __dict__ (slots honoured)",
         lambda: hasattr(S.SOURCES["fred"], "__dict__"))
    show("can I silently add an attribute?",
         lambda: setattr(S.SOURCES["fred"], "trust_level", "SELF_REPORTED"))

    print("\n[mutability of the registry]")
    show("SOURCES is a plain dict (writable)",
         lambda: type(S.SOURCES).__name__)
    show("manifest to_dict is a copy, not the object",
         lambda: S.manifest()["sources"][0] is not S.SOURCES)

    print("\n[AccessError type]")
    show("AccessError issubclass RuntimeError",
         lambda: issubclass(S.AccessError, RuntimeError))
    show("AccessError issubclass ValueError",
         lambda: issubclass(S.AccessError, ValueError))
    return 0


if __name__ == "__main__":
    sys.exit(main())
