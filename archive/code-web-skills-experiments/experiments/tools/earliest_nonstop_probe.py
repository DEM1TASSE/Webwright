"""Model-free probe: earliest nonstop flight (flight_number, airline, departure_time).

Ground-truth generator / cross-checker for the earliest-nonstop task family.
Schedule data is stable within an airline season and client-independent, so this
probe's output is directly comparable across machines and days — unlike prices.

Usage:
    python earliest_nonstop_probe.py SEA ORD 2026-08-15 [more triples...]
"""
import asyncio
import re
import sys

from playwright.async_api import async_playwright


def _minutes(h: str, m: str, ampm: str) -> int:
    v = (int(h) % 12) * 60 + int(m)
    return v + (12 * 60 if ampm.upper().startswith("P") else 0)


async def probe(pw, origin: str, dest: str, date: str) -> str:
    q = f"Nonstop flights from {origin} to {dest} on {date} one way"
    url = "https://www.google.com/travel/flights?q=" + q.replace(" ", "%20")
    browser = await pw.chromium.launch(headless=True)
    page = await browser.new_page()
    try:
        await page.goto(url, timeout=45000)
        await page.get_by_role("tab", name=re.compile(r"Cheapest", re.I)).first.wait_for(timeout=30000)
        await page.wait_for_timeout(4000)

        links = page.get_by_role("link", name=re.compile(r"Select flight|US dollars", re.I))
        best = None  # (minutes, link_index, airline, time_str)
        for i in range(min(await links.count(), 60)):
            aria = await links.nth(i).get_attribute("aria-label") or ""
            m = re.search(r"Nonstop flight with ([^.]+)\..*?at (\d{1,2}):(\d{2})\s*([AP]M)", aria)
            if not m:
                continue
            key = _minutes(m.group(2), m.group(3), m.group(4))
            if best is None or key < best[0]:
                best = (key, i, m.group(1).strip(), f"{m.group(2)}:{m.group(3)} {m.group(4)}")
        if best is None:
            return f"{origin}->{dest} {date}  (no nonstop found)"

        _, idx, airline, dep = best
        row = links.nth(idx).locator("xpath=ancestor::li[1]")
        flight_no = "?"
        try:
            await row.locator("button[aria-expanded]").first.click()
            await page.wait_for_timeout(2500)
            txt = await row.inner_text()
            # carrier codes can be alphanumeric (JetBlue = B6) and render glued to the
            # aircraft name ("A320B6 434"), so no leading \b; the code-number space is
            # what actually delimits a flight number in this text
            fm = re.search(r"([A-Z][A-Z0-9])\s(\d{2,4})\b", txt.replace("\n", " "))
            if fm:
                flight_no = f"{fm.group(1)} {fm.group(2)}"
        except Exception as e:
            flight_no = f"(expand failed: {type(e).__name__})"
        return f"{origin}->{dest} {date}  [{flight_no}, {airline}, {dep}]"
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
