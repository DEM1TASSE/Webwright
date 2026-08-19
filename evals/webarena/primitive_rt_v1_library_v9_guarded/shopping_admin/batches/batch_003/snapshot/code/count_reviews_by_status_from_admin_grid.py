async def count_reviews_by_status_from_admin_grid(self, status_label: str) -> dict:
    import re

    base = "http://gcrsandbox410.redmond.corp.microsoft.com:7780"
    page = self.page

    async def _ensure_logged_in() -> None:
        await page.goto(f"{base}/admin", wait_until="domcontentloaded")
        body_text = (await page.locator("body").inner_text()).lower()
        if "welcome, please sign in" in body_text or "username" in body_text or "sign in" in body_text:
            await page.locator('input[name="login[username]"], input[type="text"]').first.fill("admin")
            await page.locator('input[name="login[password]"], input[type="password"]').first.fill("admin1234")
            await page.locator('button.action-login, button[type="submit"]').first.click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2000)

    await _ensure_logged_in()
    await page.goto(f"{base}/admin/review/product/index/", wait_until="domcontentloaded")
    await page.wait_for_timeout(1200)

    rows = page.locator("table.data-grid tr")
    if await rows.count() < 2:
        raise RuntimeError("Reviews grid filter row not available")

    filter_row = rows.nth(1)
    status_select = filter_row.locator("select").nth(1)
    if await status_select.count() == 0:
        raise RuntimeError("Status filter control not available")

    await status_select.select_option(label=status_label)
    await page.get_by_role("button", name="Search").click()
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(2000)

    text = await page.locator("body").inner_text()
    match = re.search(r"(\d+)\s+records found", text)
    if not match:
        raise RuntimeError("Could not find filtered records count")

    return {
        "status_label": status_label,
        "count": int(match.group(1)),
        "source_page": page.url,
    }
