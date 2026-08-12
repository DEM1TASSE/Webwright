# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --information ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['information', 'product']
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
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


class RunArtifacts:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        runs_dir = ensure_dir(workspace / "final_runs")
        existing = []
        for p in runs_dir.glob("run_*"):
            try:
                existing.append(int(p.name.split("_")[1]))
            except Exception:
                pass
        run_id = max(existing, default=0) + 1
        self.run_dir = ensure_dir(runs_dir / f"run_{run_id}")
        self.screenshots_dir = ensure_dir(self.run_dir / "screenshots")
        self.log_file = self.run_dir / "final_script_log.txt"
        self.log_file.write_text("", encoding="utf-8")
        self.step = 0

    def log(self, msg: str):
        print(msg)
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")

    async def screenshot(self, page, label: str):
        self.step += 1
        path = self.screenshots_dir / f"final_execution_{self.step}_{label}.png"
        try:
            await page.screenshot(path=str(path), full_page=True)
        except Exception:
            pass
        self.log(f"step {self.step}: {label}")


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def lower_norm(s: str) -> str:
    return normalize_text(s).lower()


def tokenize(s: str):
    return re.findall(r"[a-z0-9]+", lower_norm(s))


def product_matches(candidate: str, requested: str) -> bool:
    c = lower_norm(candidate)
    r = lower_norm(requested)
    if not c or not r:
        return False
    if r in c or c in r:
        return True
    rt = tokenize(requested)
    ct = set(tokenize(candidate))
    if not rt:
        return False
    overlap = sum(1 for t in rt if t in ct)
    return overlap >= max(1, min(2, len(rt)))


def derive_base_url(start_url: str) -> str:
    p = urlparse(start_url)
    return f"{p.scheme}://{p.netloc}"


async def wait_settled(page, ms: int = 1200):
    try:
        await page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    await page.wait_for_timeout(ms)


async def login(page, start_url: str, credentials: dict, artifacts: RunArtifacts):
    username = credentials.get("username") or credentials.get("user") or "admin"
    password = credentials.get("password") or credentials.get("pass") or "admin1234"

    await page.goto(start_url, wait_until="domcontentloaded")
    await wait_settled(page)

    user_locators = [
        page.locator("#username"),
        page.get_by_role("textbox", name=re.compile("username", re.I)),
        page.locator('input[name*="username"]'),
    ]
    pass_locators = [
        page.locator("#login"),
        page.get_by_role("textbox", name=re.compile("password", re.I)),
        page.locator('input[name*="password"]'),
    ]

    user_filled = False
    for loc in user_locators:
        try:
            if await loc.count():
                await loc.first.fill(username)
                user_filled = True
                break
        except Exception:
            pass
    if not user_filled:
        raise RuntimeError("Could not locate username field")

    pass_filled = False
    for loc in pass_locators:
        try:
            if await loc.count():
                await loc.first.fill(password)
                pass_filled = True
                break
        except Exception:
            pass
    if not pass_filled:
        raise RuntimeError("Could not locate password field")

    clicked = False
    for btn in [
        page.get_by_role("button", name=re.compile("sign in", re.I)),
        page.locator('button:has-text("Sign in")'),
        page.locator('input[type="submit"]'),
    ]:
        try:
            if await btn.count():
                await btn.first.click()
                clicked = True
                break
        except Exception:
            pass
    if not clicked:
        raise RuntimeError("Could not click sign in button")

    await wait_settled(page, 2500)
    artifacts.log(f"Logged in to admin; current URL: {page.url}")
    await artifacts.screenshot(page, "logged_in")


async def open_reviews_grid(page, base_url: str, artifacts: RunArtifacts):
    paths = [
        "/admin/review/product/index/",
        "/admin/review/product/",
    ]
    for path in paths:
        try:
            await page.goto(urljoin(base_url, path), wait_until="domcontentloaded")
            await wait_settled(page, 2000)
            body = lower_norm(await page.locator("body").inner_text())
            if "review" in body:
                artifacts.log(f"Opened reviews grid at {page.url}")
                await artifacts.screenshot(page, "reviews_grid")
                return
        except Exception:
            pass
    raise RuntimeError("Failed to open reviews grid")


