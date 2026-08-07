# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --start-month ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['start_month', 'end_month']
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

import json
import os
import re
import sys
import calendar
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime, date

from playwright.sync_api import sync_playwright, Page


def workspace_dir() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", os.getcwd()))


WORKSPACE = workspace_dir()
LOG_PATH = WORKSPACE / "skill.log"
SCREENSHOT_DIR = WORKSPACE / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def write_response(status: str, retrieved_data, error_details=None) -> None:
    payload = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    (WORKSPACE / "agent_response.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_taskspec(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_month_label(s: str) -> date:
    return datetime.strptime(s.strip(), "%B %Y").date().replace(day=1)


def month_range(start_label: str, end_label: str) -> List[date]:
    start = parse_month_label(start_label)
    end = parse_month_label(end_label)
    months = []
    cur = start
    while cur <= end:
        months.append(cur)
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)
    return months


def first_day_str(d: date) -> str:
    return f"{d.month}/1/{d.year}"


def last_day_str(d: date) -> str:
    last_day = calendar.monthrange(d.year, d.month)[1]
    return f"{d.month}/{last_day}/{d.year}"


def expected_month_names(start_month: str, end_month: str) -> List[str]:
    return [d.strftime("%B") for d in month_range(start_month, end_month)]


def normalize_base_url(start_url: str) -> str:
    return start_url.rstrip("/")


def login(page: Page, start_url: str, credentials: dict) -> None:
    username = credentials.get("username") or credentials.get("user") or "admin"
    password = credentials.get("password") or "admin1234"

    page.goto(start_url, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    page.screenshot(path=str(SCREENSHOT_DIR / "01_login_page.png"))

    page.locator('input[name="username"], input[type="text"]').first.fill(username)
    page.locator('input[name="password"], input[type="password"]').first.fill(password)
    page.get_by_role("button", name=re.compile("sign in", re.I)).click()
    page.wait_for_timeout(3000)
    page.screenshot(path=str(SCREENSHOT_DIR / "02_after_login.png"))
    log("Logged in to admin interface.")


def open_sales_orders_report(page: Page, start_url: str) -> None:
    report_url = normalize_base_url(start_url) + "/reports/report_sales/sales/"
    page.goto(report_url, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    page.screenshot(path=str(SCREENSHOT_DIR / "03_report_page.png"))
    log(f"Opened report page: {report_url}")


def configure_monthly_completed_orders_report(
    page: Page,
    start_month: str,
    end_month: str,
    completed_status_value: str = "complete",
) -> None:
    months = month_range(start_month, end_month)
    from_date = first_day_str(months[0])
    to_date = last_day_str(months[-1])

    page.select_option("#sales_report_period_type", "month")
    page.select_option("#sales_report_show_order_statuses", "1")
    page.select_option("#sales_report_order_statuses", completed_status_value)
    page.fill("#sales_report_from", from_date)
    page.fill("#sales_report_to", to_date)
    page.screenshot(path=str(SCREENSHOT_DIR / "04_filters_applied.png"))
    log(f"Configured report: month period, completed status, from {from_date} to {to_date}")


def run_report(page: Page) -> None:
    page.click("#filter_form_submit")
    page.wait_for_timeout(3500)
    page.screenshot(path=str(SCREENSHOT_DIR / "05_report_results.png"))
    log("Ran report.")


def extract_report_rows(page: Page) -> List[List[str]]:
    return page.locator("table.data-grid tbody tr").evaluate_all(
        """trs => trs.map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()))"""
    )


def parse_month_cell(cell: str) -> Optional[Tuple[int, int]]:
    m = re.match(r"^\s*(\d{1,2})/(\d{4})\s*$", cell)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def extract_monthly_counts_from_rows(rows: List[List[str]]) -> List[Dict]:
    data = []
    for r in rows:
        if len(r) < 2:
            continue
        parsed = parse_month_cell(r[0])
        if not parsed:
            continue
        month_num, year = parsed
        month_name = datetime(year, month_num, 1).strftime("%B")
        count_text = re.sub(r"[^\d-]", "", r[1])
        if count_text == "":
            continue
        data.append({"month": month_name, "count": int(count_text), "_year": year, "_month_num": month_num})
    data.sort(key=lambda x: (x["_year"], x["_month_num"]))
    return data


def extract_declared_total_records(page: Page) -> Optional[int]:
    text = page.locator("body").inner_text()
    m = re.search(r"(\d+)\s+records\s+found", text, re.I)
    return int(m.group(1)) if m else None


def verify_against_expected_months(data: List[Dict], start_month: str, end_month: str, declared_total: Optional[int]) -> List[Dict]:
    expected = expected_month_names(start_month, end_month)
    filtered = [d for d in data if d["month"] in expected]

    if declared_total is not None and declared_total != len(filtered):
        raise RuntimeError(f"Declared total {declared_total} does not match extracted month rows {len(filtered)}")

    names = [d["month"] for d in filtered]
    if names != expected:
        raise RuntimeError(f"Expected months {expected}, got {names}")

    return [{"month": d["month"], "count": d["count"]} for d in filtered]


def retrieve_monthly_completed_orders(taskspec: dict) -> List[Dict]:
    params = taskspec.get("params", {})
    start_month = params["start_month"]
    end_month = params["end_month"]
    start_url = taskspec["start_url"]
    credentials = taskspec.get("credentials", {})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 1800}, accept_downloads=True)
        page = context.new_page()
        try:
            login(page, start_url, credentials)
            open_sales_orders_report(page, start_url)
            configure_monthly_completed_orders_report(page, start_month, end_month)
            run_report(page)
            rows = extract_report_rows(page)
            log(f"Raw rows: {json.dumps(rows)}")
            parsed = extract_monthly_counts_from_rows(rows)
            declared_total = extract_declared_total_records(page)
            result = verify_against_expected_months(parsed, start_month, end_month, declared_total)
            log(f"Final extracted data: {json.dumps(result)}")
            return result
        finally:
            browser.close()


def main():
    try:
        taskspec = load_taskspec(sys.argv[1])
        retrieved_data = retrieve_monthly_completed_orders(taskspec)
        write_response("SUCCESS" if retrieved_data is not None else "NOT_FOUND_ERROR", retrieved_data, None)
    except Exception as e:
        log(f"ERROR: {type(e).__name__}: {e}")
        write_response("ERROR", None, f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
