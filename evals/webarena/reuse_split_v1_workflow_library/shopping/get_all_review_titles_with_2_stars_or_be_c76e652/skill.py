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

#!/usr/bin/env python3
import json
import os
import re
import struct
import textwrap
import zlib
from html import unescape
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def get_workspace() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", os.getcwd())).resolve()


WORKSPACE = get_workspace()


FONT = {
    'A':['01110','10001','10001','11111','10001','10001','10001'],
    'B':['11110','10001','10001','11110','10001','10001','11110'],
    'C':['01110','10001','10000','10000','10000','10001','01110'],
    'D':['11110','10001','10001','10001','10001','10001','11110'],
    'E':['11111','10000','10000','11110','10000','10000','11111'],
    'F':['11111','10000','10000','11110','10000','10000','10000'],
    'G':['01110','10001','10000','10111','10001','10001','01110'],
    'H':['10001','10001','10001','11111','10001','10001','10001'],
    'I':['11111','00100','00100','00100','00100','00100','11111'],
    'J':['00111','00010','00010','00010','10010','10010','01100'],
    'K':['10001','10010','10100','11000','10100','10010','10001'],
    'L':['10000','10000','10000','10000','10000','10000','11111'],
    'M':['10001','11011','10101','10101','10001','10001','10001'],
    'N':['10001','11001','10101','10011','10001','10001','10001'],
    'O':['01110','10001','10001','10001','10001','10001','01110'],
    'P':['11110','10001','10001','11110','10000','10000','10000'],
    'Q':['01110','10001','10001','10001','10101','10010','01101'],
    'R':['11110','10001','10001','11110','10100','10010','10001'],
    'S':['01111','10000','10000','01110','00001','00001','11110'],
    'T':['11111','00100','00100','00100','00100','00100','00100'],
    'U':['10001','10001','10001','10001','10001','10001','01110'],
    'V':['10001','10001','10001','10001','10001','01010','00100'],
    'W':['10001','10001','10001','10101','10101','10101','01010'],
    'X':['10001','10001','01010','00100','01010','10001','10001'],
    'Y':['10001','10001','01010','00100','00100','00100','00100'],
    'Z':['11111','00001','00010','00100','01000','10000','11111'],
    '0':['01110','10001','10011','10101','11001','10001','01110'],
    '1':['00100','01100','00100','00100','00100','00100','01110'],
    '2':['01110','10001','00001','00010','00100','01000','11111'],
    '3':['11110','00001','00001','01110','00001','00001','11110'],
    '4':['00010','00110','01010','10010','11111','00010','00010'],
    '5':['11111','10000','10000','11110','00001','00001','11110'],
    '6':['01110','10000','10000','11110','10001','10001','01110'],
    '7':['11111','00001','00010','00100','01000','01000','01000'],
    '8':['01110','10001','10001','01110','10001','10001','01110'],
    '9':['01110','10001','10001','01111','00001','00001','01110'],
    ':':['00000','00100','00100','00000','00100','00100','00000'],
    '.':['00000','00000','00000','00000','00000','00110','00110'],
    ',':['00000','00000','00000','00000','00110','00110','00100'],
    '-':['00000','00000','00000','11111','00000','00000','00000'],
    '_':['00000','00000','00000','00000','00000','00000','11111'],
    '/':['00001','00010','00100','01000','10000','00000','00000'],
    '"':['01010','01010','00000','00000','00000','00000','00000'],
    "'":['00100','00100','00000','00000','00000','00000','00000'],
    '(':['00010','00100','01000','01000','01000','00100','00010'],
    ')':['01000','00100','00010','00010','00010','00100','01000'],
    '[':['01110','01000','01000','01000','01000','01000','01110'],
    ']':['01110','00010','00010','00010','00010','00010','01110'],
    '{':['00010','00100','00100','01000','00100','00100','00010'],
    '}':['01000','00100','00100','00010','00100','00100','01000'],
    '!':['00100','00100','00100','00100','00100','00000','00100'],
    '?':['01110','10001','00001','00010','00100','00000','00100'],
    '=':['00000','11111','00000','11111','00000','00000','00000'],
    '>':['10000','01000','00100','00010','00100','01000','10000'],
    '<':['00001','00010','00100','01000','00100','00010','00001'],
    '%':['11001','11010','00100','01000','10110','00110','00000'],
    '&':['01100','10010','10100','01000','10101','10010','01101'],
    '+':['00000','00100','00100','11111','00100','00100','00000'],
    '*':['00000','10101','01110','11111','01110','10101','00000'],
    ' ':['00000','00000','00000','00000','00000','00000','00000']
}


