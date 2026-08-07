# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --status ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['status']
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

from pathlib import Path
import json
import os
import re
import sys
from urllib.request import build_opener, HTTPCookieProcessor, Request
from urllib.parse import urlencode
from http.cookiejar import CookieJar


def get_workspace() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", os.getcwd())).resolve()


WORKSPACE = get_workspace()
RUN_DIR = WORKSPACE / "run_artifacts"
SCREENSHOTS = RUN_DIR / "screenshots"
LOG_PATH = RUN_DIR / "skill_log.txt"
AGENT_RESPONSE_PATH = WORKSPACE / "agent_response.json"

RUN_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOTS.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def save_text_image(path: Path, text: str) -> None:
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (1400, 1800), "white")
        draw = ImageDraw.Draw(img)
        y = 20
        for raw in text.splitlines():
            line = raw[:180]
            draw.text((20, y), line, fill="black")
            y += 22
            if y > 1760:
                break
        img.save(path)
        return
    except Exception:
        pass

    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1800">']
    svg.append('<rect width="100%" height="100%" fill="white"/>')
    y = 30
    for raw in text.splitlines()[:70]:
        esc = (
            raw.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        svg.append(
            f'<text x="20" y="{y}" font-size="18" font-family="monospace" fill="black">{esc}</text>'
        )
        y += 24
    svg.append("</svg>")
    path.write_text("".join(svg), encoding="utf-8")


def load_taskspec(path_str: str) -> dict:
    return json.loads(Path(path_str).read_text(encoding="utf-8"))


def get_base_admin_url(taskspec: dict) -> str:
    start_url = taskspec.get("start_url", "").strip()
    if not start_url:
        raise ValueError("taskspec.start_url is required")
    if not start_url.endswith("/"):
        start_url += "/"
    return start_url


def build_status_url(base_admin_url: str, status: str) -> str:
    status_slug = status.strip().lower().replace(" ", "")
    return f"{base_admin_url}review/product/{status_slug}/"


def build_all_reviews_url(base_admin_url: str) -> str:
    return f"{base_admin_url}review/product/index/"


def create_session():
    cj = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cj))
    return opener


def fetch_html(opener, url: str, data: bytes = None, headers: dict = None, timeout: int = 30):
    req = Request(url, data=data, headers=headers or {})
    resp = opener.open(req, timeout=timeout)
    html = resp.read().decode("utf-8", "ignore")
    return html, resp.geturl()


def extract_form_key(login_html: str) -> str:
    patterns = [
        r'name="form_key"\s+type="hidden"\s+value="([^"]+)"',
        r'name="form_key"\s+value="([^"]+)"',
        r'value="([^"]+)"\s+name="form_key"',
    ]
    for pattern in patterns:
        m = re.search(pattern, login_html, re.I)
        if m:
            return m.group(1)
    raise ValueError("Could not extract Magento form_key from login page")


