"""
Phase 10 (D-0128): versioning and rollback.

A RELEASE is a manifest that pins everything a result depends on: the model
file's sha256, the version, the prompt options, the inference settings, the
hashes of every tracked config and policy file, the corpus hash, and the
benchmark baseline. Manifests are written to releases/<version>.json and are
immutable once written (a second write of the same version is refused).

ROLLBACK means: pick an earlier manifest, and verify the CURRENT working tree
against it -- every pinned file hash must match. It does not rewrite files by
itself (git does that: `git checkout <manifest.git_commit> -- <paths>`); it
tells you exactly which pinned files differ, so a rollback is verified rather
than assumed. A rollback target whose model sha differs from the file on disk
is refused, because the results recorded for that release were produced by a
different model.

Semantic versioning: MAJOR.MINOR.PATCH, where any change to the model sha,
prompt options or inference settings is at least a MINOR bump (results are not
comparable across it), and a change to only docs/tests is a PATCH.
"""

from __future__ import annotations

import datetime
import json
import os
import re
from typing import Any, Dict, List, Mapping, Optional

from maintenance.monitor import ROOT, file_sha256

#: Files whose content defines a release. Paths relative to the repo root.
PINNED_FILES = (
    "VERSION",
    "configs/maintenance-policy.json",
    "configs/risk-policy.json",
    "configs/capability-manifest.yaml",
    "deploy/ollama/Modelfile",
    "evals/bilingual_eval_v1.jsonl",
    "evals/rag_corpus_combined.jsonl",
    "evals/rag_gold_combined.jsonl",
    "src/execution/mode.py",
    "src/execution/paper.py",
    "src/llm/style.py",
    "src/rag/citations.py",
    "src/rag/sources.py",
    "src/safety/untrusted.py",
    "src/tools/registry.py",
    "scripts/run_phase4.py",
    "scripts/phase4_lib.py",
    "requirements.txt",
)

#: Release-defining settings whose change requires at least a MINOR bump.
BEHAVIOUR_KEYS = ("model_sha256", "prompt_options", "inference")

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class ReleaseError(RuntimeError):
    pass


def parse_version(v: str):
    m = _SEMVER.match(str(v or "").strip())
    if not m:
        raise ReleaseError("version %r is not MAJOR.MINOR.PATCH" % (v,))
    return tuple(int(x) for x in m.groups())


def read_version(root=ROOT) -> str:
    with open(os.path.join(root, "VERSION"), encoding="utf-8") as fh:
        v = fh.read().strip()
    parse_version(v)
    return v


def build_manifest(version: str, model_sha256: str, prompt_options: Mapping[str, Any],
                   inference: Mapping[str, Any], benchmark_baseline: Optional[str],
                   git_commit: Optional[str], root=ROOT, now=None) -> Dict[str, Any]:
    parse_version(version)
    if not re.fullmatch(r"[0-9a-f]{64}", str(model_sha256 or "")):
        raise ReleaseError("model_sha256 must be a 64-hex sha256")
    files = {}
    for rel in PINNED_FILES:
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            raise ReleaseError("pinned file missing: %s" % rel)
        files[rel] = file_sha256(p)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return {"version": version, "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_commit": git_commit, "model_sha256": model_sha256,
            "prompt_options": dict(sorted(prompt_options.items())),
            "inference": dict(sorted(inference.items())),
            "benchmark_baseline": benchmark_baseline, "files": files}


def releases_dir(root=ROOT):
    return os.path.join(root, "releases")


def list_releases(root=ROOT) -> List[Dict[str, Any]]:
    d = releases_dir(root)
    out = []
    if os.path.isdir(d):
        for f in os.listdir(d):
            if _SEMVER.match(f[:-5]) and f.endswith(".json"):
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    out.append(json.load(fh))
    return sorted(out, key=lambda m: parse_version(m["version"]))


def required_bump(prev: Mapping[str, Any], new: Mapping[str, Any]) -> str:
    """'major', 'minor', 'patch' or 'none' -- the smallest bump the change needs."""
    if any(prev.get(k) != new.get(k) for k in BEHAVIOUR_KEYS):
        return "minor"
    if prev.get("files") != new.get("files"):
        return "patch"
    return "none"


