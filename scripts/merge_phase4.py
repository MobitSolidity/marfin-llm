#!/usr/bin/env python3
"""
Merge per-arm Phase 4 result files into one payload.

WHY THIS EXISTS
---------------
scripts/run_phase4.py writes its output file ONCE, at the very end (a single
open(out_path, "w") after every arm has run). On a CPU-only box the full three
arm run is ~3.4 hours, so a Ctrl+C or a reboot in hour three loses everything.
--arms exists precisely to split that ("comma-separated subset, for resuming a
run"), but each invocation then produces a SEPARATE file, and those files are
not trivially concatenable:

  * `latency` is re-measured per invocation (a TTFT probe plus a 128-token
    decode probe, MEASURED at 148 s per command on the user's machine). Three
    files therefore hold three DIFFERENT latency measurements of the same
    machine. Averaging them would invent a number nobody measured; picking one
    silently would hide the spread.
  * `threshold_verdicts` is computed from whichever arms ran. A verdict computed
    over the rag arm alone is not the verdict for the run.
  * `peak_rss_gib` is a per-process maximum. The true peak across three
    processes is the max, never the sum.
  * `model.answers_lost_to_thinking_truncation` and `thinking_replies` are
    per-process counters and DO add up.

This script does the honest thing with each of those, and refuses rather than
guesses. It recomputes nothing that requires the model; verdicts stay PENDING
with an explicit reason, because a verdict is a claim and this script cannot
measure.

USAGE
    python scripts/merge_phase4.py FILE [FILE ...] --out merged.json
"""
import argparse
import json
import os
import sys

ARMS = ("plain", "tools", "rag")


