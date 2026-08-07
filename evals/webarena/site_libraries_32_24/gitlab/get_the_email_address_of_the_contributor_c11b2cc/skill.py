# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --branch ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['branch']
    argv = sys.argv[1:]
    # A single positional, non-flag argument is a taskspec.json path -> original behaviour,
    # sys.argv left untouched. This is the path replay uses, so it must not change.
    if len(argv) == 1 and not argv[0].startswith("-"):
        return
    ap = argparse.ArgumentParser(
        prog="skill.py",
        description="Run this skill directly. Pass --flags, or a taskspec.json path.")
    for _p in _PARAMS:
        ap.add_argument("--" + _p.replace("_", "-"), dest=_p, default=None)
    ap.add_argument("taskspec", nargs="?", help="path to a taskspec.json (instead of --flags)")
    a = ap.parse_args(argv)
    # A taskspec path given alongside/without flags -> honour it, stay untouched.
    if a.taskspec and not any(getattr(a, _p) is not None for _p in _PARAMS):
        sys.argv = [sys.argv[0], a.taskspec]
        return
    params = {_p: getattr(a, _p) for _p in _PARAMS if getattr(a, _p) is not None}
    if not params:
        ap.print_help()
        ex = " ".join("--" + _p.replace("_", "-") + " <" + _p + ">" for _p in _PARAMS)
        print("\n  example:  python skill.py " + ex)
        print("  or:       python skill.py taskspec.json  "
              '(taskspec = {"params": {' + ", ".join('"' + _p + '": ...' for _p in _PARAMS)
              + "}})")
        raise SystemExit(0)
    spec = {"params": params}
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(spec, f)
    f.close()
    sys.argv = [sys.argv[0], f.name]
_skillfactory_cli()
# --- end CLI entry shim ---------------------------------------------------------------------

import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse


WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", os.getcwd()))


def ensure_workspace() -> Path:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    return WORKSPACE


def run_cmd(cmd, cwd=None) -> str:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_repo_name(start_url: str) -> str:
    parsed = urlparse(start_url)
    tail = parsed.path.rstrip("/").split("/")[-1] or "repo"
    if tail.endswith(".git"):
        tail = tail[:-4]
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in tail)
    return cleaned or "repo"


def normalize_branch_candidates(branch: str):
    candidates = [branch]
    if branch.endswith("s"):
        singular = branch[:-1]
        if singular:
            candidates.append(singular)
    else:
        candidates.append(branch + "s")
    if branch.endswith("page"):
        candidates.append(branch + "s")
    if branch.endswith("pages"):
        candidates.append(branch[:-1])
    seen = []
    for c in candidates:
        if c and c not in seen:
            seen.append(c)
    return seen


def clone_repository_mirror(start_url: str, dest_dir: Path) -> Path:
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    run_cmd(["git", "clone", "--mirror", start_url, str(dest_dir)])
    return dest_dir


def list_refs(repo_dir: Path):
    refs = run_cmd(["git", "for-each-ref", "--format=%(refname:short)"], cwd=repo_dir)
    return [line.strip() for line in refs.splitlines() if line.strip()]


def resolve_branch_name(repo_dir: Path, requested_branch: str) -> str:
    refs = list_refs(repo_dir)
    ref_set = set(refs)

    direct_candidates = []
    for candidate in normalize_branch_candidates(requested_branch):
        direct_candidates.extend(
            [
                candidate,
                f"heads/{candidate}",
                f"origin/{candidate}",
                f"refs/heads/{candidate}",
                f"refs/remotes/origin/{candidate}",
            ]
        )

    for cand in direct_candidates:
        if cand in ref_set:
            return cand

    normalized_requested = requested_branch.lower()
    normalized_candidates = [c.lower() for c in normalize_branch_candidates(requested_branch)]

    matches = []
    for ref in refs:
        ref_low = ref.lower()
        if any(nc == ref_low.split("/")[-1] for nc in normalized_candidates):
            matches.append(ref)
        elif any(nc in ref_low for nc in normalized_candidates):
            matches.append(ref)

    if len(matches) == 1:
        return matches[0]

    if matches:
        for m in matches:
            tail = m.split("/")[-1].lower()
            if tail in normalized_candidates:
                return m
        return matches[0]

    raise RuntimeError(f"Could not resolve branch '{requested_branch}' from refs: {refs}")


def extract_commit_emails(repo_dir: Path, branch_ref: str):
    out = run_cmd(["git", "log", branch_ref, "--format=%ae"], cwd=repo_dir)
    emails = [line.strip() for line in out.splitlines() if line.strip()]
    if not emails:
        raise RuntimeError(f"No commits found on branch '{branch_ref}'")
    return emails


def top_commit_email(repo_dir: Path, branch_ref: str) -> str:
    emails = extract_commit_emails(repo_dir, branch_ref)
    counts = Counter(emails)
    return counts.most_common(1)[0][0]


def validate_output_schema(output_schema):
    if not isinstance(output_schema, dict):
        raise RuntimeError("output_schema must be an object")
    if output_schema.get("type") != "array":
        raise RuntimeError("This skill expects output_schema.type == 'array'")
    items = output_schema.get("items", {})
    if items.get("type") != "string":
        raise RuntimeError("This skill expects array items of type string")


def build_response(email: str):
    return {
        "status": "SUCCESS",
        "retrieved_data": [email],
        "error_details": None,
    }


def main():
    ensure_workspace()
    taskspec_path = Path(sys.argv[1])
    taskspec = json.loads(taskspec_path.read_text(encoding="utf-8"))

    params = taskspec.get("params", {})
    start_url = taskspec.get("start_url")
    output_schema = taskspec.get("output_schema", {})

    validate_output_schema(output_schema)

    branch = params.get("branch")
    if not branch:
        raise RuntimeError("Missing required params.branch")
    if not start_url:
        raise RuntimeError("Missing required start_url")

    repo_name = safe_repo_name(start_url)
    repo_dir = WORKSPACE / "tmp_repos" / f"{repo_name}.mirror"

    clone_repository_mirror(start_url, repo_dir)
    resolved_branch = resolve_branch_name(repo_dir, branch)
    email = top_commit_email(repo_dir, resolved_branch)

    response = build_response(email)
    write_json(WORKSPACE / "agent_response.json", response)


if __name__ == "__main__":
    main()
