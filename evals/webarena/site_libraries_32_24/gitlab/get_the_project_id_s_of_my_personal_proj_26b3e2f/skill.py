# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --param ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = []
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
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import Page, async_playwright


WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", os.getcwd()))
RUN_DIR = WORKSPACE / "skill_run"
SCREENSHOTS_DIR = RUN_DIR / "screenshots"
LOG_PATH = RUN_DIR / "skill_log.txt"
AGENT_RESPONSE_PATH = WORKSPACE / "agent_response.json"


def ensure_dirs() -> None:
    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("", encoding="utf-8")


def log(message: str) -> None:
    print(message)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


async def save_screenshot(page: Page, name: str) -> None:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("_") or "shot"
    await page.screenshot(path=str(SCREENSHOTS_DIR / f"{safe}.png"), full_page=True)


def load_taskspec(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def get_param(taskspec: Dict[str, Any], key: str, default: Any = None) -> Any:
    return taskspec.get("params", {}).get(key, default)


async def maybe_login(page: Page, start_url: str, credentials: Dict[str, Any]) -> None:
    await page.goto(start_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(1200)

    if "/users/sign_in" in page.url:
        username = credentials.get("username") or credentials.get("email") or credentials.get("login")
        password = credentials.get("password")
        if not username or not password:
            raise RuntimeError("Login required but username/password missing in taskspec.credentials")

        user_box = page.get_by_role("textbox", name=re.compile(r"Username or email", re.I))
        pass_box = page.get_by_role("textbox", name=re.compile(r"Password", re.I))
        sign_in_btn = page.get_by_role("button", name=re.compile(r"Sign in", re.I))

        await user_box.fill(str(username))
        await pass_box.fill(str(password))
        await sign_in_btn.click()
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1500)

    await save_screenshot(page, "after_login")


async def open_projects_dashboard(page: Page, start_url: str) -> None:
    await page.goto(f"{start_url.rstrip('/')}/dashboard/projects", wait_until="domcontentloaded")
    await page.wait_for_timeout(1200)


async def apply_personal_filter(page: Page, personal_label: str = "Personal") -> None:
    personal_link = page.get_by_role("link", name=re.compile(rf"^{re.escape(personal_label)}$", re.I))
    if await personal_link.count() > 0:
        await personal_link.first.click()
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1500)
    await save_screenshot(page, "personal_projects")


def parse_numeric_metrics_from_text(text: str) -> Optional[Tuple[int, int, int, int]]:
    m = re.search(
        r"\n\s*(\d+)\s*\n\s*(\d+)\s*\n\s*(\d+)\s*\n\s*(\d+)\s*\n\s*Updated",
        "\n" + text + "\n",
    )
    if not m:
        return None
    return tuple(map(int, m.groups()))  # stars, forks, merge_requests, issues


async def extract_project_title_and_href(li) -> Optional[Tuple[str, str]]:
    links = await li.locator("a").evaluate_all(
        """els => els.map(a => ({
            text: (a.innerText || '').trim(),
            href: a.getAttribute('href') || ''
        }))"""
    )
    for link in links:
        text = (link.get("text") or "").strip()
        href = (link.get("href") or "").strip()
        if text and "/" in text and not text.isdigit() and href:
            return text, href
    return None


async def extract_zero_star_project_paths_from_current_page(
    page: Page,
    star_count_target: int = 0,
) -> List[Tuple[str, str]]:
    items = page.locator("main .projects-list > li")
    count = await items.count()
    results: List[Tuple[str, str]] = []

    log(f"Found {count} project list items on current page")

    for i in range(count):
        li = items.nth(i)
        text = (await li.inner_text()).strip()
        title_info = await extract_project_title_and_href(li)
        metrics = parse_numeric_metrics_from_text(text)

        if not title_info or not metrics:
            continue

        title, href = title_info
        stars, forks, merge_requests, issues = metrics
        log(
            f"List item {i}: {title} | stars={stars} forks={forks} "
            f"merge_requests={merge_requests} issues={issues} href={href}"
        )

        if stars == star_count_target:
            results.append((title, href))

    return results


async def click_next_page_if_available(page: Page) -> bool:
    next_candidates = [
        page.get_by_role("link", name=re.compile(r"^\s*Next\s*$", re.I)),
        page.get_by_role("link", name=re.compile(r"^\s*›\s*$")),
        page.locator("a[rel='next']"),
        page.locator(".gl-pagination a[rel='next']"),
    ]

    for locator in next_candidates:
        if await locator.count() > 0:
            candidate = locator.first
            classes = (await candidate.get_attribute("class")) or ""
            aria_disabled = (await candidate.get_attribute("aria-disabled")) or ""
            if "disabled" in classes.lower() or aria_disabled.lower() == "true":
                continue
            href = await candidate.get_attribute("href")
            if href is None:
                continue
            await candidate.click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(1200)
            return True
    return False


