# -*- coding: utf-8 -*-
"""Mutation battery for Phase 9 (D-0126): each mutation makes a doc FALSE; test_phase9 must fail."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ORACLE = os.path.join(HERE, "test_phase9.py")

MUTATIONS = [
    ("MODEL_CARD.md", "wrong checksum", "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4` (V, full", "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a5` (V, full"),
    ("MODEL_CARD.md", "benchmark inflated", "| 90.48 | **FAIL** |", "| 95.48 | **FAIL** |"),
    ("MODEL_CARD.md", "SS.23 field dropped", "| **Context** |", "| **Ctx** |"),
    ("MODEL_CARD.md", "tool count wrong", "85 deterministic", "86 deterministic"),
    ("LICENSES.md", "licence registry edited by hand", "| fred |", "| fred_x |"),
    ("LICENSES.md", "wrong licence named for the project code", "**Apache License 2.0** (`LICENSE`, `NOTICE`)", "**MIT License** (`LICENSE`, `NOTICE`)"),
    ("LICENSE", "licence text altered", "Version 2.0, January 2004", "Version 2.0, January 2005"),
    ("NOTICE", "Alpha Vantage carve-out removed", "- tests/fixtures/alpha_vantage/*.json", "- (fixtures)"),
    ("NOTICE", "Alpha Vantage fixtures claimed as licensed", "these files are NOT licensed to you by this project", "these files are licensed with the project"),
    ("MODEL_CARD.md", "model card still says unlicensed", "Project code: Apache-2.0 (`LICENSE`, `NOTICE`", "Project code: not yet licensed (`LICENSE`, `NOTICE`"),
    ("README.md", "README contradicts the licence", "licensed under the **Apache License 2.0**", "licensed under the **MIT License**"),
    ("tools/build_licenses.py", "model-cards carve-out dropped", "- `configs/model-cards/*.json`: configuration files", "- configuration files"),
    ("src/rag/sources.py", "registry changed without regenerating LICENSES.md", "FRED (Federal Reserve Bank of St. Louis)", "FRED (St. Louis Fed)"),
    ("requirements.txt", "runtime dependency missing", "psutil>=5.9", "#psutil"),
    (".env.example", "a real-looking secret value", "ALPHAVANTAGE_API_KEY=\n", "ALPHAVANTAGE_API_KEY=abc123\n"),
    (".env.example", "a key the code reads is missing", "OPENAI_API_KEY=\n", ""),
    ("docs/execution-safety.md", "wrong SS.6.1 count", "10 of 12 are unmet", "9 of 12 are unmet"),
    ("docs/execution-safety.md", "wrong check count", "17 pre-trade checks", "18 pre-trade checks"),
    ("docs/tradingview-integration.md", "wrong webhook validation count", "16 validations", "15 validations"),
    ("docs/deployment.md", "documented flag does not exist", "--continue-budget 256 `", "--continue-tokens 256 `"),
    ("docs/deployment.md", "wrong checksum in deployment", "00FE7986FF5F6B463E62455821146049DB6F9313603938A70800D1FB69EF11A4", "00FE7986FF5F6B463E62455821146049DB6F9313603938A70800D1FB69EF11A0"),
    (".gitignore", ".env.example ignored", "!.env.example\n", ""),
]


def oracle():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run([sys.executable, ORACLE], cwd=ROOT, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
    except subprocess.TimeoutExpired:
        return False
    return p.returncode == 0


def main():
    if not oracle():
        print("ABORT: oracle fails before mutation")
        return 1
    killed = survived = skipped = 0
    surv, skips = [], []
    for i, (f, desc, find, repl) in enumerate(MUTATIONS, 1):
        path = os.path.join(ROOT, f)
        orig = open(path, encoding="utf-8").read()
        if orig.count(find) != 1:
            skipped += 1
            skips.append("%s: %s (count=%d)" % (f, desc, orig.count(find)))
            print("  %2d. SKIP     %s" % (i, desc))
            continue
        try:
            open(path, "w", encoding="utf-8").write(orig.replace(find, repl, 1))
            ok = oracle()
        finally:
            open(path, "w", encoding="utf-8").write(orig)
        if ok:
            survived += 1
            surv.append("%s: %s" % (f, desc))
            print("  %2d. SURVIVED %s" % (i, desc))
        else:
            killed += 1
            print("  %2d. killed   %s" % (i, desc))
    intact = oracle()
    print("=" * 70)
    print("  seeded %d  killed %d  survived %d  skipped %d  restored+green %s"
          % (len(MUTATIONS), killed, survived, skipped, intact))
    for s in surv:
        print("  SURVIVOR:", s)
    for s in skips:
        print("  SKIPPED: ", s)
    return 0 if (survived == 0 and skipped == 0 and intact) else 1


if __name__ == "__main__":
    sys.exit(main())
