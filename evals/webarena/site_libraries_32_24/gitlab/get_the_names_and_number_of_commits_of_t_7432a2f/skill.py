# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --count ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['count', 'repo']
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
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Page


def get_workspace_dir() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", os.getcwd())).resolve()


WORKSPACE_DIR = get_workspace_dir()
LOG_PATH = WORKSPACE_DIR / "skill.log"
SCREENSHOT_DIR = WORKSPACE_DIR / "screenshots"
AGENT_RESPONSE_PATH = WORKSPACE_DIR / "agent_response.json"


def log(message: str) -> None:
    print(message)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def ensure_dirs() -> None:
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("", encoding="utf-8")


def load_taskspec(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_agent_response(status: str, retrieved_data: Any, error_details: Optional[str]) -> None:
    AGENT_RESPONSE_PATH.write_text(
        json.dumps(
            {
                "task_type": "RETRIEVE",
                "status": status,
                "retrieved_data": retrieved_data,
                "error_details": error_details,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def parse_repo_path(repo: str) -> str:
    repo = repo.strip().strip("/")
    return repo


def default_branch_candidates() -> List[str]:
    return ["main", "master"]


def split_name(full_name: str) -> Tuple[str, str]:
    clean = " ".join(full_name.split()).strip()
    if not clean:
        return "", ""
    parts = clean.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


async def screenshot(page: Page, name: str) -> None:
    try:
        await page.screenshot(path=str(SCREENSHOT_DIR / name), full_page=True)
    except Exception as e:
        log(f"screenshot failed for {name}: {e}")


async def login(page: Page, start_url: str, credentials: Dict[str, Any]) -> None:
    username = credentials.get("username") or credentials.get("email") or credentials.get("user")
    password = credentials.get("password")
    if not username or not password:
        raise ValueError("Missing credentials.username/email and/or credentials.password")

    login_url = f"{start_url.rstrip('/')}/users/sign_in"
    log(f"Opening login page: {login_url}")
    await page.goto(login_url, wait_until="domcontentloaded")
    await page.get_by_label("Username or email").fill(str(username))
    await page.get_by_label("Password").fill(str(password))
    await page.get_by_role("button", name=re.compile(r"sign in", re.I)).click()
    await page.wait_for_load_state("networkidle")
    await screenshot(page, "01_after_login.png")
    log(f"Post-login URL: {page.url}")


async def try_open_graphs_page(page: Page, start_url: str, repo_path: str, branch: str) -> bool:
    url = f"{start_url.rstrip('/')}/{repo_path}/-/graphs/{branch}"
    log(f"Trying contributors page: {url}")
    await page.goto(url, wait_until="networkidle")
    await screenshot(page, f"02_graphs_{branch}.png")
    text = await page.locator("body").inner_text()
    lowered = text.lower()
    if "404" in lowered or "page not found" in lowered or "not found" in lowered:
        return False
    if "/-/graphs/" not in page.url and page.url.rstrip("/") != url.rstrip("/"):
        # Still may be valid, continue to parse body if content exists.
        pass
    return True


def parse_contributors_from_text(text: str) -> List[Tuple[str, int]]:
    patterns = [
        re.compile(r"([A-Za-z][A-Za-z0-9.'\-\[\] ]*[A-Za-z0-9\]])\n\n(\d+)\s+commits?\s+\(", re.M),
        re.compile(r"([A-Za-z][A-Za-z0-9.'\-\[\] ]*[A-Za-z0-9\]])\s*\n+\s*(\d+)\s+commits?\s+\(", re.M),
        re.compile(r"([A-Za-z][A-Za-z0-9.'\-\[\] ]*[A-Za-z0-9\]])\s+(\d+)\s+commits?\s+\(", re.M),
    ]

    results: List[Tuple[str, int]] = []
    seen = set()

    for pattern in patterns:
        for name, commits in pattern.findall(text):
            clean_name = " ".join(str(name).split()).strip()
            commit_count = int(commits)
            key = (clean_name, commit_count)
            if clean_name and key not in seen:
                seen.add(key)
                results.append((clean_name, commit_count))
        if results:
            break

    if not results:
        generic = re.findall(r"([A-Z][A-Za-z0-9.'\-\[\] ]{1,80})\s*\n+\s*(\d+)\s+commits?", text, re.M)
        for name, commits in generic:
            clean_name = " ".join(name.split()).strip()
            if clean_name.lower() in {"contributors", "commit activity", "all time"}:
                continue
            key = (clean_name, int(commits))
            if key not in seen:
                seen.add(key)
                results.append((clean_name, int(commits)))

    return results


async def extract_contributors(page: Page) -> List[Tuple[str, int]]:
    main_locator = page.locator("main")
    text = await main_locator.inner_text() if await main_locator.count() > 0 else await page.locator("body").inner_text()
    log("Captured page text excerpt:")
    log(text[:5000])
    contributors = parse_contributors_from_text(text)
    if contributors:
        log(f"Parsed contributors: {contributors[:10]}")
        return contributors

    all_text = await page.evaluate("document.body.innerText")
    contributors = parse_contributors_from_text(all_text)
    log(f"Fallback parsed contributors: {contributors[:10]}")
    return contributors


def normalize_and_validate(contributors: List[Tuple[str, int]], count: int) -> List[Dict[str, Any]]:
    deduped: List[Tuple[str, int]] = []
    seen_names = set()
    for name, commits in contributors:
        if name in seen_names:
            continue
        seen_names.add(name)
        deduped.append((name, commits))

    deduped.sort(key=lambda x: x[1], reverse=True)
    top = deduped[:count]

    result = []
    for name, commits in top:
        first, last = split_name(name)
        result.append(
            {
                "first_name": first,
                "last_name": last,
                "number_of_commits": commits,
            }
        )
    return result


async def get_top_contributors(page: Page, start_url: str, repo: str, count: int) -> List[Dict[str, Any]]:
    repo_path = parse_repo_path(repo)

    opened = False
    for branch in default_branch_candidates():
        if await try_open_graphs_page(page, start_url, repo_path, branch):
            contributors = await extract_contributors(page)
            if contributors:
                opened = True
                result = normalize_and_validate(contributors, count)
                if len(result) >= min(count, len(contributors)):
                    return result

    if not opened:
        raise RuntimeError(f"Could not open contributors page for repo '{repo_path}' using known branches.")

    raise RuntimeError(f"Failed to parse contributor data for repo '{repo_path}'.")


async def run(taskspec: Dict[str, Any]) -> None:
    params = taskspec.get("params", {})
    start_url = taskspec.get("start_url")
    credentials = taskspec.get("credentials", {})
    output_schema = taskspec.get("output_schema")

    if not start_url:
        raise ValueError("taskspec.start_url is required")
    if not isinstance(params, dict):
        raise ValueError("taskspec.params must be an object")

    repo = params.get("repo")
    count_raw = params.get("count")
    if not repo:
        raise ValueError("params.repo is required")
    if count_raw is None:
        raise ValueError("params.count is required")
    count = int(count_raw)

    if output_schema and output_schema.get("type") != "array":
        log("Warning: output_schema.type is not 'array'; proceeding with array output for this template.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 1800})
        page = await context.new_page()
        try:
            await login(page, start_url, credentials)
            data = await get_top_contributors(page, start_url, repo, count)
            await screenshot(page, "03_final_page.png")
            write_agent_response("SUCCESS", data, None)
            log(f"Final retrieved_data: {json.dumps(data, ensure_ascii=False)}")
        finally:
            await browser.close()


def main() -> None:
    ensure_dirs()
    try:
        if len(sys.argv) < 2:
            raise ValueError("Expected taskspec.json path as argv[1]")
        taskspec = load_taskspec(sys.argv[1])
        asyncio.run(run(taskspec))
    except Exception as e:
        log(f"ERROR: {e}")
        write_agent_response("ERROR", [], str(e))


if __name__ == "__main__":
    main()