def write_release(manifest: Mapping[str, Any], root=ROOT) -> str:
    """Write releases/<version>.json. Refuses overwrite and too-small bumps."""
    v = manifest["version"]
    path = os.path.join(releases_dir(root), "%s.json" % v)
    if os.path.exists(path):
        raise ReleaseError("release %s already exists; releases are immutable" % v)
    prior = [m for m in list_releases(root) if parse_version(m["version"]) < parse_version(v)]
    if [m for m in list_releases(root) if parse_version(m["version"]) >= parse_version(v)]:
        raise ReleaseError("a release >= %s already exists; versions only increase" % v)
    if prior:
        prev = prior[-1]
        need = required_bump(prev, manifest)
        pv, nv = parse_version(prev["version"]), parse_version(v)
        bumped = ("major" if nv[0] > pv[0] else "minor" if nv[1] > pv[1] else
                  "patch" if nv[2] > pv[2] else "none")
        order = ("none", "patch", "minor", "major")
        if need == "none":
            raise ReleaseError("nothing changed since %s; no release needed" % prev["version"])
        if order.index(bumped) < order.index(need):
            raise ReleaseError("%s -> %s is a %s bump, but the change needs at least %s "
                               "(model, prompt options or inference changed)"
                               % (prev["version"], v, bumped, need))
    os.makedirs(releases_dir(root), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def unreleased_changes(root=ROOT) -> Optional[Dict[str, Any]]:
    """verify_against(latest release), or None when there is no release yet."""
    rels = list_releases(root)
    return verify_against(rels[-1], root) if rels else None


def verify_against(manifest: Mapping[str, Any], root=ROOT,
                   model_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Compare the working tree with a manifest. Returns {"ok", "differs",
    "missing", "model"}; ok only if every pinned file matches and, when a model
    path is given, its sha256 matches too.
    """
    differs, missing = [], []
    for rel, sha in sorted(manifest["files"].items()):
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            missing.append(rel)
        elif file_sha256(p) != sha:
            differs.append(rel)
    model = None
    if model_path is not None:
        have = file_sha256(model_path)
        model = {"expected": manifest["model_sha256"], "found": have,
                 "ok": have == manifest["model_sha256"]}
    ok = not differs and not missing and (model is None or model["ok"])
    return {"ok": ok, "version": manifest["version"], "differs": differs,
            "missing": missing, "model": model}


def release_commit(version: str, root=ROOT) -> Optional[str]:
    """
    The commit that ADDED releases/<version>.json. A manifest cannot name the
    commit that contains it (the hash depends on the content), and squash or
    rebase rewrites hashes anyway, so the commit is looked up from history at
    rollback time. The manifest is written in the same commit as the pinned
    files it hashes, so that commit restores exactly those files.
    """
    import subprocess
    try:
        out = subprocess.check_output(
            ["git", "-C", root, "log", "--diff-filter=A", "-n", "1", "--format=%H", "--",
             "releases/%s.json" % version], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:                                       # noqa: BLE001
        return None
    return out or None


def commit_has_files(commit: str, files: Mapping[str, str], root=ROOT) -> List[str]:
    """
    The pinned paths whose content AT `commit` does not hash to the manifest's
    sha256. Empty means the commit really is that release. D-0129: needed
    because two releases squashed into ONE commit share a "commit that added
    the manifest", and checking out that commit would restore the NEWER files
    while claiming to roll back to the older release.
    """
    import hashlib
    import subprocess
    bad = []
    for rel, sha in sorted(files.items()):
        try:
            blob = subprocess.check_output(["git", "-C", root, "show", "%s:%s" % (commit, rel)],
                                           stderr=subprocess.DEVNULL)
        except Exception:                                   # noqa: BLE001
            bad.append(rel)
            continue
        if hashlib.sha256(blob).hexdigest() != sha:
            bad.append(rel)
    return bad


def rollback_plan(target_version: str, root=ROOT, model_path: Optional[str] = None,
                  commit_resolver=None, commit_checker=None) -> Dict[str, Any]:
    """
    What a rollback to `target_version` requires: the git commit and the exact
    files to restore. Refused if the target is unknown or (with model_path) the
    model on disk is not the target's model.
    """
    rels = {m["version"]: m for m in list_releases(root)}
    if target_version not in rels:
        raise ReleaseError("no release %s (known: %s)" % (target_version, ", ".join(rels) or "none"))
    m = rels[target_version]
    v = verify_against(m, root, model_path)
    if v["model"] is not None and not v["model"]["ok"]:
        raise ReleaseError("the model on disk (%s) is not release %s's model (%s): its recorded "
                           "results do not apply" % (v["model"]["found"][:12], target_version,
                                                     m["model_sha256"][:12]))
    restore = v["differs"] + v["missing"]
    commit = m.get("git_commit") or (commit_resolver or release_commit)(target_version, root)
    if restore and not commit:
        raise ReleaseError("release %s differs from the tree but its commit cannot be found "
                           "(releases/%s.json is not committed?)" % (target_version, target_version))
    if restore:
        wrong = (commit_checker or commit_has_files)(commit, {r: m["files"][r] for r in restore}, root)
        if wrong:
            raise ReleaseError("commit %s does not hold release %s's version of %s (were two releases "
                               "squashed into one commit?); restore by hand from a commit that does"
                               % (str(commit)[:12], target_version, ", ".join(wrong)))
    cmd = "git checkout %s -- %s" % (commit, " ".join(restore)) if restore else None
    return {"target": target_version, "already_at_target": not restore, "commit": commit,
            "restore_files": restore, "command": cmd,
            "then": "bash tests/run_all.sh, then re-verify with tools/maintain.py --verify %s"
                    % target_version}
