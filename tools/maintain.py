# -*- coding: utf-8 -*-
"""
Phase 10 (D-0128): one entry point for the maintenance routine.

    python3 tools/maintain.py                 # run every check, print a report
    python3 tools/maintain.py --json out.json # also write the report
    python3 tools/maintain.py --record-index  # re-record the corpus manifest (after review)
    python3 tools/maintain.py --audit DIR     # include a paper engine's audit log
    python3 tools/maintain.py --release       # write releases/<VERSION>.json
    python3 tools/maintain.py --verify 0.10.0 # verify the tree against a release
    python3 tools/maintain.py --rollback 0.10.0

Exit status: 0 OK, 1 DUE (warnings), 2 FAIL (critical). Nothing here reaches
the network; source and licence re-probes are reported as DUE, with the command
that performs them (tools/verify_tradingview_terms.py and friends).
"""
import argparse
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from maintenance import monitor as MON                      # noqa: E402
from maintenance import release as REL                      # noqa: E402

INDEX_MANIFEST = os.path.join(ROOT, "releases", "index-manifest.json")
DEP_LOCK = os.path.join(ROOT, "releases", "dependencies.lock.json")
BASELINE = os.path.join(ROOT, "releases", "benchmark-baseline.json")
LEGAL = {"tradingview-terms-review": "docs/legal/tradingview-terms-review.md",
         "market-data-providers": "docs/legal/market-data-providers.md",
         "research-and-news-sources": "docs/legal/research-and-news-sources.md",
         "ai-web-search-review": "docs/legal/ai-web-search-review.md"}
DIRECTION = {"citation_correctness_pct_min": "min", "correct_abstention_pct_min": "min",
             "deterministic_calc_correctness_pct_min": "min", "generation_tokens_per_sec_min": "min",
             "tool_call_schema_validity_pct_min": "min", "fabricated_financial_data_count_max": "max",
             "model_file_size_gib_max": "max", "peak_rss_8k_gib_max": "max",
             "time_to_first_token_2k_sec_max": "max", "unsupported_claim_rate_pct_max": "max",
             "paper_live_confusion_count_max": "max", "persian_fluency_regression_pct_max": "max"}
# D-0129: the benchmark of the RECOMMENDED configuration (display + continuation),
# measured on the i5-12400 by the owner. D-0140: the 2026-10-25 rerun (same verdict,
# EN-TERM-001 no longer guard-blocked) replaces the 2026-10-21 run as the baseline.
CURRENT_VERDICT = os.path.join(ROOT, "evidence", "phase8c_rerun_verdict_2026-10-25.json")
BASELINE_MEASURED_ON = "2026-10-25"
MODEL_SHA = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"
PROMPT_OPTIONS = {"second_turn": True, "refusal_language": True, "execution_guard": True,
                  "min_trust": 80, "display": True, "continue_budget": 256}
INFERENCE = {"runtime": "llama.cpp in-process", "quant": "Q4_K_M", "ctx": 16384, "threads": 6,
             "max_tokens": 512, "temperature": 0.0, "seed": 20260831, "repeat_penalty": 1.0}