def p(s=""):
    sys.stdout.write(str(s) + "\n")


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def merge(paths):
    """
    Return (payload, problems). `problems` is a list of strings; a non-empty
    list means the caller must NOT treat the payload as a measurement.
    """
    docs = []
    problems = []
    for path in paths:
        if not os.path.isfile(path):
            problems.append("missing file: %s" % path)
            continue
        try:
            docs.append((path, load(path)))
        except Exception as exc:                      # noqa: BLE001
            problems.append("unreadable JSON in %s: %s" % (path, exc))
    if not docs:
        return None, problems or ["no input files"]

    # ---- refuse to merge files that did not come from the same run --------
    # Different weights, context size or token budget produce numbers that are
    # not comparable. Merging them would fabricate a run that never happened.
    def sig(d):
        m = d.get("model", {}) or {}
        ident = m.get("identity") or {}
        return (
            m.get("file"),
            m.get("ctx"),
            m.get("threads"),
            m.get("max_tokens"),
            m.get("tool_call_cap"),
            ident.get("sha256") if isinstance(ident, dict) else None,
        )

    sigs = {}
    for path, d in docs:
        sigs.setdefault(sig(d), []).append(os.path.basename(path))
    if len(sigs) > 1:
        problems.append(
            "inputs disagree on (model, ctx, threads, max_tokens, cap, sha256); "
            "these are NOT arms of one run: %s"
            % json.dumps({str(k): v for k, v in sigs.items()},
                         ensure_ascii=False))

    # ---- arms: union, and a duplicate is a conflict, not a merge ----------
    arms = {}
    arm_source = {}
    for path, d in docs:
        for arm, cases in (d.get("arms") or {}).items():
            if arm in arms:
                problems.append(
                    "arm %r appears in both %s and %s; refusing to choose "
                    "between two measurements of the same arm"
                    % (arm, arm_source[arm], os.path.basename(path)))
                continue
            arms[arm] = cases
            arm_source[arm] = os.path.basename(path)

    summaries = {}
    summary_source = {}
    for path, d in docs:
        for arm, s in (d.get("summaries") or {}).items():
            if arm in summaries:
                problems.append(
                    "summary %r appears in both %s and %s"
                    % (arm, summary_source[arm], os.path.basename(path)))
                continue
            summaries[arm] = s
            summary_source[arm] = os.path.basename(path)

    missing = [a for a in ARMS if a not in arms]
    # A MISSING ARM IS A PROBLEM, NOT A FOOTNOTE. Found by adversarial test
    # 2026-08-24: merging the rag file alone printed "arms MISSING: plain,
    # tools" and then, two lines later, "No problems detected. All three arms
    # present" with exit 0. An incomplete run that exits 0 is exactly the class
    # of silence this project has been bitten by twice (a printed SKIP that
    # failed nothing; a printed truncation that graded nothing). Recorded in
    # `problems` so `complete` goes False and the exit code goes non-zero.
    if missing:
        problems.append(
            "arms missing from the merge: %s. This file describes %d of %d "
            "arms and is not a complete run; no threshold may be graded from it"
            % (", ".join(missing), len(arms), len(ARMS)))

    # ---- latency: keep EVERY measurement, publish the spread -------------
    lats = [{"source": os.path.basename(path), **(d.get("latency") or {})}
            for path, d in docs if d.get("latency")]
    tps = [l.get("decode_tokens_per_sec") for l in lats
           if isinstance(l.get("decode_tokens_per_sec"), (int, float))]
    ttfts = [l.get("ttft_seconds") for l in lats
             if isinstance(l.get("ttft_seconds"), (int, float))]

    # ---- peak RSS: a maximum, never a sum --------------------------------
    peaks = [(d.get("peak_rss_gib"), d.get("peak_rss_label"),
              os.path.basename(path))
             for path, d in docs]
    numeric_peaks = [x for x in peaks if isinstance(x[0], (int, float))]
    if numeric_peaks:
        peak_val, peak_lab, peak_src = max(numeric_peaks, key=lambda x: x[0])
    else:
        peak_val, peak_lab, peak_src = None, "UNKNOWN", None
    if len(numeric_peaks) != len(peaks):
        problems.append(
            "%d of %d inputs report no numeric peak RSS; the merged peak is "
            "the max of those that do, so it is a LOWER BOUND"
            % (len(peaks) - len(numeric_peaks), len(peaks)))

    # ---- per-process counters that genuinely add ------------------------
    def csum(key):
        vals = [(d.get("model") or {}).get(key) for _, d in docs]
        nums = [v for v in vals if isinstance(v, int)]
        return sum(nums) if len(nums) == len(vals) else None

    base_model = dict((docs[0][1].get("model") or {}))
    base_model["thinking_replies"] = csum("thinking_replies")
    base_model["answers_lost_to_thinking_truncation"] = \
        csum("answers_lost_to_thinking_truncation")
    base_model["load_seconds_per_invocation"] = [
        (d.get("model") or {}).get("load_seconds") for _, d in docs]
    base_model.pop("load_seconds", None)

    payload = {
        # NOT "MEASURED". Every number inside was measured, but the file itself
        # is an assembly, and a reader must be able to see that from the label
        # alone rather than having to find this script.
        "label": "MEASURED_PER_ARM_MERGED",
        "phase": 4,
        "route": "A (user's own machine), run in per-arm chunks",
        "merged_from": [
            {"file": os.path.basename(path),
             "timestamp": d.get("timestamp"),
             "arms": sorted((d.get("arms") or {}).keys())}
            for path, d in docs],
        "timestamp": max((d.get("timestamp") or "") for _, d in docs) or None,
        "host": docs[0][1].get("host"),
        "model": base_model,
        "tool_registry_size": docs[0][1].get("tool_registry_size"),

        # THE HONEST FORM. Three invocations measured latency three times. The
        # merged file publishes all three plus the observed range, and states
        # that no single value is "the" latency of the run.
        "latency_per_invocation": lats,
        "latency_spread": {
            "decode_tokens_per_sec_min": min(tps) if tps else None,
            "decode_tokens_per_sec_max": max(tps) if tps else None,
            "ttft_seconds_min": min(ttfts) if ttfts else None,
            "ttft_seconds_max": max(ttfts) if ttfts else None,
            "n_measurements": len(lats),
            "note": "Each --arms invocation re-measures latency. These are "
                    "repeated measurements of one machine, not of one run. No "
                    "single value is promoted to 'the' latency here.",
        },

        "peak_rss_gib": peak_val,
        "peak_rss_label": peak_lab,
        "peak_rss_note": (
            "MAX across %d invocations (source: %s). Peak RSS is a per-process "
            "maximum; summing it would report memory that was never "
            "simultaneously resident." % (len(peaks), peak_src)),

        "thresholds_approved": docs[0][1].get("thresholds_approved"),

        # Deliberately NOT copied from any input. A verdict computed over a
        # subset of arms is not the run's verdict, and this script has no model
        # with which to recompute one.
        "threshold_verdicts": None,
        "threshold_verdicts_status": {
            "status": "PENDING",
            "reason": "Verdicts in a per-arm file were computed over that arm "
                      "only. This script does not recompute them, because "
                      "recomputation needs the aggregate metrics that "
                      "run_phase4.py derives while the model is loaded. Grade "
                      "the merged summaries deliberately; do not inherit a "
                      "subset's verdict.",
            "per_arm_verdicts_as_measured": {
                os.path.basename(path): d.get("threshold_verdicts")
                for path, d in docs},
        },

        "summaries": summaries,
        "arms": arms,
        "arms_present": sorted(arms.keys()),
        "arms_missing": missing,
        "complete": not missing and not problems,
        "human_grading": {
            "status": "PENDING",
            "note": "Persian fluency, rubric compliance and unsupported-claim "
                    "judgement require a human reader (R10). No field in this "
                    "file records a human grade.",
        },
        "merge_problems": problems,
        "generated_by": "scripts/merge_phase4.py",
    }
    return payload, problems


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Merge per-arm Phase 4 result files")
    ap.add_argument("inputs", nargs="+", help="per-arm JSON files")
    ap.add_argument("--out", default="evals/results/phase4_merged.json")
    a = ap.parse_args(argv)

    payload, problems = merge(a.inputs)
    if payload is None:
        for x in problems:
            p("ERROR: %s" % x)
        return 2

    d = os.path.dirname(os.path.abspath(a.out))
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    p("Merged %d file(s) -> %s" % (len(a.inputs), a.out))
    p("  arms present : %s" % ", ".join(payload["arms_present"]))
    if payload["arms_missing"]:
        p("  arms MISSING : %s" % ", ".join(payload["arms_missing"]))
    ls = payload["latency_spread"]
    p("  decode tok/s : %s .. %s across %d measurement(s)"
      % (ls["decode_tokens_per_sec_min"], ls["decode_tokens_per_sec_max"],
         ls["n_measurements"]))
    p("  peak RSS GiB : %s (%s, max across invocations)"
      % (payload["peak_rss_gib"], payload["peak_rss_label"]))
    p("  verdicts     : PENDING by design, not inherited from any subset")
    if problems:
        p("")
        p("PROBLEMS (%d). This file is NOT a complete run:" % len(problems))
        for x in problems:
            p("  - %s" % x)
        return 1
    p("")
    p("No problems detected. All three arms present and mutually consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
