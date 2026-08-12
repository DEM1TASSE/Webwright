# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --status ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['status', 'retrieved_data_format_spec']
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
import html
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.async_api import async_playwright, Page


WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", ".")).resolve()
RUNS_DIR = WORKSPACE / "final_runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)
AGENT_RESPONSE_PATH = WORKSPACE / "agent_response.json"


def next_run_dir() -> Path:
    existing = []
    for p in RUNS_DIR.glob("run_*"):
        try:
            existing.append(int(p.name.split("_")[1]))
        except Exception:
            pass
    run_id = max(existing, default=0) + 1
    run_dir = RUNS_DIR / f"run_{run_id:03d}"
    (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)
    return run_dir


RUN_DIR = next_run_dir()
SCREENSHOTS_DIR = RUN_DIR / "screenshots"
LOG_PATH = RUN_DIR / "final_script_log.txt"
LOG_PATH.write_text("", encoding="utf-8")


def log(msg: str) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)


def strip_text(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def money_to_float(s: str) -> float:
    m = re.search(r"-?\$?\s*([0-9][0-9,]*\.\d{2})", s or "")
    if not m:
        raise ValueError(f"Could not parse money from: {s!r}")
    return float(m.group(1).replace(",", ""))


def normalize_status(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def parse_status_condition(raw: str) -> Tuple[str, str]:
    s = (raw or "").strip()
    sl = s.lower()

    m = re.search(r'marked as\s+"([^"]+)"', sl)
    if m:
        return ("equals", normalize_status(m.group(1)))

    m = re.search(r"marked as\s+'([^']+)'", sl)
    if m:
        return ("equals", normalize_status(m.group(1)))

    m = re.search(r"that is not\s+(.+)$", sl)
    if m:
        return ("not_equals", normalize_status(m.group(1).strip(" .")))

    m = re.search(r"not\s+(.+)$", sl)
    if m:
        return ("not_equals", normalize_status(m.group(1).strip(" .")))

    if s:
        return ("equals", normalize_status(s))

    raise ValueError("Missing or unparseable status condition")


def matches_status(order_status: str, condition: Tuple[str, str]) -> bool:
    kind, value = condition
    st = normalize_status(order_status)
    if kind == "equals":
        return st == value
    if kind == "not_equals":
        return st != value
    raise ValueError(f"Unknown condition kind: {kind}")


def load_taskspec() -> Dict[str, Any]:
    import sys
    if len(sys.argv) < 2:
        raise RuntimeError("Expected taskspec.json path as argv[1]")
    return json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))


def get_base_url(taskspec: Dict[str, Any]) -> str:
    base = (taskspec.get("start_url") or "").rstrip("/")
    if not base:
        raise RuntimeError("Missing taskspec.start_url")
    return base


def get_credentials(taskspec: Dict[str, Any]) -> Tuple[str, str]:
    creds = taskspec.get("credentials") or {}

    username = (
        creds.get("username")
        or creds.get("email")
        or creds.get("login")
        or creds.get("user")
        or os.environ.get("USERNAME")
        or os.environ.get("EMAIL")
        or os.environ.get("LOGIN_EMAIL")
        or ""
    )
    password = (
        creds.get("password")
        or creds.get("pass")
        or creds.get("pw")
        or os.environ.get("PASSWORD")
        or os.environ.get("PASS")
        or os.environ.get("LOGIN_PASSWORD")
        or ""
    )

    # Known default for this site template if taskspec omits credentials.
    if not username:
        username = "emma.lopez@gmail.com"
    if not password:
        password = "Password.123"

    return username, password


def write_response(status: str, retrieved_data: Optional[List[float]], error_details: Optional[str]) -> None:
    AGENT_RESPONSE_PATH.write_text(
        json.dumps(
            {
                "task_type": "RETRIEVE",
                "status": status,
                "retrieved_data": retrieved_data,
                "error_details": error_details,
            }
        ),
        encoding="utf-8",
    )


async def snap(page: Page, step: int, name: str) -> None:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_") or "step"
    path = SCREENSHOTS_DIR / f"final_execution_{step}_{safe}.png"
    await page.screenshot(path=str(path), full_page=True)


async def login(page: Page, base_url: str, username: str, password: str) -> None:
    await page.goto(f"{base_url}/customer/account/login/", wait_until="domcontentloaded")
    await page.locator("input[name='login[username]']").fill(username)
    await page.locator("input[name='login[password]']").fill(password)
    await page.locator("button.action.login.primary, button:has-text('Sign In')").first.click()
    await page.wait_for_load_state("networkidle")
    body = (await page.locator("body").inner_text()).lower()
    if "/customer/account/login" in page.url and ("incorrect" in body or "invalid" in body):
        raise RuntimeError("Login failed")
    log(f"Logged in as {username}; current URL: {page.url}")


