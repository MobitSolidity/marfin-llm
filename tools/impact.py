#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Which test suites and mutation batteries does a change reach?

WHY THIS EXISTS (D-0109)
------------------------
Twice in a row a change was verified against the wrong subset of the safety
net, and both times the miss was silent:

  * D-0107 edited src/rag/normalize.py and ran tests/mutate_rag.py. It did NOT
    run tests/mutate_phase4.py -- whose NORM target is the very same file. Three
    of that battery's mutants lost their anchors and were reported SKIPPED, not
    failed. Nobody saw it until D-0108 ran the battery for another reason.
  * D-0108's own first draft blinded two more, found only because the skipped
    count read 14 against an established 9.

Both are the same question asked by memory instead of by the graph: "what
depends on this file?" The dependency graph already answers it. This tool asks
it mechanically, so the answer no longer depends on remembering which battery
quietly points at which module.

HOW IT DECIDES -- and how sure it is
------------------------------------
Each reason carries graphify's confidence label (see tools/graph_project.py):

  battery TARGETS the file   EXTRACTED  the battery's own source names the
                                        file it patches (string literals and
                                        os.path.join() constants, read by ast)
  suite IMPORTS the file     EXTRACTED  transitive import closure from
                                        tools/graph_project.py's graph
  suite/closure NAMES it     INFERRED   the basename appears as a string
                                        literal in the suite or in a module it
                                        imports -- how data files (evals/*.jsonl)
                                        and spec_from_file_location() loads are
                                        reached. A name is evidence, not proof.
  battery ORACLE reaches it  INFERRED   a battery whose oracle suite is reached
                                        can be blinded by the change too

Nothing is executed. The graph is built from the stdlib `ast` (no graphify
install required); if graphify-out/graph.json exists it is used as a
CROSS-CHECK only, and any import edge it has that ours lacks is reported as a
disagreement rather than silently merged.

Run:
    python3 tools/impact.py src/rag/normalize.py
    python3 tools/impact.py --rev HEAD           # files changed by a commit
    python3 tools/impact.py --staged             # files in the index
    python3 tools/impact.py --json ... 

Exit 0 always when the analysis completed. Stdlib only.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import graph_project as GP                                    # noqa: E402

EXTRACTED, INFERRED = GP.EXTRACTED, GP.INFERRED

# The skipped count each battery reports on a clean tree. A higher count after
# a change means anchors went stale -- mutants that silently stopped applying.
# Only batteries whose baseline is RECORDED in DECISIONS.md are listed; the
# others are reported as "compare to your last run" rather than given a number
# nobody measured.
SKIP_BASELINE = {
    "tests/mutate_phase4.py": 9,      # D-0100, D-0108
}


def _rel(path):
    return os.path.relpath(os.path.abspath(path), ROOT).replace("\\", "/")


# ---------------------------------------------------------------------------
# what run_all.sh actually runs
# ---------------------------------------------------------------------------
def suites(root=ROOT):
    """The SUITES list from tests/run_all.sh, in order. Read, not re-declared."""
    txt = open(os.path.join(root, "tests", "run_all.sh"), encoding="utf-8").read()
    m = re.search(r'SUITES="(.*?)"', txt, re.S)
    if not m:
        raise RuntimeError("tests/run_all.sh: SUITES list not found")
    return [s for s in re.split(r"[\s\\]+", m.group(1)) if s]


def batteries(root=ROOT):
    """Every mutation battery the --mutate path can run."""
    tdir = os.path.join(root, "tests")
    out = sorted("tests/" + f for f in os.listdir(tdir)
                 if f.startswith("mutate_") and f.endswith(".py"))
    if os.path.exists(os.path.join(tdir, "mutation_test.sh")):
        out.insert(0, "tests/mutation_test.sh")
    return out


# ---------------------------------------------------------------------------
# what each battery patches, and which suite judges it
# ---------------------------------------------------------------------------
def _join_constants(node):
    """Leading string constants of an os.path.join(...) call, after ROOT/HERE."""
    parts = []
    for a in node.args:
        if isinstance(a, ast.Constant) and isinstance(a.value, str):
            parts.append(a.value)
        elif parts:
            break
    return parts


def battery_files(battery, root=ROOT):
    """
    (targets, oracles) for one battery, as repo-relative paths that EXIST.

    Read from the battery's own source, so a new target or oracle is picked up
    the moment it is written. A literal that resolves to nothing is dropped,
    never guessed at.
    """
    path = os.path.join(root, battery)
    if battery.endswith(".sh"):
        # tests/mutation_test.sh: `for m in a b c; do cp "src/calc/$m.py" ...`
        txt = open(path, encoding="utf-8").read()
        targets = set()
        for loop in re.finditer(r"for m in ([\w ]+); do", txt):
            for m in loop.group(1).split():
                p = "src/calc/%s.py" % m
                if os.path.exists(os.path.join(root, p)):
                    targets.add(p)
        # `run_mut <module> <oracle.py> ...` -- the oracle is the 2nd word.
        oracles = {"tests/" + o
                   for o in re.findall(r"^run_mut \w+ (test_\w+\.py)", txt, re.M)}
        return sorted(targets), sorted(o for o in oracles
                                       if os.path.exists(os.path.join(root, o)))

    tree = ast.parse(open(path, encoding="utf-8").read(), filename=battery)
    literals, dirs = set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            if re.fullmatch(r"[\w./-]+\.(?:py|jsonl|json)", n.value):
                literals.add(n.value)
        elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and n.func.attr == "join"):
            parts = _join_constants(n)
            if parts:
                cand = "/".join(parts)
                full = os.path.join(root, cand)
                if os.path.isdir(full):
                    dirs.add(cand)
                elif os.path.isfile(full):
                    literals.add(cand)
    dirs |= {"", "src"}
    targets, oracles = set(), set()
    for lit in literals:
        base = os.path.basename(lit)
        if base.startswith(("test_", "probe_")):
            p = "tests/" + base
            if os.path.exists(os.path.join(root, p)):
                oracles.add(p)
            continue
        hits = {("%s/%s" % (d, lit)).lstrip("/") for d in dirs
                if os.path.isfile(os.path.join(root, d, lit))}
        if len(hits) == 1:
            targets.add(hits.pop())
        # 0 hits: a backup name (selector_orig.py) or a path built at runtime.
        # >1 hits: genuinely ambiguous; dropping it is the honest choice, and
        # the test suite pins every real battery's target list so a drop that
        # matters cannot pass unnoticed.
    targets.discard(battery)
    return sorted(targets), sorted(oracles)


# ---------------------------------------------------------------------------
# what each suite reaches
# ---------------------------------------------------------------------------
_GRAPH_CACHE = {}


def import_graph(root=ROOT):
    """file -> set(files it imports), our modules only, from graph_project."""
    if root in _GRAPH_CACHE:
        return _GRAPH_CACHE[root]
    files = GP.detect(root)
    g = GP.extract(files)
    mod_file = g["module_of"]
    out = {}
    for e in g["edges"]:
        if e["relation"] != "imports":
            continue
        a, b = mod_file.get(e["source"]), mod_file.get(e["target"])
        if a and b and a != b:
            out.setdefault(a, set()).add(b)
    _GRAPH_CACHE[root] = out
    return out


def closure(start, graph):
    seen, stack = {start}, [start]
    while stack:
        for nxt in graph.get(stack.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def _mentions(path, basename, root=ROOT, _cache={}):
    key = (root, path)
    if key not in _cache:
        try:
            _cache[key] = open(os.path.join(root, path), encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            _cache[key] = ""
    txt = _cache[key]
    return re.search(r"(?<![\w.])%s(?![\w])" % re.escape(basename), txt) is not None


def suite_reaches(suite, changed, graph, root=ROOT):
    """(confidence, why) if `suite` reaches `changed`, else None."""
    clo = closure(suite, graph)
    if changed == suite:
        return EXTRACTED, "is the suite"
    if changed in clo:
        return EXTRACTED, "imported (transitively)"
    base = os.path.basename(changed)
    for f in sorted(clo):
        if _mentions(f, base, root):
            return INFERRED, "named in %s" % f
    return None


# ---------------------------------------------------------------------------
# the analysis
# ---------------------------------------------------------------------------
def analyse(changed, root=ROOT):
    changed = sorted({c.replace("\\", "/") for c in changed})
    graph = import_graph(root)
    rows_s, rows_b = [], []
    for s in suites(root):
        why = [(c,) + r for c in changed
               for r in [suite_reaches(s, c, graph, root)] if r]
        if why:
            rows_s.append({"suite": s, "reasons": [
                {"file": c, "confidence": conf, "why": w} for c, conf, w in why]})
    reached_suites = {r["suite"] for r in rows_s}
    for b in batteries(root):
        targets, oracles = battery_files(b, root)
        reasons = []
        for c in changed:
            if c == b:
                reasons.append({"file": c, "confidence": EXTRACTED,
                                "why": "is the battery"})
            elif c in targets:
                reasons.append({"file": c, "confidence": EXTRACTED,
                                "why": "battery PATCHES this file -- its "
                                       "anchors may no longer match"})
        for o in oracles:
            if o in reached_suites and not reasons:
                reasons.append({"file": o, "confidence": INFERRED,
                                "why": "its oracle %s is reached" % o})
        if reasons:
            rows_b.append({"battery": b, "targets": targets,
                           "oracles": oracles, "reasons": reasons,
                           "skip_baseline": SKIP_BASELINE.get(b)})
    return {"changed": changed, "suites": rows_s, "batteries": rows_b,
            "label": "COMPUTED_STATIC_DEPENDENCY",
            "method": "stdlib ast import closure + literal names; "
                      "graphify-style confidence labels"}


def cross_check(root=ROOT):
    """
    Import edges graphify has that our graph lacks. Empty is the good answer.

    Only file->file edges between .py files are compared. graphify does not
    resolve imports made after a sys.path.insert(), so OUR graph has edges it
    lacks; that direction is expected and is reported only as a count.
    """
    gpath = os.path.join(root, "graphify-out", "graph.json")
    if not os.path.exists(gpath):
        return None
    g = json.load(open(gpath, encoding="utf-8"))
    sf = {n["id"]: n.get("source_file") for n in g.get("nodes", [])}
    theirs = set()
    for l in g.get("links", g.get("edges", [])):
        if l.get("relation") not in ("imports", "imports_from"):
            continue
        a, b = sf.get(l["source"]), sf.get(l["target"])
        if a and b and a != b and a.endswith(".py") and b.endswith(".py"):
            theirs.add((a, b))
    ours = {(a, b) for a, bs in import_graph(root).items() for b in bs}
    return {"graphify_commit": g.get("built_at_commit"),
            "only_graphify": sorted(theirs - ours),
            "only_ours_n": len(ours - theirs),
            "both_n": len(ours & theirs)}


def _git_files(args):
    out = subprocess.run(["git"] + args, cwd=ROOT, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, check=True)
    return [l for l in out.stdout.decode("utf-8").splitlines() if l.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description="What does a change reach?")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--rev", help="files changed by this commit")
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--worktree", action="store_true",
                    help="files changed in the working tree vs HEAD")
    ap.add_argument("--cross-check", action="store_true",
                    help="compare our import graph with graphify-out/graph.json")
    ap.add_argument("--json", metavar="PATH")
    a = ap.parse_args(argv)

    changed = [_rel(f) for f in a.files]
    if a.rev:
        changed += _git_files(["show", "--name-only", "--format=", a.rev])
    if a.staged:
        changed += _git_files(["diff", "--name-only", "--cached"])
    if a.worktree:
        changed += _git_files(["diff", "--name-only", "HEAD"])
    p = print
    if a.cross_check:
        cc = cross_check()
        p("graphify cross-check:")
        if cc is None:
            p("  graphify-out/graph.json absent -- run `graphify update .`")
        else:
            p("  graphify built at %s; edges in both: %d; only ours: %d"
              % (cc["graphify_commit"], cc["both_n"], cc["only_ours_n"]))
            p("  only graphify (a gap in OUR graph): %d" % len(cc["only_graphify"]))
            for e in cc["only_graphify"]:
                p("    %s -> %s" % e)
        if not changed:
            return 0
    if not changed:
        ap.error("name files, or use --rev / --staged / --worktree")

    res = analyse(changed)
    p("=" * 74)
    p("IMPACT of %d changed file(s) -- COMPUTED from the static graph" % len(res["changed"]))
    p("=" * 74)
    for c in res["changed"]:
        p("  * %s" % c)
    p("\nSUITES that reach the change (%d of %d):"
      % (len(res["suites"]), len(suites())))
    for r in res["suites"]:
        p("  %s" % r["suite"])
        for why in r["reasons"]:
            p("      [%s] %s: %s" % (why["confidence"], why["file"], why["why"]))
    p("\nMUTATION BATTERIES to run (%d):" % len(res["batteries"]))
    for r in res["batteries"]:
        p("  %s" % r["battery"])
        for why in r["reasons"]:
            p("      [%s] %s: %s" % (why["confidence"], why["file"], why["why"]))
        if any("PATCHES" in w["why"] for w in r["reasons"]):
            base = r["skip_baseline"]
            p("      CHECK: its SKIPPED count, not only killed/survived -- %s"
              % ("baseline %d" % base if base is not None
                 else "compare to the last recorded run"))
    if not res["batteries"]:
        p("  none")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        p("\nwritten: %s" % a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