async def apply_review_product_filter_if_available(page, product: str, artifacts: RunArtifacts):
    selectors = [
        "#reviewGrid_filter_name",
        'input[id*="reviewGrid_filter_name"]',
        'input[name="name"]',
        'input[id*="filter_name"]',
    ]
    for sel in selectors:
        loc = page.locator(sel)
        try:
            if await loc.count() and await loc.first.is_visible():
                await loc.first.fill(product)
                search_btns = [
                    page.get_by_role("button", name=re.compile("^search$", re.I)),
                    page.locator('button:has-text("Search")'),
                    page.locator('span:has-text("Search")'),
                ]
                clicked = False
                for btn in search_btns:
                    try:
                        if await btn.count():
                            await btn.first.click()
                            clicked = True
                            break
                    except Exception:
                        pass
                if not clicked:
                    await page.keyboard.press("Enter")
                await wait_settled(page, 1800)
                artifacts.log(f"Applied review product filter with value: {product}")
                await artifacts.screenshot(page, "reviews_filtered")
                return True
        except Exception:
            pass
    artifacts.log("No usable review filter found; will inspect rows/details directly")
    return False


async def grid_rows_text(page):
    rows = page.locator("tbody tr")
    count = await rows.count()
    out = []
    for i in range(count):
        try:
            txt = normalize_text(await rows.nth(i).inner_text())
            if txt:
                out.append(txt)
        except Exception:
            pass
    return out


async def extract_detail_links_from_current_grid(page, base_url: str):
    rows = page.locator("tbody tr")
    count = await rows.count()
    links = []
    for i in range(count):
        row = rows.nth(i)
        try:
            row_text = normalize_text(await row.inner_text())
        except Exception:
            row_text = ""
        anchors = row.locator('a[href*="/review/product/edit/id/"]')
        a_count = await anchors.count()
        row_links = []
        for j in range(a_count):
            href = await anchors.nth(j).get_attribute("href")
            if href:
                full = urljoin(base_url, href)
                row_links.append({"url": full, "row_text": row_text})
        if row_links:
            links.extend(row_links)
    if not links:
        html = await page.content()
        for m in re.finditer(r'href="([^"]*/admin/review/product/edit/id/\d+/[^"]*)"', html):
            links.append({"url": urljoin(base_url, m.group(1)), "row_text": ""})
    dedup = []
    seen = set()
    for item in links:
        if item["url"] not in seen:
            dedup.append(item)
            seen.add(item["url"])
    return dedup


async def paginate_review_grid_and_collect_links(page, base_url: str, artifacts: RunArtifacts):
    collected = []
    seen_pages = set()
    while True:
        marker = page.url + "||" + normalize_text(await page.locator("body").inner_text())[:500]
        if marker in seen_pages:
            break
        seen_pages.add(marker)

        current = await extract_detail_links_from_current_grid(page, base_url)
        for item in current:
            if item["url"] not in {x["url"] for x in collected}:
                collected.append(item)

        next_candidates = [
            page.get_by_role("link", name=re.compile(r"\bnext\b", re.I)),
            page.locator("a.next"),
            page.locator(".action-next"),
            page.locator('button[title="Next Page"]'),
        ]
        moved = False
        for nxt in next_candidates:
            try:
                if await nxt.count() and await nxt.first.is_visible():
                    cls = lower_norm(await nxt.first.get_attribute("class") or "")
                    aria = lower_norm(await nxt.first.get_attribute("aria-disabled") or "")
                    disabled = lower_norm(await nxt.first.get_attribute("disabled") or "")
                    if "disabled" in cls or aria == "true" or disabled:
                        continue
                    await nxt.first.click()
                    await wait_settled(page, 1500)
                    moved = True
                    break
            except Exception:
                pass
        if not moved:
            break

    artifacts.log(f"Collected {len(collected)} review detail links from grid pagination")
    return collected


