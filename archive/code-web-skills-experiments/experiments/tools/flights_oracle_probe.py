"""Model-free oracle probe for Google Flights.

Reads the Cheapest tab's own label ("Cheapest from $X") — the page's declarative
statement of the true lowest price — without any LLM. Use it to generate golds
or to check how far live prices have drifted from recorded training answers.

Usage:
    python flights_oracle_probe.py "SEA" "JFK" 2026-08-15 [more triples...]

Prints one line per route: ROUTE  declared_cheapest  cheapest_list_top
"""
import asyncio
import re
import sys

from playwright.async_api import async_playwright


async def probe(pw, origin: str, dest: str, date: str) -> str:
    q = f"Flights from {origin} to {dest} on {date} one way"
    url = "https://www.google.com/travel/flights?q=" + q.replace(" ", "%20")
    browser = await pw.chromium.launch(headless=True)
    page = await browser.new_page()
    try:
        await page.goto(url, timeout=45000)
        tab = page.get_by_role("tab", name=re.compile(r"Cheapest", re.I))
        await tab.first.wait_for(timeout=30000)
        # the price fills in only after results finish loading — poll for it
        declared, m = "(price never appeared in tab)", None
        for _ in range(30):
            txt = await tab.first.inner_text()
            aria = await tab.first.get_attribute("aria-label") or ""
            m = re.search(r"from\s+\$?(\d+)", f"{txt} {aria}")
            if m:
                declared = f"${m.group(1)}"
                break
            await page.wait_for_timeout(1000)

        # cross-check: click the tab and read the first result card's aria
        top = "(unread)"
        try:
            await tab.first.click()
            await page.wait_for_timeout(2500)
            item = page.locator('[role="listitem"]').first
            text = await item.inner_text(timeout=8000)
            pm = re.search(r"\$(\d+)", text)
            top = f"${pm.group(1)}" if pm else "(no price in top card)"
        except Exception as e:
            top = f"(top-card read failed: {type(e).__name__})"
        return f"{origin}->{dest} {date}  declared={declared}  list_top={top}"
    finally:
        await browser.close()


async def main() -> None:
    args = sys.argv[1:]
    if len(args) % 3 or not args:
        sys.exit(__doc__)
    async with async_playwright() as pw:
        for i in range(0, len(args), 3):
            print(await probe(pw, args[i], args[i + 1], args[i + 2]), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
