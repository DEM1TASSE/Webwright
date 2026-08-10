from typing import Any, Optional

_TAB_URL_HINTS = {
    "ratings & reviews": "ratings",
    "rules & cancellations": "fees",
    "seasons & fees": "seasons",
    "facility information": "info",
    "campsite list": "campsites",
}


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _tab_url_for(current_url: str, tab_name: str) -> Optional[str]:
    hint = _TAB_URL_HINTS.get(_normalize(tab_name))
    if not hint:
        return None
    base = current_url.split("?", 1)[0]
    return f"{base}?tab={hint}"


async def _click_tab_by_role(page: Any, tab_name: str, timeout_ms: int) -> bool:
    labels = [tab_name]
    normalized = _normalize(tab_name)
    if "and" in normalized:
        labels.append(tab_name.replace("and", "&"))
    if "&" in normalized:
        labels.append(tab_name.replace("&", "and"))
    for label in labels:
        try:
            await page.get_by_role("tab", name=label).click(timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False


async def _wait_for_tab_evidence(page: Any, tab_name: str, timeout_ms: int) -> str:
    normalized = _normalize(tab_name)
    evidence_labels = [tab_name]
    if normalized == "ratings & reviews":
        evidence_labels.extend(["Guest Reviews", "Ratings & Reviews"])
    elif normalized == "rules & cancellations":
        evidence_labels.extend(["Reservation Rules", "Cancellations", "Rules & Cancellations"])
    elif normalized == "facility information":
        evidence_labels.extend(["Facility Information"])
    elif normalized == "seasons & fees":
        evidence_labels.extend(["Seasons", "Fees"])

    for label in evidence_labels:
        try:
            locator = page.get_by_text(label, exact=False).first
            await locator.wait_for(timeout=min(timeout_ms, 12000))
            return label
        except Exception:
            continue
    body_text = await page.locator("body").inner_text(timeout=min(timeout_ms, 15000))
    if normalized in _normalize(body_text):
        return tab_name
    raise RuntimeError(f"Opened tab was not verified: {tab_name!r}")


async def open_facility_detail_tab(page: Any, tab_name: str, timeout_ms: int = 30000, use_url_fallback: bool = True) -> dict:
    """Open a named tab on a Recreation.gov facility detail page.

    Args:
        page: Playwright-like page already on a facility/campground page.
        tab_name: Visible tab name, e.g. 'Rules & Cancellations' or 'Ratings & Reviews'.
        timeout_ms: Timeout for interaction and verification.
        use_url_fallback: Whether to navigate directly to a known tab query if clicking fails.

    Returns:
        Runtime-state payload describing the selected tab and verification evidence.
    """
    clicked = await _click_tab_by_role(page, tab_name, min(timeout_ms, 15000))
    if not clicked and use_url_fallback:
        fallback_url = _tab_url_for(page.url, tab_name)
        if fallback_url:
            await page.goto(fallback_url, wait_until="domcontentloaded", timeout=timeout_ms)
        else:
            raise RuntimeError(f"Could not click tab and no fallback URL is known for {tab_name!r}")
    elif not clicked:
        raise RuntimeError(f"Could not click Recreation.gov facility tab {tab_name!r}")

    await page.wait_for_timeout(1000)
    evidence = await _wait_for_tab_evidence(page, tab_name, timeout_ms)
    body_text = await page.locator("body").inner_text(timeout=min(timeout_ms, 15000))
    return {
        "selected_tab": tab_name,
        "page_url": page.url,
        "verification_text": evidence,
        "tab_text_excerpt": body_text[:2000],
    }
