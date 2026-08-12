# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --keyword ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['keyword', 'retrieved_data_format_spec']
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
import shutil
from pathlib import Path
from urllib.parse import urlparse, quote_plus

from playwright.async_api import async_playwright


def get_workspace() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", os.getcwd())).resolve()


WORKSPACE = get_workspace()
RUN_DIR = WORKSPACE / "final_runs" / "run_1"
SCREENSHOTS_DIR = RUN_DIR / "screenshots"
LOG_PATH = RUN_DIR / "final_script_log.txt"
AGENT_RESPONSE_PATH = WORKSPACE / "agent_response.json"


def ensure_dirs() -> None:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(message + "\n")
    print(message)


def write_response(status: str, retrieved_data, error_details=None) -> None:
    payload = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    AGENT_RESPONSE_PATH.write_text(json.dumps(payload), encoding="utf-8")
    log("final response: " + json.dumps(payload))


def copy_self_artifact() -> None:
    try:
        src = Path(__file__)
        if src.exists():
            shutil.copy2(src, RUN_DIR / "final_script.py")
    except Exception as e:
        log(f"note: unable to copy script artifact: {e!r}")


def normalize_base_url(taskspec: dict) -> str:
    start_url = taskspec.get("start_url") or ""
    if not start_url:
        raise RuntimeError("Missing taskspec.start_url")
    parsed = urlparse(start_url)
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError("Could not determine base URL from taskspec.start_url")
    return f"{parsed.scheme}://{parsed.netloc}"


def get_credentials(taskspec: dict) -> tuple[str, str]:
    creds = taskspec.get("credentials") or {}
    username = creds.get("username") or creds.get("login") or creds.get("user") or creds.get("email")
    password = creds.get("password")
    if not username or not password:
        raise RuntimeError("Missing username/password in taskspec.credentials")
    return username, password


async def save_screenshot(page, name: str) -> None:
    try:
        await page.screenshot(path=str(SCREENSHOTS_DIR / name), full_page=True)
    except Exception as e:
        log(f"note: screenshot failed for {name}: {e!r}")


