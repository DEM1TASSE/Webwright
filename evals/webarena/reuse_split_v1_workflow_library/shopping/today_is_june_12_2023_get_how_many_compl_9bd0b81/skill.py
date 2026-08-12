# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --period ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['period', 'retrieved_data_format_spec']
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
import html
import subprocess
from decimal import Decimal, InvalidOperation
from datetime import datetime, date, timedelta
from pathlib import Path
from urllib.parse import urljoin


TODAY = date(2023, 6, 12)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_workspace() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", ".")).resolve()


def next_run_dir(workspace: Path) -> Path:
    root = ensure_dir(workspace / "final_runs")
    ids = []
    for p in root.glob("run_*"):
        try:
            ids.append(int(p.name.split("_", 1)[1]))
        except Exception:
            pass
    run_id = max(ids, default=0) + 1
    run_dir = root / f"run_{run_id}"
    ensure_dir(run_dir / "screenshots")
    return run_dir


class Logger:
    def __init__(self, path: Path):
        self.path = path
        self.path.write_text("", encoding="utf-8")

    def log(self, msg: str):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
        print(msg)


def write_text(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


def strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_money(text: str) -> Decimal:
    if text is None:
        raise ValueError("Missing money text")
    m = re.search(r"-?\$?\s*([0-9][0-9,]*\.\d{2})", text)
    if not m:
        raise ValueError(f"Could not parse money from: {text!r}")
    try:
        return Decimal(m.group(1).replace(",", ""))
    except InvalidOperation as e:
        raise ValueError(f"Invalid money value: {text!r}") from e


def parse_mmddyy(text: str):
    try:
        return datetime.strptime(text.strip(), "%m/%d/%y").date()
    except Exception:
        return None


def subtract_months(d: date, months: int) -> date:
    y = d.year
    m = d.month - months
    while m <= 0:
        y -= 1
        m += 12
    day = d.day
    while day >= 28:
        try:
            return date(y, m, day)
        except ValueError:
            day -= 1
    return date(y, m, day)


def parse_period(period_text: str, today: date) -> tuple[date, date]:
    p = (period_text or "").strip().lower()

    if p == "over the past year":
        return date(today.year - 1, today.month, today.day), today

    m = re.fullmatch(r"over the past (\d+) days?", p)
    if m:
        n = int(m.group(1))
        return today - timedelta(days=n - 1), today

    m = re.fullmatch(r"over the past (\d+) months?", p)
    if m:
        n = int(m.group(1))
        return subtract_months(today, n), today

    raise ValueError(f"Unsupported period format: {period_text}")


class CurlSession:
    def __init__(self, cookie_path: Path, logger: Logger):
        self.cookie_path = cookie_path
        self.logger = logger
        self.user_agent = "Mozilla/5.0"

    def request(self, url: str, method: str = "GET", data: list[tuple[str, str]] | None = None, referer: str | None = None) -> str:
        cmd = [
            "curl",
            "-sS",
            "-L",
            "-A",
            self.user_agent,
            "-c",
            str(self.cookie_path),
            "-b",
            str(self.cookie_path),
        ]
        if referer:
            cmd += ["-e", referer]
        if method.upper() == "POST":
            cmd += ["-X", "POST"]
            for k, v in (data or []):
                cmd += ["--data-urlencode", f"{k}={v}"]
        cmd += [url]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"curl failed for {url}: {res.stderr.strip()}")
        return res.stdout


def extract_login_form(login_html: str, base_url: str) -> tuple[str, list[tuple[str, str]]]:
    m = re.search(r"<form\b([^>]*)id=[\"']login-form[\"']([^>]*)>(.*?)</form>", login_html, re.I | re.S)
    if m:
        attrs = (m.group(1) or "") + " " + (m.group(2) or "")
        body = m.group(3) or ""
    else:
        m2 = re.search(r"<form\b([^>]*)>(.*?)</form>", login_html, re.I | re.S)
        if not m2:
            raise RuntimeError("Could not find login form")
        attrs = m2.group(1) or ""
        body = m2.group(2) or ""

    action_m = re.search(r'action=["\']([^"\']+)', attrs, re.I)
    action = urljoin(base_url, action_m.group(1)) if action_m else urljoin(base_url, "/customer/account/loginPost/")

    fields = []
    for im in re.finditer(r"<input\b([^>]*)>", body, re.I | re.S):
        attrs = im.group(1)
        name_m = re.search(r'name=["\']([^"\']+)["\']', attrs, re.I)
        if not name_m:
            continue
        val_m = re.search(r'value=["\']([^"\']*)["\']', attrs, re.I)
        typ_m = re.search(r'type=["\']([^"\']+)["\']', attrs, re.I)
        name = html.unescape(name_m.group(1))
        value = html.unescape(val_m.group(1)) if val_m else ""
        typ = typ_m.group(1).lower() if typ_m else "text"
        if typ in {"hidden", "text", "email", "password", "submit"}:
            fields.append((name, value))
    return action, fields


