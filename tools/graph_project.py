#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build a dependency and call graph of marfin-llm, and report what it shows.

WHY THIS EXISTS
---------------
Request 40 asked me to use https://github.com/Graphify-Labs/graphify "for
better understanding, project graphing and deep analysis of our own project,
marfin-llm, and to use it in the process of building our project so the project
gets better".

WHAT I ACTUALLY DID, AND WHY IT IS NOT A WRAPPER AROUND GRAPHIFY
---------------------------------------------------------------
graphify was cloned (depth 1, branch v8, Apache-2.0, 337 .py files) to
/home/user/refs/graphify and READ. Then MEASURED:

  * `graphify.extract.extract()` raises immediately:
        ImportError: tree-sitter is not installed.
                     Run: pip install 'tree-sitter>=0.23.0'
  * its declared dependencies are networkx>=3.4, numpy, rapidfuzz and roughly
    27 tree-sitter grammar packages.
  * marfin-llm is 89 .py files and NOTHING ELSE that is source: no JS, no Go,
    no Rust. `ast` from the standard library parses all 36 files under src/
    with ZERO failures.

graphify's value is breadth: one tool that reads 27 languages. marfin-llm needs
exactly one of those 27. Installing ~30 packages and a native toolchain to
analyse a single-language, stdlib-only project would make this project's
dependency footprint larger than the project, and every one of those packages
would then be something the user has to install on their Windows machine to
reproduce an analysis. That trade is wrong here, so this tool takes graphify's
IDEAS and implements them against `ast`, which is already present.

WHAT IS BORROWED FROM GRAPHIFY, DELIBERATELY
--------------------------------------------
1. Its pipeline shape, from its own ARCHITECTURE.md:
       detect -> extract -> build -> cluster -> analyze -> report
   The functions below follow that order, and the separation is the point:
   extraction never decides what is important, and analysis never re-parses.

2. Its CONFIDENCE LABELS on edges: EXTRACTED / INFERRED / AMBIGUOUS, with
   AMBIGUOUS flagged for human review rather than silently resolved. This is
   the same discipline marfin-llm already applies to facts
   (VERIFIED/MEASURED/COMPUTED/ESTIMATED/UNKNOWN), which is why adopting it
   costs nothing conceptually and why it belongs here: a call graph built from
   names is FULL of guesses, and a graph that hides which edges are guesses is
   worse than no graph.

3. Its node schema: {id, label, source_file, source_location}. Keeping the
   line number means every claim in the report can be checked by opening a
   file, rather than believed.

WHAT THIS TOOL WILL NOT DO
--------------------------
It does not resolve dynamic dispatch, getattr, or names shadowed at runtime.
Those edges are reported as AMBIGUOUS or not at all. Python cannot be fully
resolved statically and pretending otherwise would produce a confident wrong
graph -- which, in a project whose entire discipline is not overstating what is
known, would be the worst possible outcome.

Run:  python3 tools/graph_project.py
      python3 tools/graph_project.py --json out.json
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Confidence labels, borrowed from graphify's edge schema.
EXTRACTED = "EXTRACTED"    # read directly from the AST; not a guess
INFERRED = "INFERRED"      # resolved through one assumption, stated below
AMBIGUOUS = "AMBIGUOUS"    # several candidates; needs human review


# ---------------------------------------------------------------------------
# detect
# ---------------------------------------------------------------------------
def detect(root=ROOT, dirs=("src", "scripts", "tools", "tests")):
    """Every .py file worth analysing, as (module_name, abs_path)."""
    found = []
    for d in dirs:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames
                           if x not in ("__pycache__", ".git", "node_modules")]
            for fn in sorted(filenames):
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, root)
                found.append((_module_name(rel), path, rel))
    return sorted(found)


