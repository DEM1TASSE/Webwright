import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


# All artifacts go under the caller's workspace (default: cwd) — NEVER next to __file__:
# this file lives in a shared library, and writing here would dirty it for everyone.
ROOT = Path(os.environ.get("WORKSPACE_DIR", Path.cwd())).resolve()
RUN_DIR = ROOT
AGENT_RESPONSE = ROOT / "agent_response.json"
LOG_FILE = RUN_DIR / "final_script_log.txt"
SCREENSHOTS_DIR = RUN_DIR / "screenshots"


def log(msg: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)


async def snap(page, name: str) -> None:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOTS_DIR / f"{name}.png"
    await page.screenshot(path=str(path), full_page=True)
    log(f"screenshot: {path.name}")


def load_taskspec(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_output(answer: List[str]) -> dict:
    return {"retrieved_data": answer}


def write_output(answer: List[str]) -> None:
    payload = format_output(answer)
    AGENT_RESPONSE.write_text(json.dumps(payload), encoding="utf-8")
    log(f"wrote agent_response.json: {json.dumps(payload)}")


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def iso_to_google_date_label(iso_date: str) -> str:
    dt = datetime.strptime(iso_date, "%Y-%m-%d")
    return dt.strftime("%A, %B %d, %Y").replace(" 0", " ")


def extract_price(text: str) -> Optional[str]:
    if not text:
        return None
    patterns = [
        r"From\s+(\d+)\s+US dollars",
        r"\$(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return f"${m.group(1)}"
    return None


def clean_airline_name(name: str) -> str:
    name = normalize_space(name)
    name = re.sub(r"\s+[•·]\s+", " ", name)
    return name


def extract_airline(text: str) -> Optional[str]:
    if not text:
        return None

    patterns = [
        r"flight with ([^.]+)",
        r"(American|Delta|United|JetBlue|Alaska|Southwest|Spirit|Frontier|Hawaiian|Sun Country|Allegiant)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            val = clean_airline_name(m.group(1))
            if val:
                return val
    return None


async def dismiss_popups(page) -> None:
    candidates = [
        page.get_by_role("button", name=re.compile(r"Accept all|I agree|Got it|No thanks|Close", re.I)),
        page.get_by_role("button", name=re.compile(r"Not now", re.I)),
    ]
    for locator in candidates:
        try:
            if await locator.count():
                await locator.first.click(timeout=1500)
                await page.wait_for_timeout(500)
        except Exception:
            pass


async def open_google_flights(page, start_url: Optional[str]) -> None:
    url = start_url or "https://www.google.com/flights"
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    await dismiss_popups(page)
    log(f"opened: {url}")


async def set_one_way(page) -> None:
    combos = [
        page.get_by_role("combobox", name=re.compile(r"ticket type", re.I)),
        page.get_by_role("combobox", name=re.compile(r"Change ticket type", re.I)),
    ]
    for combo in combos:
        try:
            if await combo.count():
                await combo.first.click()
                await page.wait_for_timeout(400)
                await page.get_by_role("option", name=re.compile(r"One way", re.I)).first.click()
                await page.wait_for_timeout(800)
                log("set trip type to one-way")
                return
        except Exception:
            continue
    raise RuntimeError("Failed to set trip type to one-way")


async def fill_airport_combobox(page, field_name: str, code: str, city: str) -> None:
    combo = page.get_by_role("combobox", name=field_name)
    await combo.click()
    await page.wait_for_timeout(400)
    try:
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
    except Exception:
        pass
    await page.keyboard.type(code, delay=50)
    await page.wait_for_timeout(1500)

    option_patterns = [
        re.compile(rf".*\({re.escape(code)}\)", re.I),
        re.compile(rf"{re.escape(city)}.*\({re.escape(code)}\)", re.I),
        re.compile(rf"{re.escape(code)}", re.I),
    ]
    for pat in option_patterns:
        try:
            opt = page.get_by_role("option", name=pat)
            if await opt.count():
                await opt.first.click()
                await page.wait_for_timeout(800)
                log(f"selected {field_name}: {city} ({code})")
                return
        except Exception:
            continue

    generic = page.locator('[role="option"]').filter(has_text=code)
    if await generic.count():
        await generic.first.click()
        await page.wait_for_timeout(800)
        log(f"selected {field_name}: {city} ({code}) via generic option")
        return

    raise RuntimeError(f"Failed to select airport for {field_name}: {city} ({code})")


async def set_route(page, origin_city: str, origin_code: str, destination_city: str, destination_code: str) -> None:
    await fill_airport_combobox(page, "Where from?", origin_code, origin_city)
    await fill_airport_combobox(page, "Where to?", destination_code, destination_city)


async def set_departure_date(page, iso_date: str) -> None:
    label = iso_to_google_date_label(iso_date)
    dep = page.get_by_role("textbox", name=re.compile(r"Departure", re.I))
    await dep.click()
    await page.wait_for_timeout(1000)

    button = page.get_by_role("button", name=re.compile(re.escape(label), re.I))
    if await button.count():
        await button.first.click()
        await page.wait_for_timeout(600)
    else:
        try:
            await page.keyboard.press("Control+A")
        except Exception:
            pass
        try:
            await page.keyboard.type(datetime.strptime(iso_date, "%Y-%m-%d").strftime("%b %d, %Y"), delay=40)
            await page.keyboard.press("Enter")
        except Exception:
            pass
        await page.wait_for_timeout(1000)

    done = page.get_by_role("button", name=re.compile(r"Done", re.I))
    try:
        if await done.count():
            await done.last.click()
            await page.wait_for_timeout(800)
    except Exception:
        pass

    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    await page.wait_for_timeout(1200)
    log(f"set departure date: {iso_date}")


async def submit_search(page) -> None:
    candidates = [
        page.get_by_role("button", name=re.compile(r"^Search$|Search for flights", re.I)),
        page.get_by_role("button", name=re.compile(r"Explore flights from", re.I)),
    ]
    for button in candidates:
        try:
            if await button.count():
                await button.first.click()
                await page.wait_for_timeout(8000)
                log("submitted search")
                return
        except Exception:
            continue
    raise RuntimeError("Failed to submit search")


async def wait_for_results(page) -> None:
    checks = [
        page.get_by_role("heading", name=re.compile(r"Search results", re.I)),
        page.get_by_role("tab", name=re.compile(r"Cheapest", re.I)),
        page.locator('[role="listitem"]'),
    ]
    for chk in checks:
        try:
            await chk.first.wait_for(timeout=20000)
            await page.wait_for_timeout(3000)
            log("results appear loaded")
            return
        except Exception:
            continue
    await page.wait_for_timeout(5000)
    log("proceeded after fallback wait for results")


async def open_cheapest_tab_if_present(page) -> None:
    tab = page.get_by_role("tab", name=re.compile(r"Cheapest", re.I))
    try:
        if await tab.count():
            await tab.first.click()
            await page.wait_for_timeout(2500)
            log("opened Cheapest tab")
    except Exception:
        log("could not open Cheapest tab; continuing")


async def parse_cheapest_from_tab_label(page) -> Optional[Tuple[Optional[str], Optional[str]]]:
    tab = page.get_by_role("tab", name=re.compile(r"Cheapest", re.I))
    if not await tab.count():
        return None
    txt = normalize_space(await tab.first.inner_text())
    price = extract_price(txt)
    if price:
        return (None, price)
    aria = await tab.first.get_attribute("aria-label") or ""
    price = extract_price(aria)
    if price:
        return (None, price)
    return None


async def extract_result_candidates(page, limit: int = 8) -> List[Tuple[Optional[str], Optional[str], str]]:
    candidates: List[Tuple[Optional[str], Optional[str], str]] = []

    items = page.locator('[role="listitem"]')
    count = min(await items.count(), limit)
    for i in range(count):
        try:
            item = items.nth(i)
            text = normalize_space(await item.inner_text())
            aria = ""
            try:
                link = item.get_by_role("link").first
                if await link.count():
                    aria = normalize_space(await link.get_attribute("aria-label") or "")
            except Exception:
                pass
            joined = normalize_space(f"{aria} {text}")
            airline = extract_airline(joined)
            price = extract_price(joined)
            if airline or price:
                candidates.append((airline, price, joined))
        except Exception:
            continue

    if not candidates:
        body = normalize_space(await page.locator("body").inner_text())
        airline = extract_airline(body)
        price = extract_price(body)
        if airline or price:
            candidates.append((airline, price, body[:1000]))

    return candidates


def choose_best_answer(
    tab_hint: Optional[Tuple[Optional[str], Optional[str]]],
    candidates: List[Tuple[Optional[str], Optional[str], str]],
) -> List[str]:
    hinted_price = tab_hint[1] if tab_hint else None

    if hinted_price:
        for airline, price, _ in candidates:
            if airline and price == hinted_price:
                return [airline, price]

    for airline, price, _ in candidates:
        if airline and price:
            return [airline, price]

    if hinted_price:
        return ["", hinted_price]

    return ["", ""]


def validate_answer(answer: List[str]) -> None:
    if not isinstance(answer, list) or len(answer) != 2 or not all(isinstance(x, str) for x in answer):
        raise RuntimeError("Answer does not match required output schema")
    if not answer[0] or not answer[1]:
        raise RuntimeError(f"Failed to extract complete cheapest flight answer: {answer}")


async def retrieve_cheapest_flight(page, params: dict) -> List[str]:
    await open_google_flights(page, params.get("start_url"))
    await snap(page, "01_home")

    await set_one_way(page)
    await snap(page, "02_one_way")

    await set_route(
        page,
        params["origin_city"],
        params["origin_code"],
        params["destination_city"],
        params["destination_code"],
    )
    await snap(page, "03_route")

    await set_departure_date(page, params["date"])
    await snap(page, "04_date")

    await submit_search(page)
    await wait_for_results(page)
    await snap(page, "05_results")

    tab_hint_before = await parse_cheapest_from_tab_label(page)
    await open_cheapest_tab_if_present(page)
    tab_hint_after = await parse_cheapest_from_tab_label(page)
    await snap(page, "06_cheapest_tab")

    candidates = await extract_result_candidates(page, limit=10)
    for idx, (airline, price, raw) in enumerate(candidates[:5], 1):
        log(f"candidate_{idx}: airline={airline!r}, price={price!r}, raw={raw[:300]!r}")

    answer = choose_best_answer(tab_hint_after or tab_hint_before, candidates)
    log(f"chosen answer: {json.dumps(answer)}")
    return answer


async def main() -> None:
    LOG_FILE.write_text("", encoding="utf-8")
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    taskspec_path = sys.argv[1]
    taskspec = load_taskspec(taskspec_path)
    params = dict(taskspec.get("params", {}))
    params["start_url"] = taskspec.get("start_url", "https://www.google.com/flights")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 1800}, locale="en-US")
        page = await context.new_page()

        try:
            answer = await retrieve_cheapest_flight(page, params)
            validate_answer(answer)
            write_output(answer)
        except PlaywrightTimeoutError as e:
            log(f"timeout error: {e}")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
