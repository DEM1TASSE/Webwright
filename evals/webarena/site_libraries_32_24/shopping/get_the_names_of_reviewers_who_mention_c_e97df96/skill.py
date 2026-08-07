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

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", Path.cwd()))
WORKSPACE.mkdir(parents=True, exist_ok=True)


class Logger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")

    def log(self, message: str) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(message.rstrip() + "\n")


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def load_taskspec(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_response(retrieved_data, status: str = "SUCCESS", error_details: Optional[str] = None) -> None:
    response = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    (WORKSPACE / "agent_response.json").write_text(json.dumps(response, indent=2), encoding="utf-8")


async def save_screenshot(page, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(path), full_page=True)


async def open_page(page, url: str) -> None:
    await page.goto(url, wait_until="networkidle")


async def reveal_reviews_section(page, logger: Logger) -> None:
    review_tab_selectors = [
        "#tab-label-reviews",
        "#tab-label-reviews-title",
        'text="Reviews"',
    ]
    for selector in review_tab_selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() > 0:
                await locator.click()
                await page.wait_for_timeout(1500)
                logger.log(f"Clicked reviews control: {selector}")
                return
        except Exception:
            continue
    logger.log("No explicit reviews tab clicked; continuing with current page content.")


async def auto_expand_reviews(page, logger: Logger) -> None:
    expand_texts = [
        "Read more",
        "Show more",
        "See more",
    ]
    for txt in expand_texts:
        try:
            loc = page.get_by_text(txt, exact=False)
            count = await loc.count()
            for i in range(min(count, 20)):
                try:
                    await loc.nth(i).click(timeout=500)
                    await page.wait_for_timeout(100)
                except Exception:
                    pass
        except Exception:
            pass
    logger.log("Attempted to expand truncated review text.")


async def collect_all_review_text(page, logger: Logger, max_rounds: int = 8) -> str:
    last_len = 0
    body_text = ""
    for round_idx in range(max_rounds):
        body_text = await page.locator("body").inner_text()
        curr_len = len(body_text)
        logger.log(f"Collection round {round_idx + 1}: body text length={curr_len}")
        if curr_len <= last_len and round_idx > 0:
            break
        last_len = curr_len
        await page.mouse.wheel(0, 2500)
        await page.wait_for_timeout(800)
        await auto_expand_reviews(page, logger)
    return body_text


def parse_reviews_from_text(raw_text: str) -> List[Dict[str, str]]:
    text = (raw_text or "").replace("\r", "")
    pattern = re.compile(
        r"(?P<title>.+?)\nRating\s*\n(?P<rating>\d+)%\s*\n(?P<body>.*?)\nReview by (?P<name>.+?)\n\nPosted on (?P<date>.+?)(?=\n\n.+?\nRating\s*\n\d+%\s*\n|\Z)",
        re.S,
    )
    reviews = []
    for m in pattern.finditer(text):
        reviews.append(
            {
                "title": normalize_ws(m.group("title")),
                "rating": normalize_ws(m.group("rating")),
                "body": normalize_ws(m.group("body")),
                "name": normalize_ws(m.group("name")),
                "date": normalize_ws(m.group("date")),
            }
        )
    return reviews


def fallback_parse_reviews_from_dom_text(raw_text: str) -> List[Dict[str, str]]:
    text = (raw_text or "").replace("\r", "")
    chunks = re.split(r"\n(?=.*?\nRating\s*\n\d+%)", text)
    reviews = []
    for chunk in chunks:
        if "Review by " not in chunk or "Rating" not in chunk:
            continue
        lines = [line.strip() for line in chunk.split("\n") if line.strip()]
        try:
            rating_idx = lines.index("Rating")
        except ValueError:
            continue
        if rating_idx < 1 or rating_idx + 1 >= len(lines):
            continue
        title = normalize_ws(" ".join(lines[:rating_idx]))
        rating = normalize_ws(lines[rating_idx + 1].replace("%", ""))
        name = ""
        date = ""
        body_parts = []
        i = rating_idx + 2
        while i < len(lines):
            line = lines[i]
            if line.startswith("Review by "):
                name = normalize_ws(line.replace("Review by ", "", 1))
                if i + 1 < len(lines) and lines[i + 1].startswith("Posted on "):
                    date = normalize_ws(lines[i + 1].replace("Posted on ", "", 1))
                break
            body_parts.append(line)
            i += 1
        if title and name:
            reviews.append(
                {
                    "title": title,
                    "rating": rating,
                    "body": normalize_ws(" ".join(body_parts)),
                    "name": name,
                    "date": date,
                }
            )
    return reviews


def parse_reviews(raw_text: str) -> List[Dict[str, str]]:
    reviews = parse_reviews_from_text(raw_text)
    if reviews:
        return reviews
    return fallback_parse_reviews_from_dom_text(raw_text)


def review_mentions_customer_service_complaint(review: Dict[str, str], extra_keywords: Optional[List[str]] = None) -> bool:
    body = (review.get("body") or "").lower()
    title = (review.get("title") or "").lower()
    text = f"{title} {body}"

    service_terms = [
        "customer service",
        "customer support",
        "technical support",
        "support phone",
        "support line",
        "service department",
        "service rep",
        "service representative",
        "person on the phone",
        "called support",
        "called customer service",
        "called customer support",
    ]
    if extra_keywords:
        service_terms.extend([k.lower() for k in extra_keywords])

    complaint_terms = [
        "poor",
        "bad",
        "terrible",
        "awful",
        "lousy",
        "horrible",
        "useless",
        "no help",
        "not helpful",
        "rude",
        "harder to understand",
        "broken english",
        "insulted",
        "angered",
        "laughable",
        "told there was no way",
        "avoid",
        "problem",
        "complaint",
        "couldn't help",
        "didn't help",
    ]

    has_service_reference = any(term in text for term in service_terms)
    has_complaint_context = any(term in text for term in complaint_terms)

    return has_service_reference and (has_complaint_context or "customer service" in text or "customer support" in text)


def extract_reviewer_names_with_service_complaints(
    reviews: List[Dict[str, str]], extra_keywords: Optional[List[str]] = None
) -> List[str]:
    names: List[str] = []
    for review in reviews:
        if review_mentions_customer_service_complaint(review, extra_keywords=extra_keywords):
            name = normalize_ws(review.get("name", ""))
            if name and name not in names:
                names.append(name)
    return names


def validate_output_schema(taskspec: Dict, data) -> None:
    schema = taskspec.get("output_schema", {})
    if schema.get("type") != "array":
        raise ValueError("Only array output_schema is supported by this skill.")
    if not isinstance(data, list):
        raise ValueError("retrieved_data must be a list.")
    item_type = schema.get("items", {}).get("type")
    if item_type == "string" and not all(isinstance(x, str) for x in data):
        raise ValueError("retrieved_data items must all be strings.")


async def run() -> None:
    taskspec_path = sys.argv[1]
    taskspec = load_taskspec(taskspec_path)
    params = taskspec.get("params", {}) or {}
    start_url = taskspec.get("start_url")

    if not start_url:
        raise ValueError("taskspec.start_url is required")

    log = Logger(WORKSPACE / "skill_log.txt")
    screenshots_dir = WORKSPACE / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 1800})
        page = await context.new_page()

        try:
            log.log(f"Opening page: {start_url}")
            await open_page(page, start_url)
            await save_screenshot(page, screenshots_dir / "01_initial_page.png")

            await reveal_reviews_section(page, log)
            await save_screenshot(page, screenshots_dir / "02_reviews_section.png")

            try:
                await page.wait_for_load_state("networkidle", timeout=3000)
            except PlaywrightTimeoutError:
                pass

            body_text = await collect_all_review_text(page, log)
            (WORKSPACE / "page_body.txt").write_text(body_text, encoding="utf-8")

            reviews = parse_reviews(body_text)
            log.log(f"Parsed reviews: {len(reviews)}")

            if not reviews:
                await save_screenshot(page, screenshots_dir / "03_no_reviews_parsed.png")

            names = extract_reviewer_names_with_service_complaints(
                reviews,
                extra_keywords=params.get("service_keywords"),
            )

            validate_output_schema(taskspec, names)
            write_response(names, status="SUCCESS", error_details=None)
            await save_screenshot(page, screenshots_dir / "04_done.png")

        except Exception as e:
            write_response(None, status="ERROR", error_details=f"{type(e).__name__}: {e}")
            await save_screenshot(page, screenshots_dir / "error.png")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