def login(session: CurlSession, base_url: str, credentials: dict, run_dir: Path, logger: Logger):
    login_url = urljoin(base_url, "/customer/account/login/")
    login_html = session.request(login_url)
    write_text(run_dir / "screenshots" / "login_page.txt", login_html[:20000])

    username = credentials.get("username") or credentials.get("email") or credentials.get("login")
    password = credentials.get("password")
    if not username or not password:
        raise ValueError("Missing credentials.username/email and/or credentials.password")

    action, fields = extract_login_form(login_html, base_url)
    payload = [(k, v) for (k, v) in fields if k not in {"login[username]", "login[password]"}]
    payload.append(("login[username]", username))
    payload.append(("login[password]", password))
    if not any(k == "send" for k, _ in payload):
        payload.append(("send", "Sign In"))

    post_html = session.request(action, method="POST", data=payload, referer=login_url)
    write_text(run_dir / "screenshots" / "post_login.txt", post_html[:20000])

    acct_html = session.request(urljoin(base_url, "/customer/account/"))
    write_text(run_dir / "screenshots" / "account_page.txt", acct_html[:20000])

    ok = any(marker in acct_html.lower() for marker in ["my account", "my orders", "sign out", "logout"])
    logger.log(f"login_markers_found={ok}")
    if not ok:
        raise RuntimeError("Login failed or account page not accessible")


def extract_history_rows(page_html: str, base_url: str) -> list[dict]:
    table_m = re.search(r"<table[^>]*id=[\"']my-orders-table[\"'][\s\S]*?</table>", page_html, re.I)
    block = table_m.group(0) if table_m else page_html
    rows = []
    for tr in re.finditer(r"<tr[^>]*>(.*?)</tr>", block, re.I | re.S):
        row_html = tr.group(1)
        cells = [strip_tags(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.I | re.S)]
        if len(cells) < 4:
            continue
        if cells[0].strip().lower() in {"order #", "order"}:
            continue
        if "view order" not in row_html.lower() and "/sales/order/view/" not in row_html.lower():
            continue
        href_m = re.search(r'href=["\']([^"\']*?/sales/order/view/order_id/\d+/?)["\']', row_html, re.I)
        view_url = urljoin(base_url, html.unescape(href_m.group(1))) if href_m else None
        rows.append(
            {
                "order_no": cells[0].strip(),
                "date_text": cells[1].strip(),
                "date": parse_mmddyy(cells[1]),
                "total_text": cells[2].strip(),
                "status": cells[3].strip(),
                "view_url": view_url,
            }
        )
    return rows


def declared_last_page(page_html: str) -> int | None:
    nums = [int(x) for x in re.findall(r"[?&]p=(\d+)", page_html)]
    return max(nums) if nums else None


def fetch_all_order_history(session: CurlSession, base_url: str, run_dir: Path, logger: Logger) -> list[dict]:
    all_rows = []
    seen_orders = set()
    seen_page_urls = set()
    page_num = 1
    total_pages_hint = None

    while True:
        rel = "/sales/order/history/" if page_num == 1 else f"/sales/order/history/?p={page_num}"
        url = urljoin(base_url, rel)
        if url in seen_page_urls:
            break
        seen_page_urls.add(url)

        page_html = session.request(url)
        write_text(run_dir / "screenshots" / f"history_page_{page_num}.txt", page_html[:30000])
        rows = extract_history_rows(page_html, base_url)
        logger.log(f"history_page={page_num} parsed_rows={len(rows)}")

        if total_pages_hint is None:
            total_pages_hint = declared_last_page(page_html)

        new_rows = 0
        for row in rows:
            if row["order_no"] not in seen_orders:
                seen_orders.add(row["order_no"])
                all_rows.append(row)
                new_rows += 1
        logger.log(f"history_page={page_num} new_unique_rows={new_rows}")

        if not rows:
            break

        has_next = (
            f"?p={page_num + 1}" in page_html
            or (total_pages_hint is not None and page_num < total_pages_hint)
        )
        if not has_next:
            break
        page_num += 1

    logger.log(f"history_total_unique_orders={len(all_rows)}")
    if total_pages_hint is not None:
        logger.log(f"history_declared_last_page={total_pages_hint}")
    return all_rows


