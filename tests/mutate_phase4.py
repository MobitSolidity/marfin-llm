"""
Mutation battery for the Phase 4 harness core (scripts/phase4_lib.py).

WHY THIS BATTERY EXISTS
-----------------------
The user gets one evening on an i5-12400 to produce the project's first
on-target measurement. This module decides what that evening's output is
WORTH. Every other battery in this project protects a number a human will
read; this one protects the instrument that produces the numbers.

A grader is the worst possible place for an untested branch, because its
failure mode is silence. A grader that always returns True does not crash, does
not warn, and produces a results file that looks exactly like a real
measurement -- a file the user would then act on. The suite that guards this
module (tests/test_phase4_harness.py) drives the whole harness with a scripted
FAKE model that answers wrongly, fabricates, refuses when it should answer, and
answers a Persian question in English. These mutations verify that the suite
NOTICES each of those, rather than merely running to completion.

This battery already earned its place before it was finished. Building it
required reading every branch of grade_rag_case, and that reading is what
surfaced the two defects fixed on 2026-08-15: summarize_rag computed
persian_script per case and then discarded it, and the results file recorded
answers without the questions they answered.

ORACLE: test_phase4_harness.py alone. That suite carries both directions --
positive controls (a correct answer scores OK, a correct refusal scores OK, a
valid tool call scores schema-valid) and negative controls (a wrong figure is
MODEL_FAILURE, an invented figure is FABRICATION, an empty reply is not an
abstention). A mutation that makes the grader accept everything dies on the
negatives; one that makes it reject everything dies on the positives.

NOTE ON PATHS: unlike the other batteries in this directory, the module under
test lives in scripts/, not src/. SRC_ROOT is therefore the repo root and the
module paths are written relative to it.

Stdlib only.
"""

import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC_ROOT = ROOT

ORACLES = ("test_phase4_harness.py",)


def module_path(module):
    return os.path.join(SRC_ROOT, module)


# Empty, and it should stay that way. An "equivalent" mutation in a grader is
# a claim that some branch cannot affect any grade -- which is a claim that the
# branch is dead code. If one appears here, the honest fix is almost always to
# delete the branch, not to document the equivalence.
EQUIVALENT = {}

LIB = "scripts/phase4_lib.py"
RUN = "scripts/run_phase4.py"

