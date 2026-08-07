# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --author ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['author', 'start_month_year', 'end_month_year']
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

import asyncio
import calendar
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import async_playwright


def get_workspace_dir() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", os.getcwd())).resolve()


WORKSPACE_DIR = get_workspace_dir()
LOG_PATH = WORKSPACE_DIR / "skill_log.txt"
SCREENSHOT_DIR = WORKSPACE_DIR / "screenshots"
AGENT_RESPONSE_PATH = WORKSPACE_DIR / "agent_response.json"


def log(msg: str) -> None:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)


def read_taskspec(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_agent_response(retrieved_data: Any, status: str = "SUCCESS", error_details: Optional[str] = None) -> None:
    payload = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    AGENT_RESPONSE_PATH.write_text(json.dumps(payload), encoding="utf-8")


def ensure_output_matches_schema(data: Any, output_schema: Dict[str, Any]) -> None:
    if output_schema.get("type") != "array":
        raise ValueError("Only array output_schema is supported by this skill.")
    if not isinstance(data, list):
        raise ValueError("retrieved_data must be a list.")
    item_schema = output_schema.get("items", {})
    if item_schema.get("type") == "number":
        for item in data:
            if not isinstance(item, (int, float)) or isinstance(item, bool):
                raise ValueError("Each retrieved_data item must be a number.")
    else:
        raise ValueError("Only array-of-number output_schema is supported by this skill.")


def parse_month_year(value: str) -> Tuple[int, int]:
    value = value.strip()
    for fmt in ("%B %Y", "%b %Y"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.year, dt.month
        except ValueError:
            pass
    raise ValueError(f"Could not parse month/year value: {value!r}")


def month_range_to_iso_bounds(start_month_year: str, end_month_year: str) -> Tuple[str, str]:
    start_year, start_month = parse_month_year(start_month_year)
    end_year, end_month = parse_month_year(end_month_year)
    start_dt = datetime(start_year, start_month, 1, 0, 0, 0, tzinfo=timezone.utc)
    last_day = calendar.monthrange(end_year, end_month)[1]
    end_dt = datetime(end_year, end_month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    if end_dt < start_dt:
        raise ValueError("end_month_year must not be earlier than start_month_year.")
    return (
        start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def build_commits_page_url(start_url: str, branch: str = "main") -> str:
    return start_url.rstrip("/") + f"/-/commits/{branch}"


def parse_gitlab_project_id_from_html(html: str) -> Optional[int]:
    patterns = [
        r'projectId["\']?\s*[:=]\s*["\']?(\d+)',
        r'project_id["\']?\s*[:=]\s*["\']?(\d+)',
        r'data-project-id=["\'](\d+)["\']',
        r'"project_id"\s*:\s*(\d+)',
        r'"projectId"\s*:\s*(\d+)',
    ]
    for pattern in patterns:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def derive_api_base(start_url: str, project_id: int) -> str:
    parsed = urllib.parse.urlparse(start_url)
    root = f"{parsed.scheme}://{parsed.netloc}"
    return f"{root}/api/v4/projects/{project_id}/repository/commits"


def parse_link_header(link_header: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if not link_header:
        return result
    for part in link_header.split(","):
        section = part.strip()
        m = re.match(r'<([^>]+)>\s*;\s*rel="([^"]+)"', section)
        if m:
            result[m.group(2)] = m.group(1)
    return result


def http_get_json(url: str, headers: Optional[Dict[str, str]] = None) -> Tuple[Any, Dict[str, str]]:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req) as resp:
        body = resp.read().decode("utf-8")
        response_headers = dict(resp.headers.items())
    return json.loads(body), response_headers


def fetch_all_commits(api_base: str, since_iso: str, until_iso: str, per_page: int = 100) -> List[Dict[str, Any]]:
    page = 1
    all_commits: List[Dict[str, Any]] = []
    declared_total: Optional[int] = None

    while True:
        query = urllib.parse.urlencode(
            {
                "since": since_iso,
                "until": until_iso,
                "per_page": str(per_page),
                "page": str(page),
            }
        )
        url = f"{api_base}?{query}"
        commits, headers = http_get_json(url)
        if not isinstance(commits, list):
            raise RuntimeError(f"Unexpected commits API payload at page {page}: expected list.")
        all_commits.extend(commits)

        if declared_total is None:
            total_header = headers.get("X-Total") or headers.get("x-total")
            if total_header and str(total_header).isdigit():
                declared_total = int(total_header)

        next_page = headers.get("X-Next-Page") or headers.get("x-next-page") or ""
        link_header = headers.get("Link") or headers.get("link") or ""
        links = parse_link_header(link_header)

        log(
            f"Fetched commits page={page} count={len(commits)} "
            f"x_total={headers.get('X-Total') or headers.get('x-total')} "
            f"x_next_page={next_page!r}"
        )

        if next_page:
            page = int(next_page)
            continue
        if "next" in links:
            page += 1
            continue
        break

    if declared_total is not None and declared_total != len(all_commits):
        raise RuntimeError(
            f"Pagination self-check failed: X-Total declared {declared_total}, fetched {len(all_commits)} commits."
        )

    return all_commits


def author_matches(commit_author_name: str, target_author: str) -> bool:
    return target_author.strip().lower() in (commit_author_name or "").strip().lower()


def count_author_commits(commits: List[Dict[str, Any]], author: str) -> int:
    matches = [c for c in commits if author_matches(c.get("author_name", ""), author)]
    for c in matches:
        log(
            "MATCH "
            f"authored_date={c.get('authored_date')} "
            f"author_name={c.get('author_name')} "
            f"short_id={c.get('short_id')} "
            f"title={c.get('title')}"
        )
    if not matches:
        log("MATCH none")
    return len(matches)


async def open_and_capture_repository_context(page, start_url: str, branch: str) -> Tuple[str, Optional[int]]:
    await page.goto(start_url, wait_until="domcontentloaded")
    await page.screenshot(path=str(SCREENSHOT_DIR / "01_repository_home.png"))

    title = await page.title()
    html = await page.content()
    body_text = await page.locator("body").inner_text()
    project_id = parse_gitlab_project_id_from_html(html)
    log(f"Repository page loaded: url={page.url} title={title} project_id={project_id} body_snippet={body_text[:500].replace(chr(10), ' | ')}")

    commits_url = build_commits_page_url(start_url, branch=branch)
    await page.goto(commits_url, wait_until="domcontentloaded")
    await page.screenshot(path=str(SCREENSHOT_DIR / "02_commits_page.png"))
    commits_title = await page.title()
    commits_body = await page.locator("body").inner_text()
    if project_id is None:
        commits_html = await page.content()
        project_id = parse_gitlab_project_id_from_html(commits_html)

    log(f"Commits page loaded: url={page.url} title={commits_title} project_id={project_id} body_snippet={commits_body[:800].replace(chr(10), ' | ')}")
    return commits_url, project_id


def infer_branch(taskspec: Dict[str, Any]) -> str:
    params = taskspec.get("params", {}) or {}
    return params.get("branch", "main")


def extract_task_params(taskspec: Dict[str, Any]) -> Tuple[str, str, str]:
    params = taskspec.get("params", {}) or {}
    author = params.get("author")
    start_month_year = params.get("start_month_year")
    end_month_year = params.get("end_month_year")
    if not author or not start_month_year or not end_month_year:
        raise ValueError("taskspec.params must include author, start_month_year, and end_month_year.")
    return author, start_month_year, end_month_year


async def run() -> None:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("", encoding="utf-8")

    taskspec_path = sys.argv[1]
    taskspec = read_taskspec(taskspec_path)

    author, start_month_year, end_month_year = extract_task_params(taskspec)
    start_url = taskspec.get("start_url")
    output_schema = taskspec.get("output_schema")
    branch = infer_branch(taskspec)

    if not start_url:
        raise ValueError("taskspec.start_url is required.")

    since_iso, until_iso = month_range_to_iso_bounds(start_month_year, end_month_year)
    log(
        f"Task params: author={author!r} start_month_year={start_month_year!r} "
        f"end_month_year={end_month_year!r} since={since_iso} until={until_iso} branch={branch!r}"
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 1800})
        page = await context.new_page()

        _, project_id = await open_and_capture_repository_context(page, start_url, branch)
        if project_id is None:
            raise RuntimeError("Could not determine GitLab project ID from repository pages.")

        api_base = derive_api_base(start_url, project_id)
        log(f"Derived commits API base: {api_base}")

        commits = fetch_all_commits(api_base, since_iso, until_iso, per_page=100)
        total_count = len(commits)
        author_count = count_author_commits(commits, author)
        log(f"Computed author commit count: author={author!r} count={author_count} total_in_window={total_count}")

        result_html = f"""
        <html><body style="font-family:Arial,sans-serif;padding:24px;">
        <h1>Computed Result</h1>
        <p>Start URL: {start_url}</p>
        <p>Project ID: {project_id}</p>
        <p>Branch: {branch}</p>
        <p>Author filter: {author}</p>
        <p>Date range: {start_month_year} through {end_month_year}</p>
        <p>ISO bounds: {since_iso} to {until_iso}</p>
        <p>Total commits in range: {total_count}</p>
        <p>Matching author commits: <strong>{author_count}</strong></p>
        </body></html>
        """
        await page.set_content(result_html)
        await page.screenshot(path=str(SCREENSHOT_DIR / "03_result.png"))

        await browser.close()

    retrieved_data = [author_count]
    ensure_output_matches_schema(retrieved_data, output_schema)
    write_agent_response(retrieved_data)
    log(f"FINAL_RESPONSE retrieved_data={retrieved_data}")


def main() -> None:
    try:
        asyncio.run(run())
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        log(err)
        write_agent_response([], status="ERROR", error_details=err)


if __name__ == "__main__":
    main()
