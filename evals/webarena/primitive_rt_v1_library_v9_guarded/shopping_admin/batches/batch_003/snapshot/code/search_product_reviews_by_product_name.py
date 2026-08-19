async def search_product_reviews_by_product_name(self, product_name: str) -> dict:
    base = "http://gcrsandbox410.redmond.corp.microsoft.com:7780"
    page = self.page

    async def _ensure_logged_in() -> None:
        await page.goto(f"{base}/admin", wait_until="domcontentloaded")
        body = (await page.locator("body").inner_text()).lower()
        if "sign in" in body or "welcome, please sign in" in body or "username" in body:
            await page.locator('input[name="login[username]"], input[type="text"]').first.fill("admin")
            await page.locator('input[name="login[password]"], input[type="password"]').first.fill("admin1234")
            await page.locator('button.action-login, button[type="submit"]').first.click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2500)

    await _ensure_logged_in()
    await page.goto(f"{base}/admin/review/product/", wait_until="domcontentloaded")
    await page.wait_for_timeout(1500)

    await page.locator("#reviewGrid_filter_name").fill(product_name)
    await page.get_by_role("button", name="Search").click()
    await page.wait_for_timeout(2500)

    rows = page.locator("#reviewGrid_table tbody tr")
    row_count = await rows.count()
    records = []

    for idx in range(row_count):
        row = rows.nth(idx)
        cells = row.locator("td")
        cell_count = await cells.count()
        cell_texts = []
        for cell_idx in range(cell_count):
            cell_texts.append((await cells.nth(cell_idx).inner_text()).strip())

        edit_link = row.locator('a').filter(has_text='Edit').first
        detail_url = None
        if await edit_link.count() > 0:
            href = await edit_link.get_attribute("href")
            if href:
                detail_url = href if href.startswith("http") else base + href

        product_name_value = None
        if cell_count > 0:
            product_name_value = cell_texts[0] or None

        records.append({
            "product_name": product_name_value,
            "detail_url": detail_url,
            "cells": cell_texts,
        })

    return {
        "records": records,
        "source_page": page.url,
    }