def filter_complete_orders(rows: list[dict], start_date: date, end_date: date) -> list[dict]:
    out = []
    for row in rows:
        if not row["date"]:
            continue
        if start_date <= row["date"] <= end_date and row["status"].strip().lower() == "complete":
            out.append(row)
    return out


def extract_grand_total(detail_html: str) -> Decimal | None:
    patterns = [
        r"Grand Total.*?\$([0-9,]+\.\d{2})",
        r'class=["\'][^"\']*grand_total[^"\']*["\'][\s\S]*?\$([0-9,]+\.\d{2})',
    ]
    matches = []
    for pat in patterns:
        for m in re.finditer(pat, detail_html, re.I | re.S):
            matches.append(m.group(1))
    if matches:
        return Decimal(matches[-1].replace(",", ""))
    return None


def fetch_order_grand_total(session: CurlSession, row: dict, run_dir: Path, logger: Logger) -> Decimal:
    if not row.get("view_url"):
        total = parse_money(row["total_text"])
        logger.log(f"order={row['order_no']} no_view_url_using_history_total={total}")
        return total

    detail_html = session.request(row["view_url"])
    write_text(run_dir / "screenshots" / f"order_{row['order_no']}.txt", detail_html[:30000])

    grand = extract_grand_total(detail_html)
    if grand is not None:
        logger.log(f"order={row['order_no']} verified_grand_total={grand}")
        return grand

    fallback = parse_money(row["total_text"])
    logger.log(f"order={row['order_no']} fallback_history_total={fallback}")
    return fallback


def sum_order_totals(session: CurlSession, rows: list[dict], run_dir: Path, logger: Logger) -> Decimal:
    total = Decimal("0.00")
    for row in rows:
        total += fetch_order_grand_total(session, row, run_dir, logger)
    return total.quantize(Decimal("0.01"))


def build_success(retrieved_data):
    return {
        "task_type": "RETRIEVE",
        "status": "SUCCESS",
        "retrieved_data": retrieved_data,
        "error_details": None,
    }


def build_error(message: str):
    return {
        "task_type": "RETRIEVE",
        "status": "ERROR",
        "retrieved_data": [],
        "error_details": message,
    }


def validate_output_shape(retrieved_data, output_schema: dict):
    if output_schema.get("type") != "array":
        raise ValueError("Unsupported output_schema: expected top-level array")
    if not isinstance(retrieved_data, list) or len(retrieved_data) != 1:
        raise ValueError("retrieved_data must be a one-item array")
    item = retrieved_data[0]
    if not isinstance(item, dict):
        raise ValueError("retrieved_data[0] must be an object")
    if set(item.keys()) != {"order_count", "amount"}:
        raise ValueError("retrieved_data[0] must contain exactly order_count and amount")


def run_task(taskspec: dict, workspace: Path, run_dir: Path, logger: Logger):
    params = taskspec.get("params", {})
    base_url = taskspec.get("start_url")
    credentials = taskspec.get("credentials", {})
    output_schema = taskspec.get("output_schema", {})

    if not base_url:
        raise ValueError("taskspec.start_url is required")
    period = params.get("period")
    if not period:
        raise ValueError("taskspec.params.period is required")

    start_date, end_date = parse_period(period, TODAY)
    logger.log(f"period={period}")
    logger.log(f"date_window={start_date.isoformat()}..{end_date.isoformat()}")

    session = CurlSession(run_dir / "cookies.txt", logger)
    login(session, base_url, credentials, run_dir, logger)

    all_orders = fetch_all_order_history(session, base_url, run_dir, logger)
    included = filter_complete_orders(all_orders, start_date, end_date)
    logger.log(f"included_complete_orders={len(included)}")
    for row in included:
        logger.log(
            f"included order={row['order_no']} date={row['date_text']} total={row['total_text']} status={row['status']}"
        )

    amount = sum_order_totals(session, included, run_dir, logger) if included else Decimal("0.00")
    retrieved_data = [{"order_count": len(included), "amount": float(amount)}]
    validate_output_shape(retrieved_data, output_schema)
    return build_success(retrieved_data)


def main():
    workspace = get_workspace()
    run_dir = next_run_dir(workspace)
    logger = Logger(run_dir / "final_script_log.txt")

    try:
        if len(os.sys.argv) < 2:
            raise ValueError("Expected taskspec.json path as argv[1]")
        taskspec_path = Path(os.sys.argv[1]).resolve()
        taskspec = json.loads(taskspec_path.read_text(encoding="utf-8"))
        response = run_task(taskspec, workspace, run_dir, logger)
    except Exception as e:
        logger.log(f"ERROR: {e}")
        response = build_error(str(e))

    (workspace / "agent_response.json").write_text(
        json.dumps(response, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