def _module_name(rel):
    """'src/llm/console.py' -> 'llm.console'. src/ is the import root."""
    parts = rel.replace("\\", "/").split("/")
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------
def _resolve_sibling(target, mod, ours_mods):
    """
    Resolve a BARE import name against the importer's own package.

    Returns (resolved_name, was_resolved). If nothing matches, the target is
    handed back untouched so the caller's own filtering still applies.

    WHY THIS EXISTS. Added after the tool's first run reported
    `tests._harness` as having NO internal edges -- which is false: 21 suites
    import it. The cause was that `from _harness import check` names the
    module `_harness`, while this tool ids the same file as `tests._harness`
    (only `src/` is stripped from the path). `build()` requires
    `target in ours`, so all 17 such edges were silently DISCARDED and the
    most-depended-on module in the test tree looked like dead code.

    MEASURED before the fix: 530 import edges, 17 recoverable, exactly two
    distinct targets -- `_harness` and `phase4_lib`.

    The rule is legitimate, not a convenience: those modules are imported as
    top-level names only because the importing files put their OWN directory
    on sys.path first. VERIFIED at tests/test_console.py line 40:
        sys.path.insert(0, os.path.dirname(__file__))
    So a bare `_harness` inside tests/ genuinely IS tests/_harness.py.

    It is still an assumption about sys.path rather than something read off
    the AST, so every edge it resolves is labelled INFERRED, never EXTRACTED.
    A same-named module elsewhere would make it wrong, so resolution is
    attempted ONLY when the sibling actually exists in the tree.
    """
    if target in ours_mods:
        return target, False        # already absolute; nothing to infer
    if "." not in mod:
        return target, False        # importer is top-level: no package to try
    pkg = mod.rsplit(".", 1)[0]
    cand = "%s.%s" % (pkg, target)
    if cand in ours_mods and cand != mod:
        return cand, True

    # CROSS-PACKAGE fallback. Some files put ANOTHER directory on sys.path
    # and then import a bare name from it -- VERIFIED at
    # tests/test_phase4_harness.py lines 104-107, which adds both src/ and
    # scripts/, then does `import phase4_lib as L` (line 111).
    #
    # Accepted ONLY when exactly one module in the tree has that basename.
    # MEASURED: 2 such edges, `phase4_lib` and `run_phase4`, each with a
    # single candidate. If two packages ever hold the same basename this
    # returns unresolved rather than picking one, because a graph that
    # guesses which of two modules an edge reaches is worse than a graph
    # that admits it does not know.
    hits = [m for m in ours_mods
            if m.rsplit(".", 1)[-1] == target and m != mod]
    if len(hits) == 1:
        return hits[0], True
    return target, False