# (module, description, find, replace)
MUTATIONS = [

    # -- Persian/Arabic digit folding ---------------------------------------
    # A grader blind to Persian numerals scores every Persian numeric answer as
    # a miss and blames the model for the grader's blindness.
    (LIB, "Persian digits are no longer folded to ASCII",
     "        i = _PERSIAN_DIGITS.find(ch)\n        if i >= 0:",
     "        i = _PERSIAN_DIGITS.find(ch)\n        if False:"),
    (LIB, "Arabic-Indic digits are no longer folded to ASCII",
     "        i = _ARABIC_DIGITS.find(ch)\n        if i >= 0:",
     "        i = _ARABIC_DIGITS.find(ch)\n        if False:"),
    (LIB, "digit folding maps every digit to zero",
     "            out.append(_ASCII_DIGITS[i])\n            continue\n"
     "        i = _ARABIC_DIGITS.find(ch)",
     "            out.append(_ASCII_DIGITS[0])\n            continue\n"
     "        i = _ARABIC_DIGITS.find(ch)"),

    # -- separator handling: the 10^3 error ---------------------------------
    # U+066B (decimal) and U+066C (thousands) are three orders of magnitude
    # apart. src/calc/persian_num.py refuses ambiguous input for this reason.
    (LIB, "the Arabic decimal separator is treated as a thousands separator",
     '_DECIMAL_SEPARATORS = (".", "\\u066b")',
     '_DECIMAL_SEPARATORS = (".",)'),
    (LIB, "the Arabic thousands separator is dropped from the grouping set",
     '_THOUSANDS_SEPARATORS = (",", "\\u066c", "\\u2009", "\\u00a0", "_")',
     '_THOUSANDS_SEPARATORS = (",",)'),
    # Retargeted 2026-08-15: this logic used to be duplicated in both
    # extractors and now lives once in _normalise_separators -- which is the
    # fix that killed the "_DECIMAL_SEPARATORS is dead" survivor.
    (LIB, "grouping separators are stripped anywhere, not only between digits",
     '        folded = re.sub(r"(?<=\\d)" + re.escape(sep) + r"(?=\\d\\d\\d(?!\\d))",\n'
     '                        "", folded)\n'
     "    return folded",
     '        folded = folded.replace(sep, "")\n'
     "    return folded"),
    # This is the ORIGINAL defect, restated: a hard-coded replace instead of a
    # loop over the table. It is indistinguishable from the correct code for
    # the two separators the table holds today, so it is killed by a probe that
    # injects a third one at runtime -- see the test. Without that probe this
    # would be a true equivalent mutant, and the equivalence would dissolve
    # silently the day a separator is added.
    (LIB, "the decimal separator table is bypassed by a hard-coded replace",
     "    for sep in _DECIMAL_SEPARATORS:\n"
     '        if sep != ".":\n'
     "            folded = folded.replace(sep, \".\")",
     '    folded = folded.replace("\\u066b", ".")'),
    (LIB, "decimal separators are treated as grouping separators (10^3 error)",
     "    for sep in _DECIMAL_SEPARATORS:\n"
     '        if sep != ".":\n'
     "            folded = folded.replace(sep, \".\")",
     "    for sep in _DECIMAL_SEPARATORS:\n"
     '        if sep != ".":\n'
     "            folded = folded.replace(sep, \"\")"),

    # -- scale words: the 10^6 error ----------------------------------------
    # This is the defect the suite actually found on 2026-08-15.
    (LIB, "extract_magnitudes ignores the trailing scale word",
     "        sm = _SCALE_RE.match(folded[m.end():m.end() + 24])\n"
     "        if sm:",
     "        sm = _SCALE_RE.match(folded[m.end():m.end() + 24])\n"
     "        if False:"),
    (LIB, "a scale word DIVIDES instead of multiplying",
     "            value *= SCALE_WORDS[sm.group(1).lower()]",
     "            value /= SCALE_WORDS[sm.group(1).lower()]"),
    (LIB, "the scale table is redeclared locally instead of imported",
     "from rag.ingest import SCALE_WORDS  # noqa: E402",
     'SCALE_WORDS = {"million": 1e6, "billion": 1e9}  # noqa: E402'),
    # MEASURED 2026-08-15: reversing the alternation order is NOT a mutation.
    # \b makes it irrelevant -- " millions" matches as "millions" under both
    # longest-first and shortest-first ordering, because \b forbids stopping at
    # the "million" prefix. The mutation was wrong, not the tests. Replaced
    # with the one that actually removes the protection: dropping \b, which
    # lets "millions" be read as "million" and loses nothing visibly while
    # being a real semantic difference in the pattern's guarantee.
    (LIB, "the scale regex drops the word boundary, so 'millions' reads as "
          "'million'",
     "                               key=len, reverse=True)) + r\")\\b\",",
     "                               key=len, reverse=True)) + r\")\","),
    (LIB, "the scale word need not follow the number immediately",
     '    r"^\\s*(" + "|".join(sorted((re.escape(w) for w in SCALE_WORDS),',
     '    r".*?(" + "|".join(sorted((re.escape(w) for w in SCALE_WORDS),'),

    # -- value matching: the gate itself ------------------------------------
    (LIB, "value_matches accepts any answer at all",
     "    for n in found:\n"
     "        if abs(n - float(expected)) <= tol:\n"
     "            return True\n"
     "    return False",
     "    for n in found:\n"
     "        if abs(n - float(expected)) <= tol:\n"
     "            return True\n"
     "    return True"),
    (LIB, "value_matches rejects every answer",
     "        if abs(n - float(expected)) <= tol:\n"
     "            return True",
     "        if abs(n - float(expected)) <= tol:\n"
     "            return False"),
    (LIB, "tolerance is reinterpreted as RELATIVE, widening every gate",
     "    tol = 0.0 if tolerance is None else abs(float(tolerance))",
     "    tol = 0.0 if tolerance is None else abs(float(tolerance)) "
     "* max(1.0, abs(float(expected)))"),
    (LIB, "a missing tolerance becomes generous instead of exact",
     "    tol = 0.0 if tolerance is None else abs(float(tolerance))",
     "    tol = 1.0 if tolerance is None else abs(float(tolerance))"),
    (LIB, "value_matches silently passes when expected is None",
     "    if expected is None:\n"
     "        raise ValueError(",
     "    if expected is None:\n"
     "        return True\n"
     "    if False:\n"
     "        raise ValueError("),
    (LIB, "the eval arm applies scale words it must not (a P/E of 17.857M)",
     "    found = extract_magnitudes(text) if scaled else extract_numbers(text)",
     "    found = extract_magnitudes(text)"),
    (LIB, "the RAG arm ignores scale words (the 10^6 error returns)",
     "    found = extract_magnitudes(text) if scaled else extract_numbers(text)",
     "    found = extract_numbers(text)"),

    # -- abstention detection: the most dangerous grader in the file --------
    (LIB, "every reply counts as an abstention",
     "    t = text.strip().lower()\n"
     "    if not t:\n"
     "        return False",
     "    t = text.strip().lower()\n"
     "    if not t:\n"
     "        return False\n"
     "    return True"),
    (LIB, "no reply ever counts as an abstention",
     "    for p in _ABSTAIN_EN:\n"
     "        if p in t:\n"
     "            return True",
     "    for p in _ABSTAIN_EN:\n"
     "        if p in t:\n"
     "            return False"),
    (LIB, "an EMPTY reply is credited as a principled refusal",
     "    t = text.strip().lower()\n"
     "    if not t:\n"
     "        return False",
     "    t = text.strip().lower()\n"
     "    if not t:\n"
     "        return True"),
    (LIB, "a None reply is credited as a refusal",
     "    if text is None:\n"
     "        return False",
     "    if text is None:\n"
     "        return True"),
    (LIB, "Persian refusals are no longer recognised",
     "    for p in _ABSTAIN_FA:\n"
     "        if p in text:",
     "    for p in _ABSTAIN_FA:\n"
     "        if False:"),
    # REMOVED as a genuine equivalent, MEASURED 2026-08-15: matching the
    # Persian phrases against `t` (the .lower()ed text) instead of `text`
    # cannot change any verdict, because .lower() alters none of the 11
    # phrases -- Arabic script has no case mapping. Documenting it in
    # EQUIVALENT would be the wrong call: an equivalence that only holds while
    # the phrase list stays free of Latin characters would dissolve silently
    # the day someone adds one. The mutation is simply not a mutation.

    # -- banned phrases (`must_not`) ----------------------------------------
    (LIB, "must_not phrases are never detected",
     "    return [b for b in (banned or []) if b.lower() in t]",
     "    return []"),
    (LIB, "must_not matching becomes case-SENSITIVE",
     "    t = (text or \"\").lower()\n"
     "    return [b for b in (banned or []) if b.lower() in t]",
     "    t = (text or \"\")\n"
     "    return [b for b in (banned or []) if b in t]"),

    # -- tool-call parsing ---------------------------------------------------
    (LIB, "malformed tool JSON is counted as a successful call",
     "        except (ValueError, TypeError):\n"
     "            malformed += 1\n"
     "            continue",
     "        except (ValueError, TypeError):\n"
     "            malformed += 1\n"
     "            obj = {\"name\": \"unknown\"}"),
    (LIB, "a nameless tool call is accepted",
     "        if not isinstance(obj, dict) or not obj.get(\"name\"):\n"
     "            malformed += 1\n"
     "            continue",
     "        if not isinstance(obj, dict) or not obj.get(\"name\"):\n"
     "            malformed += 1"),
    (LIB, "non-dict arguments are accepted as a valid call",
     "        if not isinstance(args, dict):\n"
     "            malformed += 1\n"
     "            continue",
     "        if not isinstance(args, dict):\n"
     "            malformed += 1\n"
     "            args = {}"),
    # The original form of this mutation appended `_ = malformed`, which is
    # inert -- a NO-OP dressed as a mutation, and the sixth one written in this
    # project. This version actually suppresses the count.
    (LIB, "the malformed counter is reported as zero",
     "    return calls, malformed",
     "    return calls, 0"),

    # -- schema validation ---------------------------------------------------
    (LIB, "an unknown tool name passes schema validation",
     "    if spec is None:\n"
     "        return False, \"unknown_tool:%s\" % name",
     "    if spec is None:\n"
     "        return True, \"\""),
    (LIB, "missing required arguments pass schema validation",
     "    if missing:\n"
     "        return False, \"missing_argument:%s\" % \",\".join(sorted(missing))",
     "    if missing:\n"
     "        return True, \"\""),
    (LIB, "unknown arguments pass schema validation",
     "    if extra:\n"
     "        return False, \"unknown_argument:%s\" % \",\".join(sorted(extra))",
     "    if extra:\n"
     "        return True, \"\""),
    (LIB, "every call is schema-valid regardless of its shape",
     "    missing = [r for r in required if r not in args]",
     "    missing = []\n    required = []\n    props = dict(props, **args)"),

    # -- eval case grading ---------------------------------------------------
    (LIB, "human_grade is auto-filled as a pass",
     '        "human_grade": None,\n'
     '        "rubric": case.get("rubric", ""),',
     '        "human_grade": True,\n'
     '        "rubric": case.get("rubric", ""),'),
    (LIB, "banned phrases no longer void a correct-looking abstention",
     '        g["abstention_ok"] = bool(g["abstained"]) and not g["banned_hits"]',
     '        g["abstention_ok"] = bool(g["abstained"])'),
    (LIB, "an unknown category is silently treated as answer-expected",
     '        g["should_abstain"] = None\n'
     '        g["abstention_ok"] = None\n'
     '        g["warning"] = "unknown category %r; not graded for abstention" % cat',
     '        g["should_abstain"] = False\n'
     '        g["abstention_ok"] = None'),
    (LIB, "an abstention category is graded as if it expected an answer",
     "    if cat in ABSTAIN_CATEGORIES:\n"
     '        g["should_abstain"] = True',
     "    if cat in ABSTAIN_CATEGORIES:\n"
     '        g["should_abstain"] = False'),
    (LIB, "expected_value is ignored, as run_baseline.py ignored it",
     '    if case.get("expected_value") is not None:\n'
     '        g["value_expected"] = case["expected_value"]',
     '    if False:\n'
     '        g["value_expected"] = case["expected_value"]'),
    (LIB, "expected_tool is ignored, as run_baseline.py ignored it",
     "    if want_tool:\n"
     '        g["tool_expected"] = want_tool',
     "    if False:\n"
     '        g["tool_expected"] = want_tool'),
    (LIB, "tool_ok is true whenever ANY tool was called",
     '        g["tool_ok"] = want_tool in g["tool_calls"]',
     '        g["tool_ok"] = bool(g["tool_calls"])'),
    (LIB, "a Persian case is not checked for Persian script",
     '    if case.get("lang") == "fa":\n'
     '        g["persian_script"] = is_persian_script(text)\n'
     '        g["latin_ratio"] = round(latin_ratio(text), 3)',
     '    if False:\n'
     '        g["persian_script"] = is_persian_script(text)\n'
     '        g["latin_ratio"] = round(latin_ratio(text), 3)'),
    (LIB, "empty output is not flagged",
     '        "empty_output": not text.strip(),\n'
     '        "banned_hits": contains_banned(text, case.get("must_not")),',
     '        "empty_output": False,\n'
     '        "banned_hits": contains_banned(text, case.get("must_not")),'),

    # -- RAG grading: task 6, failure attribution ----------------------------
    (LIB, "retrieval_hit is true even when no gold document was retrieved",
     "    return bool(set(gold_doc_ids or []) & set(retrieved_doc_ids or []))",
     "    return True"),
    (LIB, "retrieval_hit is never true",
     "    return bool(set(gold_doc_ids or []) & set(retrieved_doc_ids or []))",
     "    return False"),
    (LIB, "a retrieval failure is reported as a model failure",
     '        if not g["retrieval_ok"]:\n'
     '            g["outcome"] = "RETRIEVAL_FAILURE"',
     '        if not g["retrieval_ok"]:\n'
     '            g["outcome"] = "MODEL_FAILURE"'),
    (LIB, "a wrong answer on retrieved evidence is reported as OK",
     '            g["outcome"] = "MODEL_FAILURE"',
     '            g["outcome"] = "OK"'),
    (LIB, "over-abstention is reported as a clean pass",
     '            g["outcome"] = "OVER_ABSTENTION"',
     '            g["outcome"] = "OK"'),
    (LIB, "fabrication on an unanswerable question is never flagged",
     '        g["fabricated"] = (not g["abstained"]) and bool(extract_numbers(text))',
     '        g["fabricated"] = False'),
    (LIB, "any non-abstention on an unanswerable question counts as fabrication",
     '        g["fabricated"] = (not g["abstained"]) and bool(extract_numbers(text))',
     '        g["fabricated"] = not g["abstained"]'),
    (LIB, "an unanswerable question that is answered is scored OK",
     '        g["outcome"] = "OK" if g["abstained"] else (\n'
     '            "FABRICATION" if g["fabricated"] else "NON_ANSWER")',
     '        g["outcome"] = "OK"'),
    (LIB, "the RAG value gate uses a tolerance wide enough to pass anything",
     "        tol = max(abs(mag) * 1e-6, 0.5)",
     "        tol = max(abs(mag) * 1e-1, 0.5)"),
    (LIB, "the RAG value gate is skipped entirely",
     "    if answerable and mag is not None:",
     "    if False:"),
    (LIB, "a Persian RAG answer is not checked for Persian script",
     '    if gold.get("lang") == "fa":\n'
     '        g["persian_script"] = is_persian_script(text)',
     '    if False:\n'
     '        g["persian_script"] = is_persian_script(text)'),

    # -- threshold grading ---------------------------------------------------
    # run_baseline.py hard-coded 12.0 against an approved 6.0.
    (LIB, "an ABSENT measurement is graded as a PASS",
     '    if measured is None:\n'
     '        return {"threshold": name, "limit": limit, "measured": None,\n'
     '                "direction": direction, "verdict": "PENDING",\n'
     '                "label": "UNKNOWN"}',
     '    if measured is None:\n'
     '        return {"threshold": name, "limit": limit, "measured": None,\n'
     '                "direction": direction, "verdict": "PASS",\n'
     '                "label": "MEASURED"}'),
    (LIB, "a PENDING verdict is labelled MEASURED",
     '                "direction": direction, "verdict": "PENDING",\n'
     '                "label": "UNKNOWN"}',
     '                "direction": direction, "verdict": "PENDING",\n'
     '                "label": "MEASURED"}'),
    (LIB, "min and max thresholds are compared the wrong way round",
     '    if direction == "min":\n'
     "        ok = measured >= limit\n"
     "    else:\n"
     "        ok = measured <= limit",
     '    if direction == "min":\n'
     "        ok = measured <= limit\n"
     "    else:\n"
     "        ok = measured >= limit"),
    (LIB, "every threshold passes",
     '            "direction": direction, "verdict": "PASS" if ok else "FAIL",',
     '            "direction": direction, "verdict": "PASS",'),
    (LIB, "an unregistered threshold name is graded instead of refused",
     "    if direction is None:\n"
     '        raise ValueError("no direction registered for threshold %r" % (name,))',
     "    if direction is None:\n"
     '        direction = "max"'),
    (LIB, "the RSS ceiling direction is flipped to min",
     '    "peak_rss_8k_gib_max": "max",',
     '    "peak_rss_8k_gib_max": "min",'),
    (LIB, "the decode-speed floor direction is flipped to max",
     '    "generation_tokens_per_sec_min": "min",',
     '    "generation_tokens_per_sec_min": "max",'),
    (LIB, "the fabrication ceiling direction is flipped",
     '    "fabricated_financial_data_count_max": "max",',
     '    "fabricated_financial_data_count_max": "min",'),

    # -- threshold LOADING: the approval marker ------------------------------
    (LIB, "thresholds are graded even when the APPROVED marker is gone",
     '    if "APPROVED" not in str(th.get("status", "")):\n'
     "        raise ValueError(",
     '    if False:\n'
     "        raise ValueError("),
    (LIB, "a state file with no thresholds is accepted",
     "    if not th:\n"
     "        raise ValueError(",
     "    if False:\n"
     "        raise ValueError("),
    (LIB, "unregistered keys leak into the graded threshold set",
     "    return {k: v for k, v in th.items() if k in THRESHOLD_DIRECTION}",
     "    return dict(th)"),

    # -- percentages: the 0/0 trap -------------------------------------------
    (LIB, "0/0 is reported as a perfect 100%",
     "    if not denominator:\n"
     "        return None",
     "    if not denominator:\n"
     "        return 100.0"),
    (LIB, "0/0 is reported as zero",
     "    if not denominator:\n"
     "        return None",
     "    if not denominator:\n"
     "        return 0.0"),

    # -- summaries -----------------------------------------------------------
    (LIB, "malformed calls are excluded from the schema-validity denominator",
     "    attempted = total_calls + total_malformed",
     "    attempted = total_calls"),
    (LIB, "the abstention denominator counts every case, inflating the rate",
     '    abst = [g for g in grades if g.get("should_abstain") is True]',
     "    abst = list(grades)"),
    (LIB, "the calc-correctness denominator counts every case",
     '    calc = [g for g in grades if g.get("value_expected") is not None]',
     "    calc = list(grades)"),
    (LIB, "wrong-script Persian answers are not counted in the eval summary",
     '    fa_wrong_script = [g for g in fa if g.get("persian_script") is False]',
     "    fa_wrong_script = []"),
    (LIB, "wrong-script Persian answers are dropped from the RAG summary",
     '        "fa_not_in_persian": len(\n'
     '            [g for g in grades if g.get("persian_script") is False]),',
     '        "fa_not_in_persian": 0,'),
    (LIB, "the fabrication count in the RAG summary is hard-zeroed",
     '        "fabricated_financial_data_count": len(\n'
     '            [g for g in grades if g.get("fabricated")]),',
     '        "fabricated_financial_data_count": 0,'),
    (LIB, "unsupported citations are counted as supported",
     '    unsupported = [c for c in cited if c.get("status") != "SUPPORTED"]',
     "    unsupported = []"),
    (LIB, "every citation is counted as supported",
     '    supported = [c for c in cited if c.get("status") == "SUPPORTED"]',
     "    supported = list(cited)"),
    # The obvious mutation here -- swapping `answerable` for `grades` in the
    # NUMERATOR -- is equivalent by construction, MEASURED 2026-08-15: an
    # unanswerable case carries retrieval_ok=None, which is falsy, so it can
    # never enter the numerator and the denominator is len(answerable) either
    # way. What actually protects the rate is the guard in grade_rag_case that
    # sets retrieval_ok=None for unanswerable cases. Attack THAT instead: it is
    # the load-bearing part, and it is testable.
    (LIB, "an unanswerable case is given a real retrieval verdict",
     "    g[\"retrieval_ok\"] = (retrieval_hit(gold.get(\"gold_doc_ids\"),\n"
     "                                       retrieved_doc_ids)\n"
     "                         if answerable else None)",
     "    g[\"retrieval_ok\"] = retrieval_hit(gold.get(\"gold_doc_ids\"),\n"
     "                                      retrieved_doc_ids)"),
    (LIB, "the retrieval-hit DENOMINATOR counts unanswerable cases too",
     "        \"retrieval_hit_pct\": pct(len(retr_ok), len(answerable)),",
     "        \"retrieval_hit_pct\": pct(len(retr_ok), len(grades)),"),

    # -- Windows console safety ---------------------------------------------
    # MEASURED: Persian text cannot be encoded to cp1252/cp437. The user's
    # machine is Windows 11; a crash here loses the evening's run.
    (LIB, "safe() stops replacing unencodable characters",
     "def safe(text):",
     "def safe(text):\n    return text\n\ndef _safe_unused(text):"),

    # -- the runner: the results file itself ---------------------------------
    (RUN, "the plain arm stops recording the question it asked",
     '        g["question"] = c["prompt"]\n'
     '        g["output"] = text\n'
     '        g["metrics"] = m\n'
     "        out.append(g)\n"
     '        p("  %-14s %-20s %5.1fs %s" % (',
     '        g["output"] = text\n'
     '        g["metrics"] = m\n'
     "        out.append(g)\n"
     '        p("  %-14s %-20s %5.1fs %s" % ('),
    (RUN, "the RAG arm stops recording the question it asked",
     '        g["question"] = gold["query"]',
     '        g["question"] = ""'),
    (RUN, "the results file is written as escaped ASCII, unreadable in Persian",
     "ensure_ascii=False",
     "ensure_ascii=True"),
    (RUN, "citations are verified against the GOLD passage, not the shown one",
     "        if text.strip() and not L.is_abstention(text):",
     "        if False:"),

    # -- the runner: the printed report --------------------------------------
    # This report is the FIRST thing the user sees when the run ends on their
    # own machine, and for most of its life it was entirely unasserted: the
    # suite read the JSON file and ignored the console. These six mutations
    # break the report while leaving the JSON perfect, which is precisely the
    # failure the old suite could not see.
    (RUN, "the verdict column is dropped from the threshold table",
     '        p("  %-8s %-42s limit %-8s measured %s"\n'
     '          % (v["verdict"], v["threshold"], v["limit"],',
     '        p("  %-8s %-42s limit %-8s measured %s"\n'
     '          % ("", v["threshold"], v["limit"],'),
    (RUN, "the threshold table prints nothing at all",
     "    for v in verdicts:\n"
     '        p("  %-8s %-42s limit %-8s measured %s"',
     "    for v in []:\n"
     '        p("  %-8s %-42s limit %-8s measured %s"'),
    (RUN, "the tally counts PENDING verdicts as passes",
     '    n_pend = len([v for v in verdicts if v["verdict"] == "PENDING"])',
     "    n_pend = 0"),
    (RUN, "the tally counts FAIL verdicts as passes",
     '    n_fail = len([v for v in verdicts if v["verdict"] == "FAIL"])',
     "    n_fail = 0"),
    (RUN, "the report omits the notice that a human has not graded it",
     '    p("carries human_grade=null and must be read by a person before '
     'Phase 4")',
     '    p("")'),
    (RUN, "only the failing thresholds are printed, hiding the passing ones",
     "    for v in verdicts:",
     '    for v in [x for x in verdicts if x["verdict"] == "FAIL"]:'),

    # -- model identity ------------------------------------------------------
    # The downloadable GGUF is the ORIGINAL Qwen3-4B; the pinned
    # Qwen3-4B-Instruct-2507 publishes none (VERIFIED 2026-08-16). So the
    # results file must say which weights produced its numbers. Every mutation
    # here makes the file claim provenance it does not have.
    (LIB, "an unidentified model file is reported as VERIFIED",
     '        return {"sha256": digest, "label": "UNKNOWN",',
     '        return {"sha256": digest, "label": "VERIFIED",'),
    (LIB, "an unidentified model is claimed to BE the pinned revision",
     '                "is_pinned_revision": None,\n'
     '                "note": "This file is not one of the artefacts verified',
     '                "is_pinned_revision": True,\n'
     '                "note": "This file is not one of the artefacts verified'),
    (LIB, "the known-artefact table claims the file IS the pinned revision",
     '        "is_pinned_revision": False,\n'
     '        "note": "ORIGINAL Qwen3-4B',
     '        "is_pinned_revision": True,\n'
     '        "note": "ORIGINAL Qwen3-4B'),
    (LIB, "a recognised artefact is reported as UNKNOWN anyway",
     '    out = {"sha256": digest, "label": "VERIFIED"}\n'
     "    out.update(known)",
     '    out = {"sha256": digest, "label": "UNKNOWN"}\n'
     "    out.update(known)"),
    (LIB, "the recorded byte size of the verified artefact is wrong",
     '        "size_bytes": 2497280256,',
     '        "size_bytes": 4897280256,'),
    (LIB, "the hash is computed over only the first chunk of the file",
     "        while True:\n"
     "            block = f.read(chunk)\n"
     "            if not block:\n"
     "                break\n"
     "            h.update(block)",
     "        h.update(f.read(chunk))"),
    (RUN, "the results file stops recording which weights were used",
     '                  "identity": model_identity},',
     "                  },"),
]


def run_oracle(name):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(
        [os.path.join(ROOT, "src"), os.path.join(ROOT, "scripts"),
         env.get("PYTHONPATH", "")])
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, name)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode == 0, proc.stdout.decode("utf-8", "replace")


def run_tests():
    for name in ORACLES:
        ok, out = run_oracle(name)
        if not ok:
            return False, "%s FAILED\n%s" % (name, out[-2000:])
    return True, ""


def main():
    for dirpath, dirnames, _ in os.walk(ROOT):
        for d in list(dirnames):
            if d == "__pycache__":
                shutil.rmtree(os.path.join(dirpath, d), ignore_errors=True)

    ok, out = run_tests()
    if not ok:
        print("ABORT: the oracle fails BEFORE any mutation is applied.")
        print(out[-3000:])
        return 1
    print("baseline: oracle passes (%s), %d mutations to apply\n"
          % (", ".join(ORACLES), len(MUTATIONS)))

    backup = tempfile.mkdtemp(prefix="phase4_orig_")
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
                skipped += 1
                skips.append("%s: %s (NO-OP)" % (module, desc))
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
    print("  source restored and oracle green: %s" % intact)
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