async def extract_review_detail(page, detail_url: str, artifacts: RunArtifacts):
    await page.goto(detail_url, wait_until="domcontentloaded")
    await wait_settled(page, 1200)

    async def first_input_value(selectors):
        for sel in selectors:
            loc = page.locator(sel)
            try:
                if await loc.count():
                    return normalize_text(await loc.first.input_value())
            except Exception:
                pass
        return ""

    async def first_text(selectors):
        for sel in selectors:
            loc = page.locator(sel)
            try:
                if await loc.count():
                    txt = normalize_text(await loc.first.inner_text())
                    if txt:
                        return txt
            except Exception:
                pass
        return ""

    nickname = await first_input_value(["#nickname", 'input[name="nickname"]'])
    title = await first_input_value(["#title", 'input[name="title"]'])
    detail = await first_input_value(["#detail", 'textarea[name="detail"]'])
    product_name = await first_text(["#product_name", 'a[href*="/catalog/product/edit/"]'])

    checked_rating = None
    checked = page.locator('input[type="radio"][name^="ratings"]:checked')
    try:
        if await checked.count():
            cid = await checked.first.get_attribute("id")
            checked_rating = {"Rating_1": 1, "Rating_2": 2, "Rating_3": 3, "Rating_4": 4, "Rating_5": 5}.get(cid)
    except Exception:
        pass

    customer_link = None
    customer_anchors = page.locator('a[href*="/admin/customer/index/edit/id/"]')
    try:
        if await customer_anchors.count():
            customer_link = urljoin(page.url, await customer_anchors.first.get_attribute("href"))
    except Exception:
        pass

    body = await page.locator("body").inner_text()
    body_norm = normalize_text(body)
    email_match = re.search(r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', body_norm)
    embedded_email = email_match.group(1) if email_match else None

    review_id_match = re.search(r"/id/(\d+)/", detail_url)
    review_id = int(review_id_match.group(1)) if review_id_match else None

    record = {
        "review_id": review_id,
        "detail_url": detail_url,
        "product": product_name,
        "nickname": nickname,
        "title": title,
        "detail": detail,
        "rating": checked_rating,
        "customer_link": customer_link,
        "embedded_email": embedded_email,
        "body_excerpt": body_norm[:1500],
    }
    artifacts.log("Review detail extracted: " + json.dumps(record, ensure_ascii=False))
    await artifacts.screenshot(page, f"review_{review_id or 'detail'}")
    return record


async def collect_product_reviews(page, base_url: str, product: str, artifacts: RunArtifacts):
    await open_reviews_grid(page, base_url, artifacts)
    await apply_review_product_filter_if_available(page, product, artifacts)
    row_texts = await grid_rows_text(page)
    artifacts.log("Review grid row evidence: " + json.dumps(row_texts[:40], ensure_ascii=False))

    detail_refs = await paginate_review_grid_and_collect_links(page, base_url, artifacts)
    if not detail_refs:
        raise RuntimeError("No review detail links discovered from reviews grid")

    product_reviews = []
    non_product_reviews = []

    for item in detail_refs:
        rec = await extract_review_detail(page, item["url"], artifacts)
        row_text = item.get("row_text", "")
        if product_matches(rec.get("product", ""), product) or product_matches(row_text, product):
            product_reviews.append(rec)
        else:
            non_product_reviews.append(rec)

    if not product_reviews:
        for rec in non_product_reviews:
            combined = " ".join([rec.get("product", ""), rec.get("title", ""), rec.get("detail", ""), rec.get("body_excerpt", "")])
            if product_matches(combined, product):
                product_reviews.append(rec)

    if not product_reviews:
        raise RuntimeError(f"No reviews matched requested product '{product}'")

    artifacts.log(f"Matched {len(product_reviews)} review(s) for product '{product}'")
    return product_reviews


NEGATIVE_PHRASES = [
    "bad", "terrible", "awful", "horrible", "poor", "disappointed", "really disappointed",
    "not happy", "unhappy", "worse", "worst", "defective", "broken", "cheap",
    "won't recommend", "wont recommend", "would not recommend", "not recommend",
    "never again", "hate", "refund", "return", "issue", "problem", "okish",
    "not perfect", "seam", "loose", "tear", "itchy"
]
POSITIVE_PHRASES = [
    "good", "great", "excellent", "love", "perfect", "nice", "amazing",
    "wonderful", "recommend", "quite good"
]


def sentiment_score(review: dict):
    score = 0
    text = lower_norm(" ".join([review.get("title", ""), review.get("detail", "")]))
    rating = review.get("rating")

    if rating is not None:
        score += (6 - rating) * 8

    for p in NEGATIVE_PHRASES:
        if p in text:
            score += 6 if " " in p else 4
    for p in POSITIVE_PHRASES:
        if p in text:
            score -= 4 if " " in p else 2

    score += min(review.get("detail", "").count("!"), 4)
    score += min(len(review.get("detail", "")) // 80, 3)

    if re.search(r"\bbad!?$", text):
        score += 3
    if "won't recommend" in text or "would not recommend" in text:
        score += 5

    return score


def choose_most_unhappy_review(reviews, artifacts: RunArtifacts):
    scored = []
    for r in reviews:
        score = sentiment_score(r)
        scored.append({**r, "sentiment_score": score})

    scored.sort(
        key=lambda r: (
            -r["sentiment_score"],
            r["rating"] if r["rating"] is not None else 99,
            -len(r.get("detail", "")),
            -len(r.get("title", "")),
            r.get("review_id") or 0,
        )
    )
    artifacts.log("Scored candidate reviews: " + json.dumps(scored, ensure_ascii=False))
    return scored[0]


async def extract_customer_name_from_detail_page(page):
    first = ""
    last = ""
    for sel in ['input[name="account[firstname]"]', '#_accountfirstname', '#firstname']:
        loc = page.locator(sel)
        try:
            if await loc.count():
                first = normalize_text(await loc.first.input_value())
                if first:
                    break
        except Exception:
            pass
    for sel in ['input[name="account[lastname]"]', '#_accountlastname', '#lastname']:
        loc = page.locator(sel)
        try:
            if await loc.count():
                last = normalize_text(await loc.first.input_value())
                if last:
                    break
        except Exception:
            pass

    full = normalize_text(f"{first} {last}")
    if full:
        return full
    if first:
        return first

    body = await page.locator("body").inner_text()
    body_n = normalize_text(body)
    m = re.search(r"Customer View\s+([A-Z][a-zA-Z'-]+(?:\s+[A-Z][a-zA-Z'-]+)+)", body_n)
    if m:
        return normalize_text(m.group(1))
    return None


async def extract_customer_email_from_detail_page(page):
    for sel in ['input[name="account[email]"]', '#_accountemail', '#email']:
        loc = page.locator(sel)
        try:
            if await loc.count():
                value = normalize_text(await loc.first.input_value())
                if value and "@" in value:
                    return value
        except Exception:
            pass

    body = await page.locator("body").inner_text()
    m = re.search(r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', body)
    return m.group(1) if m else None


async def open_customer_and_extract(page, customer_link: str, information: str, artifacts: RunArtifacts):
    await page.goto(customer_link, wait_until="domcontentloaded")
    await wait_settled(page, 1200)
    await artifacts.screenshot(page, "customer_detail")

    info = lower_norm(information)
    if info in {"email", "email address"}:
        return await extract_customer_email_from_detail_page(page)
    if info == "name":
        return await extract_customer_name_from_detail_page(page)
    return None


async def search_customer_grid(page, base_url: str, query: str, information: str, artifacts: RunArtifacts):
    await page.goto(urljoin(base_url, "/admin/customer/index/"), wait_until="domcontentloaded")
    await wait_settled(page, 1500)

    search_inputs = [
        'input[placeholder="Search by keyword"]',
        'input[name="keyword"]',
        'input[type="search"]',
    ]
    searched = False
    for sel in search_inputs:
        loc = page.locator(sel)
        try:
            if await loc.count() and await loc.first.is_visible():
                await loc.first.fill(query)
                await page.keyboard.press("Enter")
                await wait_settled(page, 1800)
                searched = True
                break
        except Exception:
            pass

    if not searched:
        artifacts.log("Customer grid search input not found; reading current page directly")
    await artifacts.screenshot(page, "customer_grid")

    body = await page.locator("body").inner_text()
    if lower_norm(information) in {"email", "email address"}:
        emails = re.findall(r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', body)
        if emails:
            return emails[0]
    if lower_norm(information) == "name":
        if query and lower_norm(query) in lower_norm(body):
            return query
    return None


async def retrieve_information_for_review(page, base_url: str, chosen_review: dict, information: str, artifacts: RunArtifacts):
    info = lower_norm(information)

    if info == "name":
        if chosen_review.get("customer_link"):
            val = await open_customer_and_extract(page, chosen_review["customer_link"], information, artifacts)
            if val:
                return val
        if chosen_review.get("nickname"):
            return chosen_review["nickname"]
        raise RuntimeError("Unable to retrieve customer name")

    if info in {"email", "email address"}:
        if chosen_review.get("embedded_email"):
            return chosen_review["embedded_email"]
        if chosen_review.get("customer_link"):
            val = await open_customer_and_extract(page, chosen_review["customer_link"], information, artifacts)
            if val:
                return val

        query_candidates = []
        nickname = normalize_text(chosen_review.get("nickname", ""))
        if nickname:
            query_candidates.extend([nickname, nickname.split()[-1]])
        for q in query_candidates:
            val = await search_customer_grid(page, base_url, q, information, artifacts)
            if val:
                return val
        raise RuntimeError("Unable to retrieve customer email")

    raise RuntimeError(f"Unsupported information type: {information}")


def validate_output_schema(data, output_schema):
    if not isinstance(data, list):
        raise RuntimeError("retrieved_data must be a list")
    if not all(isinstance(x, str) for x in data):
        raise RuntimeError("retrieved_data items must be strings")
    if output_schema:
        if output_schema.get("type") != "array":
            raise RuntimeError("Output schema type mismatch")
        items = output_schema.get("items", {})
        if items.get("type") != "string":
            raise RuntimeError("Output schema items type mismatch")


async def solve_task(taskspec: dict, workspace: Path):
    artifacts = RunArtifacts(workspace)
    response_path = workspace / "agent_response.json"

    params = taskspec.get("params", {}) or {}
    product = (params.get("product") or "").strip()
    information = (params.get("information") or "").strip()
    start_url = (taskspec.get("start_url") or "").strip()
    credentials = taskspec.get("credentials") or {}
    output_schema = taskspec.get("output_schema") or {}

    if not product:
        raise RuntimeError("taskspec.params.product is required")
    if not information:
        raise RuntimeError("taskspec.params.information is required")
    if not start_url:
        raise RuntimeError("taskspec.start_url is required")

    base_url = derive_base_url(start_url)
    artifacts.log(f"Task: get {information} of the customer who is the most unhappy with {product}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 2200})
        page = await context.new_page()
        try:
            await login(page, start_url, credentials, artifacts)
            reviews = await collect_product_reviews(page, base_url, product, artifacts)
            chosen = choose_most_unhappy_review(reviews, artifacts)
            artifacts.log("Chosen most unhappy review: " + json.dumps(chosen, ensure_ascii=False))
            value = await retrieve_information_for_review(page, base_url, chosen, information, artifacts)
            retrieved_data = [value]
            validate_output_schema(retrieved_data, output_schema)

            response = {
                "task_type": "RETRIEVE",
                "status": "SUCCESS",
                "retrieved_data": retrieved_data,
                "error_details": None,
            }
            response_path.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
            artifacts.log("Wrote SUCCESS agent_response.json")
        except Exception as e:
            response = {
                "task_type": "RETRIEVE",
                "status": "ERROR",
                "retrieved_data": [],
                "error_details": str(e),
            }
            response_path.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")
            artifacts.log(f"ERROR: {e}")
            raise
        finally:
            await browser.close()


def main():
    import sys

    workspace = Path(os.environ.get("WORKSPACE_DIR", os.getcwd()))
    ensure_dir(workspace)
    taskspec_path = Path(sys.argv[1])
    taskspec = json.loads(taskspec_path.read_text(encoding="utf-8"))
    asyncio.run(solve_task(taskspec, workspace))


if __name__ == "__main__":
    main()
