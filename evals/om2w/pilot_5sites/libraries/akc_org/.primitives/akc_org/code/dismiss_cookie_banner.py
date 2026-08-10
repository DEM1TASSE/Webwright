import re
from typing import Any, Dict, List


_COOKIE_BUTTON_PATTERNS = [
    r"Accept All Cookies",
    r"ACCEPT ALL COOKIES",
]


async def _click_role_button(page: Any, pattern: str, timeout_ms: int) -> bool:
    try:
        await page.get_by_role("button", name=re.compile(pattern, re.I)).click(timeout=timeout_ms)
        return True
    except Exception:
        return False


async def _click_text_locator(page: Any, text: str, timeout_ms: int) -> bool:
    selectors = [
        f"text=\"{text}\"",
        f"button:has-text(\"{text}\")",
    ]
    for selector in selectors:
        try:
            await page.locator(selector).last.click(timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False


async def dismiss_akc_cookie_banner(page: Any, timeout_ms: int = 2500) -> Dict[str, Any]:
    """Dismiss AKC's cookie banner if it is visible.

    Args:
        page: A Playwright page currently on an AKC-owned page.
        timeout_ms: Maximum wait for each attempted cookie-control click.

    Returns:
        A small status dictionary describing whether a banner control was clicked.
    """
    attempts: List[str] = []
    for pattern in _COOKIE_BUTTON_PATTERNS:
        attempts.append(f"role_button:{pattern}")
        if await _click_role_button(page, pattern, timeout_ms):
            return {"dismissed": True, "method": f"role_button:{pattern}", "attempts": attempts}

    for text in ["ACCEPT ALL COOKIES", "Accept All Cookies"]:
        attempts.append(f"text_locator:{text}")
        if await _click_text_locator(page, text, timeout_ms):
            return {"dismissed": True, "method": f"text_locator:{text}", "attempts": attempts}

    return {"dismissed": False, "method": None, "attempts": attempts}
