import re
from typing import Any, Dict


async def _try_click(locator: Any, timeout_ms: int) -> bool:
    try:
        await locator.click(timeout=timeout_ms)
        return True
    except Exception:
        return False


async def dismiss_site_overlays(page: Any, timeout_ms: int = 3000) -> Dict[str, bool]:
    """Dismiss common BBB.org overlays on the current page.

    Expects an existing Playwright page-like object. The helper is intentionally
    tolerant: missing, already dismissed, or renamed overlays are reported as
    not clicked rather than raising.
    """
    actions = {
        "accepted_cookie_banner": False,
        "hid_cookie_message": False,
        "closed_cookie_message": False,
    }

    accept_button = page.get_by_role(
        "button",
        name=re.compile(r"^Accept All Cookies$", re.I),
    )
    actions["accepted_cookie_banner"] = await _try_click(accept_button, timeout_ms)

    hide_button = page.get_by_role(
        "button",
        name=re.compile(r"^Hide This Message$", re.I),
    )
    actions["hid_cookie_message"] = await _try_click(hide_button, min(timeout_ms, 2000))

    close_button = page.get_by_role(
        "button",
        name=re.compile(r"^(Close|Dismiss)$", re.I),
    )
    actions["closed_cookie_message"] = await _try_click(close_button, min(timeout_ms, 2000))

    return actions