def extract(files):
    """
    Nodes and edges, with a confidence label on every edge.

    Nodes are modules and top-level functions. Edges are imports and calls.
    Nothing here decides importance; that is cluster()'s and analyze()'s job.
    """
    nodes, edges, errors = [], [], []
    defined = {}          # simple name -> [module, ...]  (for call resolution)
    module_of = {}

    for mod, path, rel in files:
        try:
            src = open(path, encoding="utf-8").read()
            tree = ast.parse(src, filename=rel)
        except (SyntaxError, UnicodeDecodeError) as exc:
            errors.append((rel, type(exc).__name__, str(exc)[:120]))
            continue
        module_of[mod] = rel
        nodes.append({"id": mod, "label": mod, "kind": "module",
                      "source_file": rel, "source_location": 1,
                      "loc": src.count("\n") + 1})
        for item in tree.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nodes.append({"id": "%s:%s" % (mod, item.name),
                              "label": item.name, "kind": "function",
                              "source_file": rel,
                              "source_location": item.lineno})
                defined.setdefault(item.name, []).append(mod)
            elif isinstance(item, ast.ClassDef):
                nodes.append({"id": "%s:%s" % (mod, item.name),
                              "label": item.name, "kind": "class",
                              "source_file": rel,
                              "source_location": item.lineno})

    ours_mods = set(module_of)

    # Imports: read straight off the AST, so EXTRACTED.
    for mod, path, rel in files:
        try:
            tree = ast.parse(open(path, encoding="utf-8").read(), filename=rel)
        except (SyntaxError, UnicodeDecodeError):
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    # `import phase4_lib as L` is a real form in this tree
                    # (scripts/run_phase4.py:67), so the sibling rule has to
                    # apply here too, not only to from-imports.
                    tgt, inferred = _resolve_sibling(a.name, mod, ours_mods)
                    edges.append({"source": mod, "target": tgt,
                                  "relation": "imports",
                                  "confidence": INFERRED if inferred
                                  else EXTRACTED,
                                  "source_location": n.lineno})
            elif isinstance(n, ast.ImportFrom):
                target = n.module or ""
                if n.level:
                    # A relative import. Resolving it needs the package path,
                    # which we have -- but the assumption that src/ is the
                    # import root is exactly that, an assumption. INFERRED.
                    pkg = mod.rsplit(".", 1)[0] if "." in mod else ""
                    target = "%s.%s" % (pkg, target) if target else pkg
                    conf = INFERRED
                else:
                    target, inferred = _resolve_sibling(target, mod, ours_mods)
                    conf = INFERRED if inferred else EXTRACTED
                edges.append({"source": mod, "target": target,
                              "relation": "imports", "confidence": conf,
                              "source_location": n.lineno})

    # Calls: a NAME, not a resolved target. Python cannot be resolved
    # statically in general, so the label records how sure we are.
    for mod, path, rel in files:
        try:
            tree = ast.parse(open(path, encoding="utf-8").read(), filename=rel)
        except (SyntaxError, UnicodeDecodeError):
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            name = _callee_name(n.func)
            if not name:
                continue
            owners = defined.get(name, [])
            if len(owners) == 1:
                conf = EXTRACTED if owners[0] == mod else INFERRED
                tgt = "%s:%s" % (owners[0], name)
            elif len(owners) > 1:
                conf = AMBIGUOUS          # several modules define this name
                tgt = "?:%s" % name
            else:
                continue                  # stdlib or a method; not our graph
            edges.append({"source": mod, "target": tgt, "relation": "calls",
                          "confidence": conf, "source_location": n.lineno,
                          "candidates": len(owners)})
    return {"nodes": nodes, "edges": edges, "errors": errors,
            "module_of": module_of}


def _callee_name(func):
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------
def build(graph):
    """Adjacency over MODULES only, restricted to our own modules."""
    ours = {n["id"] for n in graph["nodes"] if n["kind"] == "module"}
    out = defaultdict(set)
    inn = defaultdict(set)
    for e in graph["edges"]:
        if e["relation"] != "imports":
            continue
        src, tgt = e["source"], e["target"]
        if src in ours and tgt in ours and src != tgt:
            out[src].add(tgt)
            inn[tgt].add(src)
    return {"ours": ours, "out": out, "in": inn}


# ---------------------------------------------------------------------------
# cluster
# ---------------------------------------------------------------------------
def cluster(graph):
    """Group modules by their top-level package. Cheap and honest."""
    groups = defaultdict(list)
    for n in graph["nodes"]:
        if n["kind"] != "module":
            continue
        groups[n["id"].split(".")[0] or "(root)"].append(n["id"])
    return {k: sorted(v) for k, v in sorted(groups.items())}


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------
def find_cycles(adj):
    """
    Import cycles among our own modules.

    Worth its own function because an import cycle is not a style opinion: in
    Python it is a real failure mode that appears as a partially-initialised
    module at import time, and it is easier to prevent than to debug.
    """
    out, ours = adj["out"], adj["ours"]
    cycles, state, stack = [], {}, []

    def walk(node):
        state[node] = 1
        stack.append(node)
        for nxt in sorted(out.get(node, ())):
            if state.get(nxt, 0) == 0:
                walk(nxt)
            elif state.get(nxt) == 1 and nxt in stack:
                cyc = stack[stack.index(nxt):] + [nxt]
                if cyc not in cycles:
                    cycles.append(cyc)
        stack.pop()
        state[node] = 2

    for node in sorted(ours):
        if state.get(node, 0) == 0:
            walk(node)
    return cycles


