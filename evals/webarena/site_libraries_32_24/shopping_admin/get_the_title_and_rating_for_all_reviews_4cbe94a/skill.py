# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --max-stars ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['max_stars', 'product']
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
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.async_api import async_playwright, Page


def get_workspace_dir() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", os.getcwd())).resolve()


def ensure_output_dirs(workspace: Path) -> Dict[str, Path]:
    run_dir = workspace / "artifacts"
    shots = run_dir / "screenshots"
    run_dir.mkdir(parents=True, exist_ok=True)
    shots.mkdir(parents=True, exist_ok=True)
    return {"run_dir": run_dir, "screenshots": shots}


def read_taskspec(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_agent_response(
    workspace: Path,
    retrieved_data: Optional[List[Dict[str, Any]]],
    status: str = "SUCCESS",
    error_details: Optional[str] = None,
) -> None:
    payload = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    (workspace / "agent_response.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


class Logger:
    def __init__(self, path: Path):
        self.path = path
        self.path.write_text("", encoding="utf-8")

    def log(self, msg: str) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
        print(msg)


async def safe_goto(page: Page, url: str, wait_until: str = "domcontentloaded", attempts: int = 3) -> None:
    last_exc = None
    for attempt in range(attempts):
        try:
            await page.goto(url, wait_until=wait_until, timeout=60000)
            return
        except Exception as e:
            last_exc = e
            if attempt < attempts - 1:
                await page.wait_for_timeout(1500)
    raise last_exc


def normalize_text(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def product_matches(actual: str, target: str) -> bool:
    a = normalize_text(actual)
    t = normalize_text(target)
    return a == t or a in t or t in a


def coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


async def login(page: Page, start_url: str, credentials: Dict[str, Any], log) -> None:
    await safe_goto(page, start_url, wait_until="domcontentloaded")
    password_loc = page.locator('input[type="password"], input[name="login[password]"], input[name="password"]')
    if await password_loc.count() == 0:
        log("Login not required or already authenticated.")
        return

    username = credentials.get("username") or credentials.get("user") or "admin"
    password = credentials.get("password") or "admin1234"

    user_loc = page.locator('input[name="login[username]"], input[name="username"], input[type="text"]').first
    pass_loc = password_loc.first

    await user_loc.fill(str(username))
    await pass_loc.fill(str(password))

    sign_in_btn = page.get_by_role("button", name=re.compile(r"sign in", re.I)).first
    if await sign_in_btn.count():
        await sign_in_btn.click()
    else:
        await pass_loc.press("Enter")

    await page.wait_for_load_state("networkidle")


def build_reviews_grid_url(start_url: str) -> str:
    return start_url.rstrip("/") + "/review/product/"


def build_review_detail_url(start_url: str, review_id: str) -> str:
    return start_url.rstrip("/") + f"/review/product/edit/id/{review_id}/"


async def open_reviews_grid(page: Page, start_url: str, log) -> None:
    url = build_reviews_grid_url(start_url)
    await safe_goto(page, url, wait_until="networkidle")
    log(f"Opened reviews grid: {url}")


async def filter_reviews_by_product(page: Page, product: str, log) -> None:
    candidates = [
        "#reviewGrid_filter_name",
        'input[name="name"]',
        'input[placeholder*="Product" i]',
    ]
    field = None
    for sel in candidates:
        loc = page.locator(sel)
        if await loc.count():
            field = loc.first
            break
    if field is None:
        raise RuntimeError("Could not locate product filter field in review grid.")

    await field.fill(product)
    await field.press("Enter")
    await page.wait_for_load_state("networkidle")
    log(f"Filtered reviews grid by product: {product}")


async def extract_review_rows_from_grid(page: Page, target_product: str, log) -> List[Dict[str, str]]:
    rows = page.locator("tbody tr")
    count = await rows.count()
    out: List[Dict[str, str]] = []

    for i in range(count):
        row = rows.nth(i)
        tds = row.locator("td")
        td_count = await tds.count()
        if td_count < 5:
            continue
        texts = []
        for j in range(td_count):
            texts.append((await tds.nth(j).inner_text()).strip())

        review_id = texts[1] if len(texts) > 1 else ""
        title = texts[4] if len(texts) > 4 else ""
        row_text = " ".join(texts)
        if review_id and title and product_matches(row_text, target_product):
            out.append({"review_id": review_id, "title": title})

    deduped = []
    seen = set()
    for item in out:
        key = item["review_id"]
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    log(f"Collected {len(deduped)} candidate review rows from grid.")
    return deduped


async def extract_review_detail(page: Page, start_url: str, review_id: str, log) -> Dict[str, str]:
    detail_url = build_review_detail_url(start_url, review_id)
    await safe_goto(page, detail_url, wait_until="networkidle")

    product = ""
    product_candidates = [
        'a[href*="catalog/product/edit"]',
        '.admin__field:has-text("Product") .admin__field-value',
    ]
    for sel in product_candidates:
        loc = page.locator(sel)
        if await loc.count():
            try:
                product = (await loc.first.inner_text()).strip()
                if product:
                    break
            except Exception:
                pass

    rating = ""
    checked_radio = page.locator('input[type="radio"]:checked')
    if await checked_radio.count():
        checked_id = await checked_radio.first.get_attribute("id")
        if checked_id:
            m = re.search(r"(\d+)$", checked_id)
            if m:
                rating = m.group(1)

    if not rating:
        body_text = await page.locator("body").inner_text()
        m = re.search(r"\b([1-5])\s*(?:stars?|/ ?5)\b", body_text, re.I)
        if m:
            rating = m.group(1)

    log(f"Extracted review detail for id={review_id}: product={product!r}, rating={rating!r}")
    return {"product": product, "rating": rating}


async def collect_matching_reviews(
    page: Page,
    start_url: str,
    product: str,
    max_stars: int,
    screenshots_dir: Path,
    log,
) -> List[Dict[str, str]]:
    await open_reviews_grid(page, start_url, log)
    await filter_reviews_by_product(page, product, log)
    await page.screenshot(path=str(screenshots_dir / "reviews_grid_filtered.png"))

    candidates = await extract_review_rows_from_grid(page, product, log)
    results: List[Dict[str, str]] = []

    for idx, item in enumerate(candidates, start=1):
        detail = await extract_review_detail(page, start_url, item["review_id"], log)
        await page.screenshot(path=str(screenshots_dir / f"review_detail_{idx}_{item['review_id']}.png"))

        rating_int = coerce_int(detail.get("rating"), default=999)
        if product_matches(detail.get("product", ""), product) and rating_int <= max_stars:
            results.append({"title": item["title"], "rating": str(rating_int)})
            log(f"Included review id={item['review_id']} with title={item['title']!r}, rating={rating_int}")
        else:
            log(
                f"Excluded review id={item['review_id']} "
                f"(product={detail.get('product', '')!r}, rating={detail.get('rating', '')!r})"
            )

    return results


def validate_output_schema(data: Any, output_schema: Dict[str, Any]) -> None:
    if output_schema.get("type") != "array":
        raise RuntimeError("This skill expects output_schema.type == 'array'.")
    if not isinstance(data, list):
        raise RuntimeError("Retrieved data must be a list.")
    for item in data:
        if not isinstance(item, dict):
            raise RuntimeError("Each retrieved item must be an object/dict.")


async def run() -> None:
    workspace = get_workspace_dir()
    dirs = ensure_output_dirs(workspace)
    logger = Logger(dirs["run_dir"] / "log.txt")

    try:
        taskspec_path = sys.argv[1]
    except IndexError:
        write_agent_response(workspace, None, status="ERROR", error_details="Missing taskspec path argument.")
        return

    try:
        taskspec = read_taskspec(taskspec_path)
        params = taskspec.get("params", {})
        start_url = taskspec.get("start_url")
        credentials = taskspec.get("credentials", {}) or {}
        output_schema = taskspec.get("output_schema", {})

        product = params.get("product")
        max_stars = coerce_int(params.get("max_stars"))

        if not start_url:
            raise RuntimeError("taskspec.start_url is required.")
        if not product:
            raise RuntimeError("taskspec.params.product is required.")

        logger.log(f"Task parameters: product={product!r}, max_stars={max_stars}, start_url={start_url!r}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1280, "height": 1800})
            page = await context.new_page()
            page.set_default_timeout(60000)
            page.set_default_navigation_timeout(60000)

            await login(page, start_url, credentials, logger.log)
            await page.screenshot(path=str(dirs["screenshots"] / "after_login.png"))

            results = await collect_matching_reviews(
                page=page,
                start_url=start_url,
                product=product,
                max_stars=max_stars,
                screenshots_dir=dirs["screenshots"],
                log=logger.log,
            )

            await browser.close()

        validate_output_schema(results, output_schema)
        write_agent_response(workspace, results, status="SUCCESS", error_details=None)
        logger.log(f"Wrote {len(results)} results to agent_response.json")

    except Exception as e:
        logger.log(f"ERROR: {e}")
        write_agent_response(workspace, None, status="ERROR", error_details=str(e))


if __name__ == "__main__":
    asyncio.run(run())
