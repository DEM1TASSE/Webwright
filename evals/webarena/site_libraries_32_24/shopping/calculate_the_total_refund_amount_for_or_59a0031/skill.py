# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --month-year ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['month_year']
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
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from playwright.async_api import async_playwright, Page


def get_workspace_dir() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", os.getcwd())).resolve()


WORKSPACE = get_workspace_dir()
WORKSPACE.mkdir(parents=True, exist_ok=True)
LOG_FILE = WORKSPACE / "skill_log.txt"
SCREENSHOT_DIR = WORKSPACE / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
RESPONSE_FILE = WORKSPACE / "agent_response.json"

_step_counter = 0


def log(message: str) -> None:
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(message + "\n")
    print(message)


async def snap(page: Page, label: str) -> None:
    global _step_counter
    _step_counter += 1
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", label).strip("_") or "step"
    path = SCREENSHOT_DIR / f"{_step_counter:03d}_{safe}.png"
    await page.screenshot(path=str(path), full_page=True)
    log(f"screenshot: {path.name}")


def read_taskspec(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_response(retrieved_data, status: str = "SUCCESS", error_details: Optional[str] = None) -> None:
    response = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    RESPONSE_FILE.write_text(json.dumps(response), encoding="utf-8")


def parse_month_year(month_year: str) -> Tuple[int, int]:
    dt = datetime.strptime(month_year.strip(), "%b %Y")
    return dt.month, dt.year


def extract_currency(text: str) -> Optional[float]:
    m = re.search(r"\$([\d,]+\.\d{2})", text)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def normalize_order_date(date_text: str) -> Optional[datetime]:
    date_text = date_text.strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(date_text, fmt)
        except ValueError:
            continue
    return None


async def login(page: Page, start_url: str, credentials: dict) -> None:
    await page.goto(start_url.rstrip("/") + "/customer/account/login/", wait_until="domcontentloaded")
    await page.locator('input[name="login[username]"]').fill(credentials["username"])
    await page.locator('input[name="login[password]"]').fill(credentials["password"])
    await page.get_by_role("button", name=re.compile("sign in", re.I)).click()
    await page.wait_for_load_state("domcontentloaded")
    await snap(page, "after_login")


async def open_my_orders(page: Page, start_url: str) -> None:
    try:
        await page.get_by_role("link", name=re.compile(r"my orders", re.I)).click()
        await page.wait_for_load_state("domcontentloaded")
    except Exception:
        await page.goto(start_url.rstrip("/") + "/sales/order/history/", wait_until="domcontentloaded")
    await snap(page, "my_orders_page")


async def extract_order_rows_on_current_page(page: Page) -> List[dict]:
    rows_data = []
    rows = page.locator("table tbody tr")
    count = await rows.count()
    for i in range(count):
        row = rows.nth(i)
        text = " ".join((await row.inner_text()).split())
        href = None
        try:
            href = await row.get_by_role("link", name=re.compile(r"view order", re.I)).get_attribute("href")
        except Exception:
            pass

        order_no = None
        m = re.search(r"\b0+\d+\b", text)
        if m:
            order_no = m.group(0)

        status = None
        for candidate in ["Canceled", "Complete", "Pending", "Processing", "Closed", "On Hold"]:
            if re.search(rf"\b{re.escape(candidate)}\b", text, re.I):
                status = candidate
                break

        date_value = None
        date_match = re.search(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", text)
        if date_match:
            date_value = normalize_order_date(date_match.group(0))

        rows_data.append(
            {
                "text": text,
                "href": href,
                "order_no": order_no,
                "status": status,
                "date": date_value,
            }
        )
    return rows_data


async def paginate_all_order_rows(page: Page) -> List[dict]:
    seen_signatures = set()
    all_rows: List[dict] = []

    while True:
        current_rows = await extract_order_rows_on_current_page(page)
        page_sig = tuple((r.get("order_no"), r.get("text")) for r in current_rows)
        if page_sig in seen_signatures:
            break
        seen_signatures.add(page_sig)
        all_rows.extend(current_rows)

        next_button = page.get_by_role("link", name=re.compile(r"next", re.I))
        if await next_button.count() == 0:
            break
        try:
            cls = await next_button.first.get_attribute("class") or ""
            aria_disabled = await next_button.first.get_attribute("aria-disabled")
            if "disabled" in cls.lower() or aria_disabled == "true":
                break
            await next_button.first.click()
            await page.wait_for_load_state("domcontentloaded")
        except Exception:
            break

    log(f"extracted_order_rows: {len(all_rows)}")
    return all_rows


def filter_canceled_orders_for_month(rows: List[dict], month_year: str) -> List[dict]:
    month, year = parse_month_year(month_year)
    filtered = []
    for row in rows:
        if (row.get("status") or "").lower() != "canceled":
            continue
        dt = row.get("date")
        if not dt:
            continue
        if dt.month == month and dt.year == year:
            filtered.append(row)
    log(f"matching_canceled_orders_in_month: {len(filtered)}")
    return filtered


async def open_order_detail(page: Page, start_url: str, href: str) -> None:
    url = href if href.startswith("http") else start_url.rstrip("/") + href
    await page.goto(url, wait_until="domcontentloaded")


async def extract_order_refund_total(page: Page) -> float:
    body = await page.locator("body").inner_text()

    if not re.search(r"\bCanceled\b", body, re.I):
        raise ValueError("Order detail page is not canceled")

    grand_total_match = re.search(r"Grand Total\s*\$([\d,]+\.\d{2})", body, re.I)
    if not grand_total_match:
        grand_total_match = re.search(r"Grand Total[^\$]*\$([\d,]+\.\d{2})", body, re.I | re.S)
    if not grand_total_match:
        raise ValueError("Grand Total not found on order detail page")

    total = float(grand_total_match.group(1).replace(",", ""))

    if "Shipping & Handling" not in body:
        log("warning: Shipping & Handling text not found explicitly; using grand total as refund including shipping")

    return total


async def collect_monthly_canceled_refund_total(page: Page, start_url: str, month_year: str) -> float:
    await open_my_orders(page, start_url)
    rows = await paginate_all_order_rows(page)
    target_rows = filter_canceled_orders_for_month(rows, month_year)

    refunds: List[float] = []
    for idx, row in enumerate(target_rows, start=1):
        href = row.get("href")
        if not href:
            log(f"skipping_row_without_href: {row.get('text')}")
            continue
        await open_order_detail(page, start_url, href)
        refund = await extract_order_refund_total(page)
        refunds.append(refund)
        log(f"order_refund_{idx}: order_no={row.get('order_no')} refund={refund:.2f}")
        await snap(page, f"order_{row.get('order_no') or idx}_detail")

    total_refund = round(sum(refunds), 2)
    log(f"total_refund_for_{month_year}: {total_refund:.2f}")
    return total_refund


def validate_output_schema(output_schema: dict, data) -> None:
    if output_schema != {"type": "array", "items": {"type": "number"}}:
        raise ValueError("Unsupported output_schema for this skill")
    if not isinstance(data, list) or any(not isinstance(x, (int, float)) for x in data):
        raise ValueError("retrieved_data does not match required output_schema")


async def run() -> None:
    LOG_FILE.write_text("", encoding="utf-8")
    taskspec_path = sys.argv[1]
    taskspec = read_taskspec(taskspec_path)

    params = taskspec.get("params", {})
    start_url = taskspec.get("start_url", "").rstrip("/")
    credentials = taskspec.get("credentials", {})
    output_schema = taskspec.get("output_schema")

    month_year = params["month_year"]
    username = credentials.get("username") or credentials.get("email")
    password = credentials.get("password")

    if not start_url:
        raise ValueError("start_url is required")
    if not username or not password:
        raise ValueError("credentials.username/email and credentials.password are required")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 1800})
        page = await context.new_page()
        try:
            await login(page, start_url, {"username": username, "password": password})
            total_refund = await collect_monthly_canceled_refund_total(page, start_url, month_year)
            retrieved_data = [total_refund]
            validate_output_schema(output_schema, retrieved_data)
            write_response(retrieved_data, "SUCCESS", None)
            await snap(page, "final")
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except Exception as e:
        log(f"ERROR: {e}")
        write_response([], "FAILURE", str(e))