def analyze(graph, adj):
    ours = adj["ours"]
    fan_in = {m: len(adj["in"].get(m, ())) for m in ours}
    fan_out = {m: len(adj["out"].get(m, ())) for m in ours}
    loc = {n["id"]: n.get("loc", 0)
           for n in graph["nodes"] if n["kind"] == "module"}
    conf = defaultdict(int)
    for e in graph["edges"]:
        conf[e["confidence"]] += 1
    orphans = sorted(m for m in ours
                     if not fan_in[m] and not fan_out[m])
    ambiguous = sorted({e["target"].split(":")[-1] for e in graph["edges"]
                        if e["confidence"] == AMBIGUOUS})
    return {
        "fan_in": fan_in, "fan_out": fan_out, "loc": loc,
        "confidence_counts": dict(conf),
        "cycles": find_cycles(adj),
        "orphans": orphans,
        "ambiguous_names": ambiguous,
    }


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def report(graph, adj, clusters, stats):
    L = []
    A = L.append
    mods = sorted(adj["ours"])
    A("=" * 74)
    A("MARFIN-LLM STRUCTURE REPORT")
    A("=" * 74)
    A("  method: stdlib `ast`, pipeline and confidence labels modelled on")
    A("          graphify (Apache-2.0). Every figure below is MEASURED from")
    A("          the source tree; nothing is estimated.")
    A("")
    A("  modules analysed        %d" % len(mods))
    A("  nodes (mod/func/class)  %d" % len(graph["nodes"]))
    A("  edges                   %d" % len(graph["edges"]))
    A("  parse errors            %d" % len(graph["errors"]))
    for rel, kind, msg in graph["errors"]:
        A("      %s  %s: %s" % (rel, kind, msg))
    A("")
    A("  EDGE CONFIDENCE (graphify's convention)")
    total = sum(stats["confidence_counts"].values()) or 1
    for k in (EXTRACTED, INFERRED, AMBIGUOUS):
        n = stats["confidence_counts"].get(k, 0)
        A("      %-10s %5d  (%4.1f%%)" % (k, n, 100.0 * n / total))
    A("")
    A("  AMBIGUOUS names -- a name defined in more than one module, so a")
    A("  static reader cannot say which one a call reaches. NOT presented as")
    A("  resolved:")
    if stats["ambiguous_names"]:
        for name in stats["ambiguous_names"][:20]:
            A("      %s" % name)
        if len(stats["ambiguous_names"]) > 20:
            A("      ... and %d more"
              % (len(stats["ambiguous_names"]) - 20))
    else:
        A("      none")
    A("")
    A("  IMPORT CYCLES among our own modules")
    if stats["cycles"]:
        for c in stats["cycles"]:
            A("      %s" % " -> ".join(c))
    else:
        A("      none  <- this is the good answer")
    A("")
    A("  MOST DEPENDED-ON MODULES (fan-in): a defect here reaches furthest,")
    A("  so this is where test effort belongs.")
    for m in sorted(mods, key=lambda x: (-stats["fan_in"][x], x))[:10]:
        if stats["fan_in"][m]:
            A("      %-34s in=%-3d out=%-3d %5d loc"
              % (m, stats["fan_in"][m], stats["fan_out"][m],
                 stats["loc"].get(m, 0)))
    A("")
    A("  CLUSTERS")
    for k, v in clusters.items():
        A("      %-12s %d module(s)" % (k, len(v)))
    A("")
    A("  MODULES WITH NO INTERNAL EDGES (entry points, or dead code --")
    A("  the graph cannot tell which, and does not guess):")
    for m in stats["orphans"][:15]:
        A("      %s" % m)
    if len(stats["orphans"]) > 15:
        A("      ... and %d more" % (len(stats["orphans"]) - 15))
    A("=" * 74)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--json", metavar="PATH",
                    help="also write the raw graph as JSON")
    args = ap.parse_args()

    files = detect()
    graph = extract(files)
    adj = build(graph)
    clusters = cluster(graph)
    stats = analyze(graph, adj)
    print(report(graph, adj, clusters, stats))

    if args.json:
        payload = {"nodes": graph["nodes"], "edges": graph["edges"],
                   "clusters": clusters,
                   "analysis": {k: v for k, v in stats.items()
                                if k not in ("fan_in", "fan_out", "loc")},
                   "label": "MEASURED_STATIC_AST",
                   "method": "stdlib ast; graphify-style confidence labels"}
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
        print("\n  raw graph written to %s" % args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