async def open_order_history(page: Page, base_url: str) -> None:
    await page.goto(f"{base_url}/sales/order/history/", wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")


async def extract_order_rows_from_current_page(page: Page) -> List[Dict[str, Any]]:
    rows = page.locator("table tbody tr")
    count = await rows.count()
    results: List[Dict[str, Any]] = []

    for i in range(count):
        row = rows.nth(i)
        cells = row.locator("td")
        cell_count = await cells.count()
        texts = [strip_text(await cells.nth(j).inner_text()) for j in range(cell_count)]
        if len(texts) < 5:
            continue

        if len(texts) >= 6:
            order_number = texts[0]
            date_text = texts[1]
            total_text = texts[3]
            status_text = texts[4]
        else:
            order_number = texts[0]
            date_text = texts[1]
            total_text = texts[2]
            status_text = texts[3]

        href = None
        link = row.get_by_role("link", name=re.compile(r"view order", re.I))
        if await link.count():
            href = await link.first.get_attribute("href")

        order_id = None
        if href:
            m = re.search(r"/order_id/(\d+)/", href)
            if m:
                order_id = int(m.group(1))

        results.append(
            {
                "order_number": order_number,
                "date_text": date_text,
                "total_text": total_text,
                "status_text": status_text,
                "href": href,
                "order_id": order_id,
                "raw_cells": texts,
            }
        )
    return results


async def collect_all_orders(page: Page, base_url: str) -> List[Dict[str, Any]]:
    await open_order_history(page, base_url)
    all_orders: List[Dict[str, Any]] = []
    seen = set()
    page_num = 1

    while True:
        current = await extract_order_rows_from_current_page(page)
        for row in current:
            key = (row["order_number"], row["date_text"], row["status_text"], row["total_text"])
            if key not in seen:
                seen.add(key)
                all_orders.append(row)

        log(f"Parsed order history page {page_num}: {len(current)} rows, cumulative {len(all_orders)}")

        next_link = page.get_by_role("link", name=re.compile(r"next", re.I))
        if not await next_link.count():
            break

        disabled = False
        try:
            cls = await next_link.first.get_attribute("class")
            aria = await next_link.first.get_attribute("aria-disabled")
            disabled = (cls and "disabled" in cls.lower()) or aria == "true"
        except Exception:
            disabled = False
        if disabled:
            break

        prev_url = page.url
        await next_link.first.click()
        await page.wait_for_load_state("networkidle")
        if page.url == prev_url:
            break
        page_num += 1

    if not all_orders:
        raise RuntimeError("No orders found in order history")
    return all_orders


def choose_latest_matching_order(orders: List[Dict[str, Any]], condition: Tuple[str, str]) -> Optional[Dict[str, Any]]:
    matching = [o for o in orders if matches_status(o["status_text"], condition)]
    log(f"Matching orders count: {len(matching)} for condition={condition}")
    return matching[0] if matching else None


async def open_order_detail(page: Page, base_url: str, order: Dict[str, Any]) -> None:
    href = order.get("href")
    if href:
        if href.startswith("/"):
            href = base_url + href
        await page.goto(href, wait_until="domcontentloaded")
    elif order.get("order_id") is not None:
        await page.goto(f"{base_url}/sales/order/view/order_id/{order['order_id']}/", wait_until="domcontentloaded")
    else:
        raise RuntimeError("No order detail link found")
    await page.wait_for_load_state("networkidle")


async def extract_order_total_from_detail(page: Page) -> Optional[float]:
    body = strip_text(await page.locator("body").inner_text())
    for pat in [
        r"Grand Total\s*\$([0-9,]+\.\d{2})",
        r"Order Total\s*\$([0-9,]+\.\d{2})",
        r"Total\s*\$([0-9,]+\.\d{2})",
    ]:
        m = re.search(pat, body, re.I)
        if m:
            return float(m.group(1).replace(",", ""))
    return None


async def retrieve_latest_order_total_by_status(
    page: Page,
    base_url: str,
    status_text_spec: str,
) -> List[float]:
    condition = parse_status_condition(status_text_spec)
    orders = await collect_all_orders(page, base_url)
    chosen = choose_latest_matching_order(orders, condition)
    if not chosen:
        raise LookupError("No matching order found")

    log(
        f"Selected latest matching order: "
        f"order_number={chosen['order_number']} date={chosen['date_text']} "
        f"status={chosen['status_text']} list_total={chosen['total_text']}"
    )

    await open_order_detail(page, base_url, chosen)
    detail_total = await extract_order_total_from_detail(page)

    list_total = None
    try:
        list_total = money_to_float(chosen["total_text"])
    except Exception:
        pass

    if detail_total is not None:
        final_total = detail_total
        if list_total is not None and abs(detail_total - list_total) > 0.01:
            log(f"Warning: detail total {detail_total:.2f} differs from list total {list_total:.2f}; using detail total")
    elif list_total is not None:
        final_total = list_total
        log("Detail total not found; using order-history total")
    else:
        raise RuntimeError("Could not determine order total")

    return [final_total]


async def run() -> None:
    taskspec = load_taskspec()
    params = taskspec.get("params") or {}
    base_url = get_base_url(taskspec)
    username, password = get_credentials(taskspec)

    status_spec = params.get("status", "")
    if not status_spec:
        raise RuntimeError("Missing params.status")

    step = 1
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 1800})
        page = await context.new_page()

        try:
            await login(page, base_url, username, password)
            await snap(page, step, "logged_in")
            step += 1

            await open_order_history(page, base_url)
            await snap(page, step, "order_history")
            step += 1

            retrieved_data = await retrieve_latest_order_total_by_status(page, base_url, status_spec)
            await snap(page, step, "selected_order_detail")
            write_response("SUCCESS", retrieved_data, None)
            log(f"Final retrieved_data: {retrieved_data}")

        except LookupError:
            write_response("NOT_FOUND_ERROR", None, None)
            log("No matching order found")
        except Exception as e:
            write_response("ERROR", None, f"{type(e).__name__}: {e}")
            log(f"ERROR: {type(e).__name__}: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
