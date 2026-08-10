import re
from typing import Any, Dict, Optional


async def _current_url_matches(page: Any, expected_url_contains: Optional[str]) -> bool:
    if not expected_url_contains:
        return True
    return expected_url_contains in getattr(page, "url", "")


def _css_attr_contains_selector(href_contains: str) -> str:
    safe = href_contains.replace('\\', '\\\\').replace('"', '\\"')
    return f'a[href*=\"{safe}\"]'


async def _click_by_link_name(page: Any, link_name_pattern: str, timeout_ms: int) -> Dict[str, Any]:
    try:
        locator = page.get_by_role("link", name=re.compile(link_name_pattern, re.I)).first
        href = await locator.get_attribute("href", timeout=timeout_ms)
        await locator.click(timeout=timeout_ms)
        return {"clicked": True, "method": "link_name", "href": href, "error": None}
    except Exception as exc:
        return {"clicked": False, "method": "link_name", "href": None, "error": f"{type(exc).__name__}: {exc}"}


async def _click_by_href_contains(page: Any, href_contains: str, timeout_ms: int) -> Dict[str, Any]:
    try:
        locator = page.locator(_css_attr_contains_selector(href_contains)).first
        href = await locator.get_attribute("href", timeout=timeout_ms)
        await locator.click(timeout=timeout_ms)
        return {"clicked": True, "method": "href_contains", "href": href, "error": None}
    except Exception as exc:
        return {"clicked": False, "method": "href_contains", "href": None, "error": f"{type(exc).__name__}: {exc}"}


async def navigate_akc_destination(
    page: Any,
    link_name_pattern: Optional[str] = None,
    href_contains: Optional[str] = None,
    fallback_url: Optional[str] = None,
    expected_url_contains: Optional[str] = None,
    click_timeout_ms: int = 10000,
    settle_timeout_ms: int = 3000,
    goto_timeout_ms: int = 60000,
) -> Dict[str, Any]:
    """Navigate to an AKC destination using the site's own links plus a fallback URL.

    Args:
        page: A Playwright page on an AKC-owned page.
        link_name_pattern: Optional accessible-name regex for a destination link.
        href_contains: Optional substring that should appear in the destination link href.
        fallback_url: Optional official URL to open if clicking does not reach the destination.
        expected_url_contains: Optional substring used to verify arrival.
        click_timeout_ms: Timeout for link-click attempts.
        settle_timeout_ms: Post-click wait time for client-side navigation.
        goto_timeout_ms: Timeout for fallback navigation.

    Returns:
        A dictionary containing the final URL, whether fallback was used, and click diagnostics.
    """
    diagnostics = []

    if link_name_pattern:
        result = await _click_by_link_name(page, link_name_pattern, click_timeout_ms)
        diagnostics.append(result)
        try:
            await page.wait_for_timeout(settle_timeout_ms)
        except Exception:
            pass
        if await _current_url_matches(page, expected_url_contains):
            return {"arrived": True, "used_fallback": False, "final_url": page.url, "diagnostics": diagnostics}

    if href_contains:
        result = await _click_by_href_contains(page, href_contains, click_timeout_ms)
        diagnostics.append(result)
        try:
            await page.wait_for_timeout(settle_timeout_ms)
        except Exception:
            pass
        if await _current_url_matches(page, expected_url_contains):
            return {"arrived": True, "used_fallback": False, "final_url": page.url, "diagnostics": diagnostics}

    if fallback_url:
        await page.goto(fallback_url, wait_until="domcontentloaded", timeout=goto_timeout_ms)
        try:
            await page.wait_for_timeout(settle_timeout_ms)
        except Exception:
            pass
        return {
            "arrived": await _current_url_matches(page, expected_url_contains),
            "used_fallback": True,
            "final_url": page.url,
            "diagnostics": diagnostics,
        }

    return {"arrived": await _current_url_matches(page, expected_url_contains), "used_fallback": False, "final_url": page.url, "diagnostics": diagnostics}