def ensure_output_dirs(workspace: Path):
    run_dir = workspace / "artifacts"
    screenshots_dir = run_dir / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    return run_dir, screenshots_dir


RUN_DIR, SCREENSHOTS_DIR = ensure_output_dirs(WORKSPACE)
LOG_PATH = RUN_DIR / "skill_log.txt"


def log(message: str):
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def fetch_url(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def strip_tags(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", unescape(s or "")).strip()


def decode_js_escaped_url(s: str) -> str:
    if not s:
        return s
    s = s.encode("utf-8").decode("unicode_escape")
    s = s.replace("\\/", "/").replace("\\u002F", "/").replace("\\u003A", ":").replace("\\u002D", "-")
    return s


def write_png(path: Path, width: int, height: int, rgb_rows):
    raw = bytearray()
    for row in rgb_rows:
        raw.append(0)
        raw.extend(row)

    def chunk(tag, data):
        return struct.pack('!I', len(data)) + tag + data + struct.pack('!I', zlib.crc32(tag + data) & 0xffffffff)

    png = bytearray(b'\x89PNG\r\n\x1a\n')
    png += chunk(b'IHDR', struct.pack('!IIBBBBB', width, height, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(bytes(raw), 9))
    png += chunk(b'IEND', b'')
    path.write_bytes(png)


def render_text_png(path: Path, title: str, lines, width: int = 1280, height: int = 1800):
    bg = [255, 255, 255]
    fg = [20, 20, 20]
    accent = [52, 86, 160]
    rows = [[*bg] * width for _ in range(height)]

    def fill_rect(x, y, w, h, color):
        for yy in range(max(0, y), min(height, y + h)):
            row = rows[yy]
            for xx in range(max(0, x), min(width, x + w)):
                row[xx * 3: xx * 3 + 3] = color

    def draw_char(x, y, ch, color, scale=3):
        patt = FONT.get(ch.upper(), FONT['?'])
        for ry, bits in enumerate(patt):
            for rx, bit in enumerate(bits):
                if bit == '1':
                    fill_rect(x + rx * scale, y + ry * scale, scale, scale, color)

    def draw_text(x, y, text, color=fg, scale=3, max_width=1180):
        cx, cy = x, y
        for paragraph in str(text).split("\n"):
            words = paragraph.split(" ")
            if not words:
                cy += 10 * scale
                cx = x
                continue
            for raw_word in words:
                word = raw_word + " "
                ww = len(word) * 6 * scale
                if cx + ww > x + max_width:
                    cx = x
                    cy += 10 * scale
                for ch in word:
                    draw_char(cx, cy, ch, color, scale)
                    cx += 6 * scale
            cx = x
            cy += 10 * scale
        return cy

    fill_rect(0, 0, width, 90, accent)
    draw_text(30, 24, title, color=[255, 255, 255], scale=4, max_width=1200)

    y = 120
    for line in lines:
        y = draw_text(40, y, line, color=fg, scale=3, max_width=1180) + 24
        if y > height - 50:
            break

    write_png(path, width, height, rows)


def load_taskspec(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def discover_review_url(product_html: str, start_url: str, params: dict) -> str:
    if params.get("review_url"):
        return params["review_url"]

    patterns = [
        r'"productReviewUrl"\s*:\s*"(.*?)"',
        r"'productReviewUrl'\s*:\s*'(.*?)'",
        r'review/product/listAjax/id/\d+/'
    ]
    for pattern in patterns:
        m = re.search(pattern, product_html, re.I | re.S)
        if m:
            candidate = m.group(1) if m.lastindex else m.group(0)
            candidate = decode_js_escaped_url(candidate)
            if candidate.startswith("http://") or candidate.startswith("https://"):
                return candidate
            return urljoin(start_url, candidate)

    pid_match = re.search(r'review/product/listAjax/id/(\d+)/', product_html, re.I)
    if pid_match:
        return urljoin(start_url, f"/review/product/listAjax/id/{pid_match.group(1)}/")

    raise RuntimeError("Could not discover review AJAX/list URL from product page")


def extract_declared_review_count(product_html: str):
    patterns = [
        r'itemprop="reviewCount">(\d+)</',
        r'<span[^>]*itemprop=["\']reviewCount["\'][^>]*>\s*(\d+)\s*</span>',
        r'"reviewCount"\s*:\s*"?(\d+)"?'
    ]
    for pattern in patterns:
        m = re.search(pattern, product_html, re.I | re.S)
        if m:
            return int(m.group(1))
    return None


def parse_review_items(review_html: str):
    blocks = re.findall(r'<li[^>]*class="[^"]*\bitem\b[^"]*\breview-item\b[^"]*"[\s\S]*?</li>', review_html, re.I)
    reviews = []

    for block in blocks:
        title = ""
        title_patterns = [
            r'<div[^>]*class="[^"]*\breview-title\b[^"]*"[^>]*>(.*?)</div>',
            r'itemprop=["\']name["\'][^>]*>\s*(.*?)\s*</',
        ]
        for tp in title_patterns:
            tm = re.search(tp, block, re.I | re.S)
            if tm:
                title = strip_tags(tm.group(1))
                break

        pct = None
        pct_patterns = [
            r'title="(\d+)%"',
            r'itemprop=["\']ratingValue["\']>\s*(\d+)%\s*</span>',
            r'(\d+)%'
        ]
        for pp in pct_patterns:
            pm = re.search(pp, block, re.I | re.S)
            if pm:
                try:
                    pct = int(pm.group(1))
                    break
                except Exception:
                    pass

        reviews.append({
            "title": title,
            "rating_percent": pct,
            "raw_text": strip_tags(block)
        })

    return reviews


def maybe_follow_review_pagination(initial_review_url: str, initial_html: str, max_pages: int = 20):
    pages = [(initial_review_url, initial_html)]
    seen_urls = {initial_review_url}
    current_html = initial_html
    current_url = initial_review_url

    for _ in range(max_pages - 1):
        next_url = None
        candidates = [
            r'<a[^>]+class="[^"]*\bnext\b[^"]*"[^>]+href="([^"]+)"',
            r'<a[^>]+href="([^"]+)"[^>]*>\s*Next\s*</a>',
            r'<li[^>]*class="[^"]*\bpages-item-next\b[^"]*"[\s\S]*?<a[^>]+href="([^"]+)"'
        ]
        for pattern in candidates:
            m = re.search(pattern, current_html, re.I | re.S)
            if m:
                next_url = urljoin(current_url, decode_js_escaped_url(m.group(1)))
                break

        if not next_url or next_url in seen_urls:
            break

        next_html = fetch_url(next_url)
        pages.append((next_url, next_html))
        seen_urls.add(next_url)
        current_url, current_html = next_url, next_html

    return pages


def dedupe_reviews(reviews):
    seen = set()
    out = []
    for r in reviews:
        key = (normalize_whitespace(r.get("title", "")), r.get("rating_percent"), normalize_whitespace(r.get("raw_text", "")))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def rating_percent_to_stars_upper_bound(percent: int):
    if percent is None:
        return None
    return percent / 20.0


def filter_low_star_review_titles(reviews, max_stars: float = 2.0):
    titles = []
    for r in reviews:
        pct = r.get("rating_percent")
        title = normalize_whitespace(r.get("title", ""))
        if pct is None or not title:
            continue
        if rating_percent_to_stars_upper_bound(pct) <= max_stars:
            titles.append(title)
    return titles


def validate_output_schema(output_schema: dict):
    if output_schema != {"type": "array", "items": {"type": "string"}}:
        raise RuntimeError(f"Unsupported output_schema for this skill: {output_schema}")


def write_agent_response(status: str, retrieved_data, error_details=None):
    response = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    out_path = WORKSPACE / "agent_response.json"
    out_path.write_text(json.dumps(response, indent=2, ensure_ascii=False), encoding="utf-8")
    return response


def run_task(taskspec: dict):
    params = taskspec.get("params", {}) or {}
    start_url = taskspec["start_url"]
    output_schema = taskspec.get("output_schema", {})
    validate_output_schema(output_schema)

    log("step 1: fetch product page and identify review endpoint")
    product_html = fetch_url(start_url)
    declared_count = extract_declared_review_count(product_html)
    page_title_match = re.search(r"<title>(.*?)</title>", product_html, re.I | re.S)
    page_title = strip_tags(page_title_match.group(1)) if page_title_match else ""
    review_url = discover_review_url(product_html, start_url, params)

    render_text_png(
        SCREENSHOTS_DIR / "step1_product_page.png",
        "STEP 1 PRODUCT PAGE",
        [
            f"Start URL: {start_url}",
            f"Page title: {page_title}",
            f"Discovered review URL: {review_url}",
            f"Declared review count: {declared_count if declared_count is not None else 'unknown'}",
        ],
    )

    log("step 2: fetch review pages and parse all reviews")
    first_review_html = fetch_url(review_url)
    review_pages = maybe_follow_review_pagination(review_url, first_review_html, max_pages=int(params.get("max_review_pages", 20)))

    all_reviews = []
    page_summaries = []
    for idx, (url, html) in enumerate(review_pages, start=1):
        page_reviews = parse_review_items(html)
        all_reviews.extend(page_reviews)
        page_summaries.append(f"Page {idx}: {url} -> parsed {len(page_reviews)} review items")

    all_reviews = dedupe_reviews(all_reviews)

    render_text_png(
        SCREENSHOTS_DIR / "step2_review_parsing.png",
        "STEP 2 REVIEW PARSING",
        page_summaries + [
            f"Unique reviews parsed: {len(all_reviews)}",
            *[
                f'{i+1}. title="{r["title"]}" rating_percent={r["rating_percent"]}'
                for i, r in enumerate(all_reviews[:40])
            ]
        ],
    )

    if declared_count is not None and len(all_reviews) < declared_count:
        log(f"warning: parsed fewer unique reviews ({len(all_reviews)}) than declared review count ({declared_count})")

    log("step 3: filter to titles with 2 stars or below")
    max_stars = float(params.get("max_stars", 2))
    qualifying_titles = filter_low_star_review_titles(all_reviews, max_stars=max_stars)

    render_text_png(
        SCREENSHOTS_DIR / "step3_filtered_results.png",
        "STEP 3 FILTERED RESULTS",
        [
            f"Rule: include review titles with stars <= {max_stars}",
            "Magento-style review ratings are represented as percentages out of 100.",
            f"Operational threshold used: rating_percent <= {int(max_stars * 20)}",
            f"Qualifying titles count: {len(qualifying_titles)}",
            *([f"- {t}" for t in qualifying_titles] if qualifying_titles else ["No qualifying review titles found."])
        ],
    )

    status = "SUCCESS" if qualifying_titles else "NOT_FOUND_ERROR"
    retrieved_data = qualifying_titles if qualifying_titles else None

    log(f"step 4: write response status={status}")
    return write_agent_response(status=status, retrieved_data=retrieved_data, error_details=None)


def main():
    LOG_PATH.write_text("", encoding="utf-8")
    taskspec_path = os.sys.argv[1]
    taskspec = load_taskspec(taskspec_path)
    try:
        run_task(taskspec)
    except Exception as e:
        log(f"error: {type(e).__name__}: {e}")
        write_agent_response(
            status="ERROR",
            retrieved_data=None,
            error_details={"type": type(e).__name__, "message": str(e)}
        )


if __name__ == "__main__":
    main()