async def login(page, base_url: str, username: str, password: str) -> None:
    sign_in_url = base_url.rstrip("/") + "/users/sign_in"
    await page.goto(sign_in_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(800)

    if await page.locator('input[name="user[login]"], input[type="text"], input[type="email"]').count() == 0:
        log("login page did not show expected input fields immediately; continuing")
    await page.locator('input[name="user[login]"], input[type="text"], input[type="email"]').first.fill(username)
    await page.locator('input[name="user[password]"], input[type="password"]').first.fill(password)
    await page.get_by_role("button", name=re.compile(r"sign in", re.I)).click()
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(1500)

    current = page.url.lower()
    body_text = (await page.locator("body").inner_text()).lower()
    if "/users/sign_in" in current and "sign in" in body_text:
        raise RuntimeError("Login failed")

    log(f"authenticated successfully as {username}")
    await save_screenshot(page, "final_execution_1_login.png")


def title_matches_keyword(title: str, keyword: str) -> bool:
    return keyword.lower() in (title or "").lower()


async def open_search_results(page, base_url: str, keyword: str) -> None:
    search_url = (
        base_url.rstrip("/")
        + "/search?search="
        + quote_plus(keyword)
        + "&group_id=&project_id=&scope=issues"
    )
    await page.goto(search_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(1800)
    await save_screenshot(page, "final_execution_2_search_results.png")
    log(f"opened issue search for keyword {keyword!r}: {search_url}")


async def try_sort_by_updated(page) -> bool:
    candidates = [
        ("button", re.compile(r"created date", re.I)),
        ("button", re.compile(r"updated date", re.I)),
    ]
    try:
        created = page.get_by_role(candidates[0][0], name=candidates[0][1]).first
        await created.click(timeout=2500)
        updated = page.get_by_role(candidates[1][0], name=candidates[1][1]).first
        await updated.click(timeout=2500)
        await page.wait_for_load_state("networkidle", timeout=5000)
        await page.wait_for_timeout(1200)
        log("applied updated-date sort using search UI controls")
        return True
    except Exception as e:
        log(f"note: could not switch search sort to updated date via UI: {e!r}")
        return False


async def extract_issue_links_from_page(page) -> list[dict]:
    js = r"""
    () => {
      const out = [];
      const seen = new Set();

      function nearestText(el) {
        let node = el.closest('li, .issue, .issuable-info, .search-result-row, .search-result, tr, .panel, .card') || el.parentElement || el;
        let txt = (node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim();
        return txt;
      }

      for (const a of Array.from(document.querySelectorAll('a[href*="/issues/"], a[href*="/-/issues/"]'))) {
        const href = a.href || '';
        if (!href || href.includes('#') || href.endsWith('/issues') || href.endsWith('/-/issues')) continue;
        if (seen.has(href)) continue;
        seen.add(href);

        const text = (a.innerText || a.textContent || '').replace(/\s+/g, ' ').trim();
        const context = nearestText(a);
        out.push({href, text, context});
      }
      return out;
    }
    """
    items = await page.evaluate(js)
    cleaned = []
    for item in items or []:
        href = (item.get("href") or "").strip()
        text = re.sub(r"\s+", " ", (item.get("text") or "")).strip()
        context = re.sub(r"\s+", " ", (item.get("context") or "")).strip()
        if not href:
            continue
        cleaned.append({"href": href, "text": text, "context": context})
    return cleaned


def rank_issue_candidates(candidates: list[dict], keyword: str) -> list[dict]:
    ranked = []
    for item in candidates:
        title = item.get("text") or item.get("context") or ""
        title_l = title.lower()
        kw_l = keyword.lower()

        if not title_matches_keyword(title, keyword):
            continue

        score = 0
        if kw_l in (item.get("text") or "").lower():
            score += 3
        if "/-/issues/" in item.get("href", ""):
            score += 2
        if "/issues/" in item.get("href", ""):
            score += 1
        if len(title) < 220:
            score += 1

        ranked.append(
            {
                "href": item["href"],
                "title": title,
                "context": item.get("context", ""),
                "score": score,
            }
        )
    ranked.sort(key=lambda x: (-x["score"], x["title"]))
    return ranked


async def get_issue_detail_status(page, issue_url: str, keyword: str) -> tuple[bool | None, dict]:
    await page.goto(issue_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(1800)
    body = await page.locator("body").inner_text()
    title = await page.title()

    body_norm = "\n" + body + "\n"
    is_closed = ("\nClosed\n" in body_norm) or ("Reopen issue" in body)
    is_open = ("\nOpen\n" in body_norm) or ("Close issue" in body)

    keyword_found = keyword.lower() in (body + "\n" + title).lower()
    evidence = {
        "issue_url": issue_url,
        "page_title": title,
        "keyword_found_on_page": keyword_found,
        "detected_closed": is_closed,
        "detected_open": is_open,
        "body_excerpt": body[:2500],
    }

    await save_screenshot(page, "final_execution_4_issue_detail.png")

    if is_closed and not is_open:
        return True, evidence
    if is_open and not is_closed:
        return False, evidence
    if is_closed:
        return True, evidence
    if is_open:
        return False, evidence
    return None, evidence


async def find_latest_matching_issue_closed_state(page, base_url: str, keyword: str) -> bool:
    await open_search_results(page, base_url, keyword)
    sort_applied = await try_sort_by_updated(page)
    if sort_applied:
        await save_screenshot(page, "final_execution_3_search_sorted_updated.png")

    candidates_raw = await extract_issue_links_from_page(page)
    ranked = rank_issue_candidates(candidates_raw, keyword)
    log("candidate issue links: " + json.dumps(ranked[:20], ensure_ascii=False))

    if not ranked:
        body = await page.locator("body").inner_text()
        log("search page body excerpt: " + body[:3000].replace("\n", " | "))
        raise FileNotFoundError(f"No issue title containing keyword {keyword!r} found")

    latest = ranked[0]
    log("selected latest matching issue candidate from visible search order: " + json.dumps(latest, ensure_ascii=False))
    status, evidence = await get_issue_detail_status(page, latest["href"], keyword)
    log("issue detail evidence: " + json.dumps(evidence, ensure_ascii=False))

    if status is None:
        raise RuntimeError("Could not determine whether selected issue is open or closed from detail page")

    return status


def validate_output_schema(taskspec: dict) -> None:
    expected = {"type": "array", "items": {"type": "boolean"}}
    schema = taskspec.get("output_schema")
    if schema != expected:
        log(f"note: output_schema differs from expected boolean-array schema: {json.dumps(schema)}")


async def run_task(taskspec: dict) -> list[bool]:
    params = taskspec.get("params") or {}
    keyword = params.get("keyword")
    if not keyword:
        raise RuntimeError("Missing params.keyword")

    base_url = normalize_base_url(taskspec)
    username, password = get_credentials(taskspec)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 1800})
        page = await context.new_page()
        try:
            await login(page, base_url, username, password)
            closed = await find_latest_matching_issue_closed_state(page, base_url, keyword)
            return [closed]
        finally:
            await browser.close()


def main() -> None:
    ensure_dirs()
    LOG_PATH.write_text("", encoding="utf-8")
    copy_self_artifact()

    try:
        taskspec_path = sys.argv[1]
    except IndexError:
        write_response("ERROR", None, "Missing taskspec.json path argument")
        return

    try:
        with open(taskspec_path, "r", encoding="utf-8") as f:
            taskspec = json.load(f)
        validate_output_schema(taskspec)
        retrieved_data = asyncio.run(run_task(taskspec))
        write_response("SUCCESS", retrieved_data, None)
    except FileNotFoundError as e:
        write_response("NOT_FOUND_ERROR", None, str(e))
    except Exception as e:
        write_response("ERROR", None, f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
