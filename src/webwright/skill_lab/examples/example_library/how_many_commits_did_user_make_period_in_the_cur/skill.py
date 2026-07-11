import sys
import json
import re
import subprocess
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta, timezone


def load_taskspec(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_agent_response(retrieved_data, status="SUCCESS", error_details=None):
    response = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    Path("agent_response.json").write_text(
        json.dumps(response, ensure_ascii=False), encoding="utf-8"
    )


def start_url_to_git_url(start_url: str) -> str:
    return start_url[:-1] + ".git" if start_url.endswith("/") else start_url + ".git"


def infer_branch_from_start_url(start_url: str) -> str:
    return "main"


def parse_period_to_range(period_text: str):
    text = period_text.strip()

    m = re.fullmatch(r"on ([A-Za-z]+) (\d+)(?:st|nd|rd|th)? (\d{4})", text, re.I)
    if m:
        month_name, day, year = m.groups()
        start = datetime.strptime(f"{year} {month_name} {day}", "%Y %B %d").replace(tzinfo=timezone.utc)
        end = start + timedelta(days=1) - timedelta(seconds=1)
        return start, end

    m = re.fullmatch(
        r"between start of ([A-Za-z]{3,9}) (\d{4}) and end of ([A-Za-z]{3,9}) (\d{4})",
        text,
        re.I,
    )
    if m:
        smonth, syear, emonth, eyear = m.groups()
        start = datetime.strptime(f"{syear} {smonth} 1", "%Y %B %d").replace(tzinfo=timezone.utc)
        if len(emonth) == 3:
            em = datetime.strptime(emonth, "%b").month
        else:
            em = datetime.strptime(emonth, "%B").month
        ey = int(eyear)
        if em == 12:
            next_month = datetime(ey + 1, 1, 1, tzinfo=timezone.utc)
        else:
            next_month = datetime(ey, em + 1, 1, tzinfo=timezone.utc)
        end = next_month - timedelta(seconds=1)
        return start, end

    raise ValueError(f"Unsupported period format: {period_text}")


def clone_repository(repo_url: str, target_dir: Path):
    subprocess.run(
        ["git", "clone", "--depth", "1000", repo_url, str(target_dir)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def count_commits_with_git(repo_dir: Path, author: str, start_dt: datetime, end_dt: datetime, branch: str = "main") -> int:
    cmd = [
        "git",
        "-C",
        str(repo_dir),
        "log",
        branch,
        "--since",
        start_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "--until",
        end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "--author",
        author,
        "--pretty=format:%H",
    ]
    out = subprocess.check_output(cmd, text=True)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return len(lines)


def retrieve_commit_count(taskspec: dict):
    params = taskspec.get("params", {})
    user = params["user"]
    period = params["period"]
    start_url = taskspec["start_url"]

    start_dt, end_dt = parse_period_to_range(period)
    repo_url = start_url_to_git_url(start_url)
    branch = infer_branch_from_start_url(start_url)

    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = Path(tmp) / "repo"
        clone_repository(repo_url, repo_dir)
        count = count_commits_with_git(repo_dir, user, start_dt, end_dt, branch)

    return [count]


def main():
    try:
        taskspec = load_taskspec(sys.argv[1])
        retrieved_data = retrieve_commit_count(taskspec)
        write_agent_response(retrieved_data)
    except Exception as e:
        write_agent_response([], status="ERROR", error_details=f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
