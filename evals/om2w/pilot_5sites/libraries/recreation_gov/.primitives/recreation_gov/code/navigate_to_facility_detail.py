from typing import Any, Optional
from urllib.parse import quote_plus, urljoin

BASE_URL = "https://www.recreation.gov/"


async def _first_visible(locator: Any, timeout_ms: int = 1500) -> Optional[Any]:
    count = await locator.count()
    for index in range(count):
        item = locator.nth(index)
        try:
            if await item.is_visible(timeout=timeout_ms):
                return item
        except Exception:
            continue
    return None


async def _fill_search_box(page: Any, query: str) -> bool:
    candidates = [
        page.get_by_role("combobox", name="Search Recreation.gov"),
        page.locator("input#navbar-search-input"),
        page.locator("input#hero-search-input"),
        page.locator("input[placeholder*='Search']"),
    ]
    for locator in candidates:
        try:
            target = await _first_visible(locator, timeout_ms=2000)
            if target is None:
                continue
            await target.click(timeout=10000)
            try:
                await target.fill(query, timeout=10000)
            except Exception:
                await page.keyboard.press("Control+A")
                await page.keyboard.type(query)
            return True
        except Exception:
            continue
    return False


async def _click_autosuggest_match(page: Any, query: str, expected_text: Optional[str], timeout_ms: int) -> bool:
    try:
        await page.wait_for_timeout(1200)
        options = page.locator('[role="option"]')
        if await options.count() == 0:
            return False
        match_text = expected_text or query
        option = options.filter(has_text=match_text).first
        if await option.count() == 0:
            option = options.filter(has_text=query).first
        await option.click(timeout=timeout_ms)
        return True
    except Exception:
        return False


async def _open_search_result(page: Any, query: str, expected_text: Optional[str], facility_url_fragment: Optional[str], timeout_ms: int) -> None:
    search_url = BASE_URL + "search?q=" + quote_plus(query)
    await page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)
    await page.wait_for_timeout(1500)
    if facility_url_fragment:
        link = page.locator(f'a[href*="{facility_url_fragment}"]').first
        href = await link.get_attribute("href", timeout=timeout_ms)
    else:
        link_text = expected_text or query
        link = page.get_by_role("link", name=link_text).first
        href = await link.get_attribute("href", timeout=timeout_ms)
    if not href:
        raise RuntimeError(f"Could not find Recreation.gov facility result for {query!r}")
    await page.goto(urljoin(BASE_URL, href), wait_until="domcontentloaded", timeout=timeout_ms)


async def navigate_to_facility_detail(page: Any, query: str, expected_text: Optional[str] = None, facility_url_fragment: Optional[str] = None, start_url: str = BASE_URL, timeout_ms: int = 60000) -> dict:
    """Navigate to a Recreation.gov facility/campground detail page.

    Args:
        page: Playwright-like page object.
        query: Place or facility name to search for.
        expected_text: Optional text expected in the desired autosuggest/result.
        facility_url_fragment: Optional known URL fragment such as '/camping/campgrounds/234046'.
        start_url: Recreation.gov start URL.
        timeout_ms: Navigation and selector timeout.

    Returns:
        Runtime-state payload with final URL, title, and visible identity checks.
    """
    await page.goto(start_url, wait_until="domcontentloaded", timeout=timeout_ms)
    await page.wait_for_timeout(1000)

    used_autosuggest = False
    if await _fill_search_box(page, query):
        used_autosuggest = await _click_autosuggest_match(page, query, expected_text, min(timeout_ms, 15000))
        if used_autosuggest:
            if facility_url_fragment:
                await page.wait_for_url(lambda url: facility_url_fragment in url, timeout=timeout_ms)
            else:
                await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        else:
            await page.keyboard.press("Enter")
            await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)

    if facility_url_fragment and facility_url_fragment not in page.url:
        await _open_search_result(page, query, expected_text, facility_url_fragment, timeout_ms)
    elif "/search" in page.url:
        await _open_search_result(page, query, expected_text, facility_url_fragment, timeout_ms)

    await page.wait_for_timeout(1500)
    body_text = await page.locator("body").inner_text(timeout=min(timeout_ms, 20000))
    title = await page.title()
    checks = {
        "query_visible": query.lower() in body_text.lower() or query.lower() in title.lower(),
        "expected_text_visible": True if not expected_text else expected_text.lower() in body_text.lower() or expected_text.lower() in title.lower(),
        "url_fragment_matched": True if not facility_url_fragment else facility_url_fragment in page.url,
    }
    return {
        "facility_page_url": page.url,
        "facility_page_title": title,
        "used_autosuggest": used_autosuggest,
        "identity_checks": checks,
    }