async def collect_zero_star_project_paths_across_pages(
    page: Page,
    expected_total: Optional[int] = None,
    star_count_target: int = 0,
    max_pages: int = 100,
) -> List[Tuple[str, str]]:
    all_projects: List[Tuple[str, str]] = []
    seen_hrefs = set()
    pages_visited = 0

    while pages_visited < max_pages:
        pages_visited += 1
        current = await extract_zero_star_project_paths_from_current_page(page, star_count_target=star_count_target)
        for title, href in current:
            if href not in seen_hrefs:
                seen_hrefs.add(href)
                all_projects.append((title, href))

        log(f"After page {pages_visited}, collected {len(all_projects)} unique zero-star project candidates")
        await save_screenshot(page, f"projects_page_{pages_visited}")

        if expected_total is not None and len(all_projects) >= expected_total:
            break

        moved = await click_next_page_if_available(page)
        if not moved:
            break

    return all_projects


async def extract_project_id_and_verify_star_count(
    page: Page,
    start_url: str,
    href: str,
    expected_star_count: int = 0,
) -> Optional[int]:
    url = href if href.startswith("http://") or href.startswith("https://") else f"{start_url.rstrip('/')}{href}"
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_timeout(1200)

    body = await page.locator("body").inner_text()

    id_match = re.search(r"Project ID:\s*(\d+)", body)
    star_match = re.search(r"\bStar\s*(\d+)\b", body)

    project_id = int(id_match.group(1)) if id_match else None
    star_count = int(star_match.group(1)) if star_match else None

    log(f"Visited project page {url} | project_id={project_id} | star_count={star_count}")

    if project_id is not None and star_count == expected_star_count:
        return project_id
    return None


async def retrieve_personal_project_ids_with_no_stars(taskspec: Dict[str, Any]) -> List[int]:
    start_url = taskspec["start_url"]
    credentials = taskspec.get("credentials", {})

    personal_label = get_param(taskspec, "personal_filter_label", "Personal")
    expected_total = get_param(taskspec, "expected_total", None)
    star_count_target = int(get_param(taskspec, "star_count_target", 0))
    max_pages = int(get_param(taskspec, "max_pages", 100))

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 1800})
        page = await context.new_page()

        try:
            log("Opening site and logging in if required")
            await maybe_login(page, start_url, credentials)

            log("Opening projects dashboard")
            await open_projects_dashboard(page, start_url)

            log("Applying personal filter")
            await apply_personal_filter(page, personal_label=personal_label)

            log("Collecting zero-star personal projects across pages")
            projects = await collect_zero_star_project_paths_across_pages(
                page,
                expected_total=expected_total,
                star_count_target=star_count_target,
                max_pages=max_pages,
            )

            log(f"Collected {len(projects)} candidate personal projects with star_count={star_count_target}")

            ids: List[int] = []
            seen_ids = set()

            for idx, (title, href) in enumerate(projects, start=1):
                log(f"Resolving project {idx}/{len(projects)}: {title} {href}")
                project_id = await extract_project_id_and_verify_star_count(
                    page,
                    start_url=start_url,
                    href=href,
                    expected_star_count=star_count_target,
                )
                await save_screenshot(page, f"project_{idx}")
                if project_id is not None and project_id not in seen_ids:
                    seen_ids.add(project_id)
                    ids.append(project_id)

            ids.sort()

            if expected_total is not None and len(ids) != expected_total:
                log(f"Warning: expected_total={expected_total}, but resolved_ids={len(ids)}")

            return ids
        finally:
            await context.close()
            await browser.close()


def write_response(retrieved_data: Optional[List[int]], error_details: Optional[str] = None) -> None:
    status = "SUCCESS" if retrieved_data is not None else "NOT_FOUND_ERROR"
    payload = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    AGENT_RESPONSE_PATH.write_text(json.dumps(payload), encoding="utf-8")


async def main() -> None:
    ensure_dirs()
    taskspec_path = sys.argv[1]
    taskspec = load_taskspec(taskspec_path)

    try:
        ids = await retrieve_personal_project_ids_with_no_stars(taskspec)
        write_response(ids)
        log(f"Final IDs: {ids}")
    except Exception as e:
        log(f"ERROR: {e}")
        write_response(None, error_details=str(e))


if __name__ == "__main__":
    asyncio.run(main())