def run_checks(now=None, audit_dir=None, policy=None):
    from rag import sources as S
    import build_licenses as BL
    from execution import paper as PP
    policy = policy or MON.load_policy()
    f = []
    f += MON.check_sources(S.SOURCES, policy, now)
    f += MON.check_index(os.path.join(ROOT, "evals", "rag_corpus_combined.jsonl"),
                         INDEX_MANIFEST, policy, now)
    f += MON.check_dependencies(os.path.join(ROOT, "requirements.txt"), DEP_LOCK, policy, now)
    f += MON.check_licenses(os.path.join(ROOT, "LICENSES.md"), BL.render,
                            {k: os.path.join(ROOT, v) for k, v in LEGAL.items()}, policy, now)
    if os.path.exists(BASELINE):
        f += MON.check_benchmark(CURRENT_VERDICT, BASELINE, policy, now)
    else:
        f.append(MON.Finding("benchmark", "WARN", "baseline", "no recorded baseline"))
    f += MON.check_risk_policy(os.path.join(ROOT, "configs", "risk-policy.json"), policy, now,
                               limits_factory=PP.RiskLimits)
    u = REL.unreleased_changes(ROOT)
    if u is None:
        f.append(MON.Finding("versioning", "WARN", "release", "no release manifest recorded"))
    elif not u["ok"]:
        f.append(MON.Finding("versioning", "WARN", "release %s" % u["version"],
                             "pinned files changed since release %s: %s -- bump VERSION and "
                             "run --release" % (u["version"], ", ".join(u["differs"] + u["missing"]))))
    else:
        f.append(MON.Finding("versioning", "INFO", "release %s" % u["version"],
                             "tree matches release %s" % u["version"]))
    if audit_dir:
        path = os.path.join(audit_dir, "audit.jsonl")
        if not os.path.exists(path):
            f.append(MON.Finding("reconciliation", "WARN", "audit",
                                 "no audit log at %s: nothing was checked" % path))
        else:
            try:
                log = PP.AuditLog(path)        # refuses a broken chain
                f += MON.check_reconciliation(log.records(), policy, now)
            except PP.PaperError as exc:
                f.append(MON.Finding("reconciliation", "CRITICAL", "audit",
                                     "audit chain broken: %s" % exc))
    return MON.summarize(f)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json")
    ap.add_argument("--audit")
    ap.add_argument("--record-index", action="store_true")
    ap.add_argument("--record-baseline", action="store_true")
    ap.add_argument("--release", action="store_true")
    ap.add_argument("--verify")
    ap.add_argument("--rollback")
    ap.add_argument("--model", help="model file, to verify its sha256")
    a = ap.parse_args(argv)

    if a.record_index:
        m = MON.corpus_manifest(os.path.join(ROOT, "evals", "rag_corpus_combined.jsonl"))
        os.makedirs(os.path.dirname(INDEX_MANIFEST), exist_ok=True)
        json.dump(m, open(INDEX_MANIFEST, "w"), indent=2)
        print("recorded %s (%d passages)" % (INDEX_MANIFEST, m["n_passages"]))
        return 0
    if a.record_baseline:
        b = MON.baseline_from_verdict(CURRENT_VERDICT, BASELINE_MEASURED_ON, DIRECTION)
        json.dump(b, open(BASELINE, "w"), indent=2)
        print("recorded %s" % BASELINE)
        return 0
    if a.release:
        m = REL.build_manifest(REL.read_version(), MODEL_SHA, PROMPT_OPTIONS, INFERENCE,
                               os.path.relpath(BASELINE, ROOT), None)
        try:
            print("written: %s" % REL.write_release(m))
        except REL.ReleaseError as exc:
            print("REFUSED: %s" % exc)
            return 2
        print("commit it together with the pinned files; rollback finds the commit from git")
        return 0
    if a.verify:
        rels = {m["version"]: m for m in REL.list_releases()}
        if a.verify not in rels:
            print("no release %s" % a.verify)
            return 2
        r = REL.verify_against(rels[a.verify], model_path=a.model)
        print(json.dumps(r, indent=2))
        return 0 if r["ok"] else 2
    if a.rollback:
        try:
            print(json.dumps(REL.rollback_plan(a.rollback, model_path=a.model), indent=2))
        except REL.ReleaseError as exc:
            print("REFUSED: %s" % exc)
            return 2
        return 0

    rep = run_checks(audit_dir=a.audit)
    for f in rep["findings"]:
        if f["severity"] != "INFO":
            print("%-8s %-15s %-28s %s" % (f["severity"], f["check"], f["subject"], f["message"]))
    print("STATUS: %s  %s" % (rep["status"], rep["counts"]))
    if a.json:
        json.dump(rep, open(a.json, "w"), indent=2, ensure_ascii=False)
    return {"OK": 0, "DUE": 1, "FAIL": 2}[rep["status"]]


if __name__ == "__main__":
    sys.exit(main())