def login_magento_admin(opener, base_admin_url: str, credentials: dict) -> dict:
    login_html, login_url = fetch_html(opener, base_admin_url)
    form_key = extract_form_key(login_html)

    username = credentials.get("username") or credentials.get("user") or "admin"
    password = credentials.get("password") or credentials.get("pass")
    if password is None:
        raise ValueError("Missing credentials.password in taskspec.credentials")

    payload = urlencode(
        {
            "form_key": form_key,
            "login[username]": username,
            "login[password]": password,
        }
    ).encode()

    dashboard_html, dashboard_url = fetch_html(
        opener,
        base_admin_url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    return {
        "login_url": login_url,
        "dashboard_url": dashboard_url,
        "form_key": form_key,
        "dashboard_html": dashboard_html,
    }


def strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def extract_review_ids(html: str):
    ids = re.findall(r"/admin/review/product/edit/id/(\d+)/", html)
    return sorted(set(ids), key=lambda x: int(x))


def extract_declared_total(html: str):
    text = strip_html(html)
    patterns = [
        r"\b(\d+)\s+records found\b",
        r"\btotal\s+(\d+)\b",
        r"\b(\d+)\s+item\(s\)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return int(m.group(1))
    return None


def extract_current_page(html: str):
    text = strip_html(html)
    patterns = [
        r"\bpage\s+(\d+)\s+of\s+\d+\b",
        r"\b(\d+)\s+of\s+\d+\s+Next page\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return int(m.group(1))
    return 1


def extract_total_pages(html: str):
    text = strip_html(html)
    patterns = [
        r"\bpage\s+\d+\s+of\s+(\d+)\b",
        r"\bof\s+(\d+)\s+Next page\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return int(m.group(1))
    return 1


def add_or_replace_page_param(url: str, page_num: int) -> str:
    if "?" in url:
        if re.search(r"([?&])p=\d+", url):
            return re.sub(r"([?&])p=\d+", lambda m: f"{m.group(1)}p={page_num}", url)
        return f"{url}&p={page_num}"
    return f"{url}?p={page_num}"


def extract_rows_across_pages(opener, list_url: str) -> dict:
    html, final_url = fetch_html(opener, list_url)
    total_pages = max(1, extract_total_pages(html))
    seen_ids = set(extract_review_ids(html))
    page_summaries = [
        {
            "page": extract_current_page(html),
            "url": final_url,
            "row_ids": sorted(seen_ids, key=lambda x: int(x)),
            "row_count": len(seen_ids),
        }
    ]
    declared_total = extract_declared_total(html)

    for page_num in range(2, total_pages + 1):
        page_url = add_or_replace_page_param(list_url, page_num)
        page_html, page_final_url = fetch_html(opener, page_url)
        page_ids = extract_review_ids(page_html)
        seen_ids.update(page_ids)
        page_summaries.append(
            {
                "page": page_num,
                "url": page_final_url,
                "row_ids": page_ids,
                "row_count": len(page_ids),
            }
        )

    unique_ids = sorted(seen_ids, key=lambda x: int(x))
    return {
        "unique_ids": unique_ids,
        "count": len(unique_ids),
        "declared_total": declared_total,
        "total_pages": total_pages,
        "page_summaries": page_summaries,
    }


def count_reviews_by_status(opener, base_admin_url: str, status: str) -> dict:
    status_url = build_status_url(base_admin_url, status)
    result = extract_rows_across_pages(opener, status_url)

    declared_total = result["declared_total"]
    if declared_total is not None and declared_total != result["count"]:
        raise ValueError(
            f"Count verification failed for status '{status}': "
            f"counted {result['count']} unique review ids across pages, "
            f"but page declared total {declared_total}"
        )

    result["status"] = status
    result["status_url"] = status_url
    return result


def write_agent_response(retrieved_data):
    response = {
        "task_type": "RETRIEVE",
        "status": "SUCCESS",
        "retrieved_data": retrieved_data,
        "error_details": None,
    }
    AGENT_RESPONSE_PATH.write_text(json.dumps(response), encoding="utf-8")
    return response


def write_error_response(message: str):
    response = {
        "task_type": "RETRIEVE",
        "status": "ERROR",
        "retrieved_data": [],
        "error_details": message,
    }
    AGENT_RESPONSE_PATH.write_text(json.dumps(response), encoding="utf-8")
    return response


def run_task(taskspec: dict):
    params = taskspec.get("params", {})
    credentials = taskspec.get("credentials", {})
    status = params.get("status")
    if not status:
        raise ValueError("taskspec.params.status is required")

    base_admin_url = get_base_admin_url(taskspec)
    opener = create_session()

    login_info = login_magento_admin(opener, base_admin_url, credentials)
    save_text_image(
        SCREENSHOTS / "01_login.png",
        "\n".join(
            [
                f"Login URL: {login_info['login_url']}",
                f"Dashboard URL: {login_info['dashboard_url']}",
                f"Form key extracted: {login_info['form_key']}",
                f"Dashboard HTML length: {len(login_info['dashboard_html'])}",
            ]
        ),
    )
    log(f"Logged into Magento admin at {login_info['dashboard_url']}")

    all_reviews = extract_rows_across_pages(opener, build_all_reviews_url(base_admin_url))
    save_text_image(
        SCREENSHOTS / "02_all_reviews.png",
        "\n".join(
            [
                f"All reviews URL: {build_all_reviews_url(base_admin_url)}",
                f"Pages: {all_reviews['total_pages']}",
                f"Unique IDs counted: {all_reviews['count']}",
                f"Declared total: {all_reviews['declared_total']}",
                f"Sample IDs: {', '.join(all_reviews['unique_ids'][:30])}",
            ]
        ),
    )
    log(
        f"All reviews checked: pages={all_reviews['total_pages']} "
        f"count={all_reviews['count']} declared_total={all_reviews['declared_total']}"
    )

    status_reviews = count_reviews_by_status(opener, base_admin_url, status)
    save_text_image(
        SCREENSHOTS / "03_status_reviews.png",
        "\n".join(
            [
                f"Status: {status}",
                f"Status URL: {status_reviews['status_url']}",
                f"Pages: {status_reviews['total_pages']}",
                f"Unique IDs counted: {status_reviews['count']}",
                f"Declared total: {status_reviews['declared_total']}",
                f"IDs: {', '.join(status_reviews['unique_ids'][:100])}",
            ]
        ),
    )
    log(
        f"Status '{status}' reviews counted successfully: "
        f"{status_reviews['count']} unique review ids"
    )

    response = write_agent_response([status_reviews["count"]])
    save_text_image(
        SCREENSHOTS / "04_agent_response.png",
        json.dumps(response, indent=2),
    )
    log(f"agent_response.json written with retrieved_data={[status_reviews['count']]}")


def main():
    LOG_PATH.write_text("", encoding="utf-8")
    try:
        if len(sys.argv) < 2:
            raise ValueError("Expected taskspec.json path in sys.argv[1]")
        taskspec = load_taskspec(sys.argv[1])
        run_task(taskspec)
    except Exception as e:
        log(f"ERROR: {e}")
        response = write_error_response(str(e))
        save_text_image(
            SCREENSHOTS / "error.png",
            json.dumps(response, indent=2),
        )


if __name__ == "__main__":
    main()
