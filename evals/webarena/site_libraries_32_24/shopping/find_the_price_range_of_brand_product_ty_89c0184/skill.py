# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --brand ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['brand', 'product_type']
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
import math
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from playwright.async_api import async_playwright, Page


def get_workspace_dir() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", os.getcwd()))


WORKSPACE = get_workspace_dir()
LOG_PATH = WORKSPACE / "skill_log.txt"
SCREENSHOT_DIR = WORKSPACE / "screenshots"
OUTPUT_PATH = WORKSPACE / "agent_response.json"

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH.write_text("", encoding="utf-8")


def log(message: str) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(message + "\n")
    print(message)


def load_taskspec(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_response(status: str, retrieved_data, error_details=None) -> None:
    payload = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    OUTPUT_PATH.write_text(json.dumps(payload), encoding="utf-8")


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()


def tokenize(s: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", normalize_text(s))


def parse_price(price_text: str) -> Optional[float]:
    if not price_text:
        return None
    m = re.search(r"([0-9][0-9,]*\.?[0-9]*)", price_text.replace("\xa0", " "))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except Exception:
        return None


def singularize(token: str) -> str:
    if token.endswith("ies") and len(token) > 3:
        return token[:-3] + "y"
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


def build_search_query(brand: str, product_type: str) -> str:
    return f"{brand} {product_type}".strip()


def get_default_negative_keywords() -> List[str]:
    return [
        "case", "cable", "charger", "album", "print head", "printhead",
        "replacement", "accessories", "accessory", "cartridge", "toner",
        "paper set", "sleeve", "adapter", "film", "cover", "parts",
        "laser unit", "ink", "refill", "drum", "maintenance", "kit",
        "ribbon", "tray", "roller", "head", "pack"
    ]


def build_product_matcher(brand: str, product_type: str):
    brand_tokens = [singularize(t) for t in tokenize(brand)]
    type_tokens = [singularize(t) for t in tokenize(product_type)]
    negative_keywords = [normalize_text(x) for x in get_default_negative_keywords()]

    essential_type_tokens = [
        t for t in type_tokens
        if t not in {"photo", "wireless", "digital", "portable", "color", "black", "white"}
    ]

    def matcher(name: str) -> bool:
        n = normalize_text(name)
        n_tokens = [singularize(t) for t in tokenize(n)]

        if any(kw in n for kw in negative_keywords):
            return False

        if brand_tokens and not all(bt in n_tokens for bt in brand_tokens):
            return False

        if essential_type_tokens and not all(tt in n_tokens for tt in essential_type_tokens):
            return False

        optional_signals = [t for t in type_tokens if t not in essential_type_tokens]
        if optional_signals:
            if any(sig in n_tokens for sig in optional_signals):
                return True

        return True

    return matcher


async def open_site(page: Page, start_url: str) -> None:
    log(f"Opening site: {start_url}")
    await page.goto(start_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(1500)
    await page.screenshot(path=str(SCREENSHOT_DIR / "01_home.png"))


async def search_catalog(page: Page, query: str) -> None:
    log(f"Searching for: {query}")
    search_box = page.get_by_placeholder("Search entire store here...")
    await search_box.fill(query)
    await page.get_by_role("button", name=re.compile(r"search", re.I)).click()
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(2000)
    await page.screenshot(path=str(SCREENSHOT_DIR / "02_search_results.png"))


async def extract_visible_products(page: Page) -> List[Dict]:
    locator = page.locator("li.product-item")
    count = await locator.count()
    log(f"Visible product cards: {count}")
    if count == 0:
        return []

    products = await locator.evaluate_all(
        """
        els => els.map(el => {
          const name =
            el.querySelector('.product-item-link')?.textContent?.trim() ||
            el.querySelector('a.product-item-link')?.textContent?.trim() ||
            '';
          const price =
            el.querySelector('.price')?.textContent?.trim() ||
            '';
          return { name, price };
        }).filter(x => x.name)
        """
    )
    return products


def filter_and_parse_products(
    raw_products: List[Dict], brand: str, product_type: str
) -> Tuple[List[Dict], List[Dict]]:
    matcher = build_product_matcher(brand, product_type)
    parsed = []

    for item in raw_products:
        name = (item.get("name") or "").strip()
        price = parse_price(item.get("price") or "")
        included = matcher(name) if name else False
        parsed.append({
            "name": name,
            "price": price,
            "included": included,
        })

    included = [x for x in parsed if x["included"] and isinstance(x["price"], (int, float)) and not math.isnan(x["price"])]
    included.sort(key=lambda x: x["price"])
    return parsed, included


def compute_price_range(products: List[Dict]) -> Optional[Dict]:
    if not products:
        return None
    return {
        "min": float(products[0]["price"]),
        "max": float(products[-1]["price"]),
    }


def validate_output_schema(retrieved_data) -> bool:
    return (
        isinstance(retrieved_data, list)
        and all(isinstance(x, dict) for x in retrieved_data)
    )


async def run_task(taskspec: dict) -> None:
    params = taskspec.get("params", {})
    start_url = taskspec.get("start_url")
    brand = params.get("brand", "").strip()
    product_type = params.get("product_type", "").strip()

    if not start_url or not brand or not product_type:
        write_response(
            "INPUT_ERROR",
            None,
            "Missing required fields: start_url, params.brand, or params.product_type",
        )
        return

    query = build_search_query(brand, product_type)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 1800})
        page = await context.new_page()

        try:
            await open_site(page, start_url)
            await search_catalog(page, query)

            raw_products = await extract_visible_products(page)
            parsed, included = filter_and_parse_products(raw_products, brand, product_type)

            log("Parsed products:")
            for item in parsed:
                log(json.dumps(item, ensure_ascii=False))

            if not included:
                await page.screenshot(path=str(SCREENSHOT_DIR / "03_no_matches.png"))
                write_response("NOT_FOUND_ERROR", None, None)
                return

            price_range = compute_price_range(included)
            await page.screenshot(path=str(SCREENSHOT_DIR / "03_range_evidence.png"))

            retrieved_data = [price_range]
            if not validate_output_schema(retrieved_data):
                write_response("ERROR", None, "Output did not match required schema")
                return

            log(f"Matched products count: {len(included)}")
            log("Included products:")
            for item in included:
                log(json.dumps(item, ensure_ascii=False))
            log(f"Computed range: {price_range}")

            write_response("SUCCESS", retrieved_data, None)

        except Exception as e:
            log(f"ERROR: {e}")
            try:
                await page.screenshot(path=str(SCREENSHOT_DIR / "error.png"))
            except Exception:
                pass
            write_response("ERROR", None, str(e))
        finally:
            await browser.close()


def main():
    taskspec_path = sys.argv[1]
    taskspec = load_taskspec(taskspec_path)
    asyncio.run(run_task(taskspec))


if __name__ == "__main__":
    main()
