# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --title ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['title', 'body_request', 'repo']
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
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote

from playwright.async_api import async_playwright, Page, BrowserContext


def get_workspace_dir() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", os.getcwd())).resolve()


WORKSPACE = get_workspace_dir()
LOG_PATH = WORKSPACE / "skill.log"


def log(msg: str) -> None:
    print(msg)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def load_taskspec(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_agent_response(
    status: str,
    retrieved_data: Optional[Dict[str, Any]],
    error_details: Optional[str] = None,
) -> None:
    response = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    out_path = WORKSPACE / "agent_response.json"
    out_path.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")


def normalize_output(params: Dict[str, Any], output_schema: Dict[str, Any]) -> Dict[str, Any]:
    props = output_schema.get("properties", {})
    result: Dict[str, Any] = {}
    for key in props.keys():
        result[key] = params.get(key)
    return result


def null_output(output_schema: Dict[str, Any]) -> Dict[str, Any]:
    props = output_schema.get("properties", {})
    return {key: None for key in props.keys()}


def get_credentials(taskspec: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    creds = taskspec.get("credentials") or {}
    username = (
        creds.get("username")
        or creds.get("email")
        or creds.get("login")
        or creds.get("user")
    )
    password = creds.get("password") or creds.get("pass")
    return username, password


def build_base_url(taskspec: Dict[str, Any]) -> str:
    start_url = (taskspec.get("start_url") or "").rstrip("/")
    if start_url:
        return start_url
    raise ValueError("Missing start_url in taskspec")


def repo_path_from_param(repo: str) -> str:
    return "/" + "/".join(quote(part.strip(), safe="") for part in repo.split("/") if part.strip())


async def screenshot(page: Page, name: str) -> None:
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    await page.screenshot(path=str(WORKSPACE / safe_name), full_page=True)


async def login(page: Page, base_url: str, username: str, password: str) -> None:
    log("Opening sign-in page")
    await page.goto(f"{base_url}/users/sign_in", wait_until="domcontentloaded")
    await page.get_by_label("Username or email").fill(username)
    await page.get_by_label("Password").fill(password)
    await screenshot(page, "01_login.png")
    await page.get_by_role("button", name="Sign in").click()
    await page.wait_for_load_state("domcontentloaded")
    log(f"Logged in, current URL: {page.url}")


async def open_repository(page: Page, base_url: str, repo: str) -> None:
    path = repo_path_from_param(repo)
    url = f"{base_url}{path}"
    log(f"Opening repository URL: {url}")
    await page.goto(url, wait_until="domcontentloaded")
    await screenshot(page, "02_repository.png")


async def repository_exists(page: Page, base_url: str, repo: str) -> bool:
    current_url = page.url.rstrip("/")
    expected_url = f"{base_url}{repo_path_from_param(repo)}".rstrip("/")

    body_text = ""
    try:
        body_text = (await page.locator("body").inner_text()).lower()
    except Exception:
        pass

    title = ""
    try:
        title = (await page.title()).lower()
    except Exception:
        pass

    not_found_markers = [
        "page not found",
        "404",
        "the page could not be found",
        "not found",
    ]

    if any(marker in title for marker in not_found_markers):
        return False
    if any(marker in body_text for marker in not_found_markers):
        if current_url == expected_url or "gitlab" in body_text:
            return False

    return current_url.startswith(expected_url)


async def search_repository(page: Page, base_url: str, repo: str) -> bool:
    terms = [t for t in repo.replace("/", " ").split() if t]
    for i, term in enumerate(terms[:5], start=1):
        search_url = f"{base_url}/search?search={quote(term)}&group_id=&project_id=&snippets=false&repository_ref="
        log(f"Searching for repository term: {term}")
        await page.goto(search_url, wait_until="domcontentloaded")
        await screenshot(page, f"03_search_{i}_{term}.png")
        body_text = (await page.locator("body").inner_text()).lower()
        if term.lower() in body_text and any(part.lower() in body_text for part in terms):
            return True
    return False


async def try_open_new_issue(page: Page, base_url: str, repo: str, title: str, body_request: str) -> bool:
    repo_path = repo_path_from_param(repo)
    candidates = [
        f"{base_url}{repo_path}/-/issues/new",
        f"{base_url}{repo_path}/issues/new",
    ]

    for idx, url in enumerate(candidates, start=1):
        log(f"Trying issue creation page: {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await screenshot(page, f"04_issue_new_attempt_{idx}.png")
        body_text = (await page.locator("body").inner_text()).lower()
        page_title = (await page.title()).lower()

        if "new issue" not in body_text and "new issue" not in page_title and "issue" not in body_text:
            continue

        title_filled = False
        body_filled = False

        title_selectors = [
            page.get_by_label("Title"),
            page.locator('input[name="issue[title]"]'),
            page.locator("#issue_title"),
            page.locator('input[placeholder*="Title"]'),
        ]
        for loc in title_selectors:
            try:
                if await loc.count() > 0:
                    await loc.first.fill(title)
                    title_filled = True
                    break
            except Exception:
                continue

        body_selectors = [
            page.get_by_label("Description"),
            page.locator('textarea[name="issue[description]"]'),
            page.locator("#issue_description"),
            page.locator("textarea"),
        ]
        for loc in body_selectors:
            try:
                if await loc.count() > 0:
                    await loc.first.fill(body_request)
                    body_filled = True
                    break
            except Exception:
                continue

        await screenshot(page, "05_issue_filled.png")

        if not (title_filled and body_filled):
            continue

        submit_candidates = [
            page.get_by_role("button", name="Create issue"),
            page.get_by_role("button", name="Submit issue"),
            page.get_by_role("button", name="Create"),
            page.locator('input[type="submit"]'),
            page.locator('button[type="submit"]'),
        ]
        for btn in submit_candidates:
            try:
                if await btn.count() > 0:
                    await btn.first.click()
                    await page.wait_for_load_state("domcontentloaded")
                    await screenshot(page, "06_issue_submitted.png")
                    body_after = (await page.locator("body").inner_text()).lower()
                    title_after = (await page.title()).lower()
                    if any(
                        marker in body_after or marker in title_after
                        for marker in ["issue", title.lower()]
                    ):
                        log("Issue submission appears successful")
                        return True
            except Exception:
                continue

    return False


async def create_issue_flow(
    context: BrowserContext,
    taskspec: Dict[str, Any],
) -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
    params = taskspec.get("params") or {}
    output_schema = taskspec.get("output_schema") or {}
    base_url = build_base_url(taskspec)
    username, password = get_credentials(taskspec)

    repo = params.get("repo")
    title = params.get("title")
    body_request = params.get("body_request")

    if not all([repo, title, body_request, username, password]):
        return "ERROR", None, "Missing required params or credentials"

    page = await context.new_page()
    await login(page, base_url, username, password)

    await open_repository(page, base_url, repo)
    exists = await repository_exists(page, base_url, repo)
    if not exists:
        log("Repository not directly accessible; performing search verification")
        found_in_search = await search_repository(page, base_url, repo)
        if not found_in_search:
            return "NOT_FOUND_ERROR", None, f"Repository not found or inaccessible: {repo}"

    created = await try_open_new_issue(page, base_url, repo, title, body_request)
    if not created:
        return "ERROR", None, f"Unable to create issue in repository: {repo}"

    return "SUCCESS", normalize_output(params, output_schema), None


async def main() -> None:
    LOG_PATH.write_text("", encoding="utf-8")
    taskspec = load_taskspec(sys.argv[1])

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1440, "height": 1800})

            status, retrieved_data, error_details = await create_issue_flow(context, taskspec)

            await browser.close()

        if status == "SUCCESS":
            write_agent_response(status, retrieved_data, None)
        elif status == "NOT_FOUND_ERROR":
            write_agent_response(status, None, error_details)
        else:
            write_agent_response(status, None, error_details)

    except Exception as e:
        log(f"Unhandled exception: {e}")
        write_agent_response("ERROR", None, str(e))


if __name__ == "__main__":
    asyncio.run(main())
