from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional


def _run_git(args: List[str], cwd: Optional[Path] = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def _clone_mirror(repo_url: str, work_dir: Path) -> Path:
    repo_dir = work_dir / "repo.git"
    if repo_dir.exists():
        shutil.rmtree(repo_dir)
    subprocess.run(
        ["git", "clone", "--mirror", repo_url, str(repo_dir)],
        text=True,
        capture_output=True,
        check=True,
    )
    return repo_dir


def _list_refs(repo_dir: Path) -> List[str]:
    output = _run_git(["for-each-ref", "--format=%(refname:short)"], cwd=repo_dir)
    return [line.strip() for line in output.splitlines() if line.strip()]


def list_repository_commit_emails(repo_url: str, branch_hint: Optional[str] = None) -> Dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        work_dir = Path(tmp)
        repo_dir = _clone_mirror(repo_url, work_dir)
        refs = _list_refs(repo_dir)

        selected_ref = None
        if branch_hint:
            if branch_hint in refs:
                selected_ref = branch_hint
            else:
                matches = [ref for ref in refs if branch_hint in ref]
                if len(matches) == 1:
                    selected_ref = matches[0]

        if not selected_ref:
            raise ValueError("Unable to resolve target branch ref")

        output = _run_git(["log", selected_ref, "--format=%ae"], cwd=repo_dir)
        emails = [line.strip() for line in output.splitlines() if line.strip()]
        return {
            "branch": selected_ref,
            "refs": refs,
            "emails": emails,
        }
