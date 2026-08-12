# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --term ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['term']
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
from typing import Optional, Tuple

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


def ensure_workspace() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", Path.cwd()))


WORKSPACE = ensure_workspace()
FINAL_RUNS = WORKSPACE / "final_runs"
FINAL_RUNS.mkdir(parents=True, exist_ok=True)

existing_ids = sorted(
    int(p.name.split("_")[-1])
    for p in FINAL_RUNS.glob("run_*")
    if p.name.split("_")[-1].isdigit()
)
RUN_ID = (existing_ids[-1] + 1) if existing_ids else 1
RUN_DIR = FINAL_RUNS / f"run_{RUN_ID:03d}"
SCREENSHOTS_DIR = RUN_DIR / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = RUN_DIR / "final_script_log.txt"
AGENT_RESPONSE_PATH = WORKSPACE / "agent_response.json"

LOG_FILE.write_text("", encoding="utf-8")


def log(message: str) -> None:
    print(message)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def load_taskspec(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def copy_self_artifact() -> None:
    src = Path(__file__)
    if src.exists():
        shutil.copy2(src, RUN_DIR / "final_script.py")


def get_param(taskspec: dict, name: str, default=None):
    return taskspec.get("params", {}).get(name, default)


def normalize_base_url(start_url: str) -> str:
    return start_url.rstrip("/")


def reviews_url_from_start(start_url: str) -> str:
    base = normalize_base_url(start_url)
    if base.endswith("/admin"):
        return base + "/review/product/index/"
    return base + "/admin/review/product/index/"


def extract_credentials(taskspec: dict) -> Tuple[str, str]:
    creds = taskspec.get("credentials") or {}
    username = (
        creds.get("username")
        or creds.get("user")
        or creds.get("email")
        or "admin"
    )
    password = creds.get("password") or creds.get("pass") or "admin1234"
    return username, password


async def safe_screenshot(page, name: str) -> None:
    try:
        await page.screenshot(path=str(SCREENSHOTS_DIR / f"{name}.png"), full_page=True)
    except Exception as e:
        log(f"screenshot failed for {name}: {e}")


async def wait_for_grid_refresh(page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except PlaywrightTimeoutError:
        pass
    await page.wait_for_timeout(1500)


async def login_if_needed(page, start_url: str, username: str, password: str) -> None:
    log(f"open admin start page: {start_url}")
    await page.goto(start_url, wait_until="domcontentloaded")
    await wait_for_grid_refresh(page)
    await safe_screenshot(page, "01_open_start")

    if "dashboard" in page.url.lower():
        log("already logged in; dashboard detected")
        return

    username_selectors = [
        'input[name="login[username]"]',
        'input[name="username"]',
        "#username",
        'input[type="text"]',
    ]
    password_selectors = [
        'input[name="login[password]"]',
        'input[name="password"]',
        'input[type="password"]',
        "#login",
    ]

    user_filled = False
    for sel in username_selectors:
        try:
            locator = page.locator(sel).first
            if await locator.count():
                await locator.fill(username)
                user_filled = True
                break
        except Exception:
            continue

    pass_filled = False
    for sel in password_selectors:
        try:
            locator = page.locator(sel).first
            if await locator.count():
                await locator.fill(password)
                pass_filled = True
                break
        except Exception:
            continue

    if not user_filled or not pass_filled:
        raise RuntimeError("Could not locate admin login fields.")

    log("filled admin credentials and submitting login form")
    await safe_screenshot(page, "02_login_filled")
    await page.get_by_role("button", name=re.compile(r"sign in", re.I)).click()
    await wait_for_grid_refresh(page)
    await safe_screenshot(page, "03_after_login")

    if "dashboard" not in page.url.lower() and "/admin" not in page.url.lower():
        log(f"post-login URL unusual: {page.url}")


async def open_reviews_grid(page, reviews_url: str) -> None:
    log(f"navigate to reviews grid: {reviews_url}")
    await page.goto(reviews_url, wait_until="domcontentloaded")
    await wait_for_grid_refresh(page)
    await safe_screenshot(page, "04_reviews_grid")


async def apply_review_detail_filter(page, term: str) -> None:
    log(f"apply review detail filter with term: {term}")
    filter_locator = page.locator("#reviewGrid_filter_detail")
    await filter_locator.fill(term)
    await safe_screenshot(page, "05_filter_filled")
    await page.get_by_role("button", name=re.compile(r"search", re.I)).click()
    await wait_for_grid_refresh(page)
    await safe_screenshot(page, "06_filter_results")


async def parse_declared_result_count(page) -> Optional[int]:
    body = await page.locator("body").inner_text()
    patterns = [
        r"(\d+)\s+records found",
        r"(\d+)\s+record[s]?\s+found",
    ]
    for pattern in patterns:
        m = re.search(pattern, body, re.I)
        if m:
            return int(m.group(1))
    return None


async def count_grid_rows(page) -> int:
    table_rows = page.locator("#reviewGrid_table tbody tr")
    count = await table_rows.count()
    if count == 1:
        txt = (await table_rows.nth(0).inner_text()).strip().lower()
        if "no records found" in txt:
            return 0
    return count


async def extract_first_rows_for_log(page, limit: int = 5) -> None:
    rows = page.locator("#reviewGrid_table tbody tr")
    total = await rows.count()
    for i in range(min(total, limit)):
        try:
            txt = await rows.nth(i).inner_text()
            log(f"row {i + 1}: {txt[:400].replace(chr(10), ' | ')}")
        except Exception as e:
            log(f"failed to read row {i + 1}: {e}")


async def verify_filtered_rows_on_page(page, term: str) -> int:
    rows = page.locator("#reviewGrid_table tbody tr")
    total = await count_grid_rows(page)
    exact = 0
    for i in range(total):
        try:
            txt = await rows.nth(i).inner_text()
            if term.lower() in txt.lower():
                exact += 1
        except Exception:
            pass
    return exact


def write_agent_response(status: str, retrieved_data, error_details=None) -> None:
    payload = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    AGENT_RESPONSE_PATH.write_text(json.dumps(payload), encoding="utf-8")
    log(f"wrote agent_response.json: {json.dumps(payload)}")


async def run() -> None:
    taskspec_path = sys.argv[1]
    taskspec = load_taskspec(taskspec_path)
    copy_self_artifact()

    term = get_param(taskspec, "term")
    if not isinstance(term, str) or not term.strip():
        write_agent_response("NOT_FOUND_ERROR", None, "Missing required params.term")
        return
    term = term.strip()

    start_url = taskspec.get("start_url") or ""
    if not start_url:
        write_agent_response("NOT_FOUND_ERROR", None, "Missing start_url")
        return

    username, password = extract_credentials(taskspec)
    reviews_url = reviews_url_from_start(start_url)

    log(f"task term={term}")
    log(f"start_url={start_url}")
    log(f"derived reviews_url={reviews_url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 1800})
        page = await context.new_page()
        try:
            await login_if_needed(page, start_url, username, password)
            await open_reviews_grid(page, reviews_url)
            await apply_review_detail_filter(page, term)

            declared_count = await parse_declared_result_count(page)
            visible_rows = await count_grid_rows(page)
            exact_visible_match_count = await verify_filtered_rows_on_page(page, term)

            log(f"declared filtered count: {declared_count}")
            log(f"visible rows on current page: {visible_rows}")
            log(f"visible rows containing term text: {exact_visible_match_count}")
            await extract_first_rows_for_log(page, limit=5)

            # Preferred source: Magento grid's declared total after applying detail filter.
            # Self-check: if declared count is 0, visible rows should also be 0.
            # If declared count is positive, current page should not exceed declared count.
            if declared_count is None:
                await safe_screenshot(page, "07_parse_failed")
                write_agent_response(
                    "NOT_FOUND_ERROR",
                    None,
                    "Could not parse filtered result count from reviews grid.",
                )
            else:
                if declared_count == 0 and visible_rows != 0:
                    log("warning: declared count is 0 but visible rows not 0")
                if declared_count > 0 and visible_rows > declared_count:
                    log("warning: visible rows exceed declared count")

                await safe_screenshot(page, "08_final_state")
                write_agent_response("SUCCESS", [declared_count], None)
        except Exception as e:
            log(f"fatal error: {e}")
            await safe_screenshot(page, "error_state")
            write_agent_response("NOT_FOUND_ERROR", None, str(e))
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
