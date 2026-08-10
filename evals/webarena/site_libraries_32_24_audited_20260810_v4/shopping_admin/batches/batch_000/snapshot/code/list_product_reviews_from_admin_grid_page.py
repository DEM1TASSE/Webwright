async def list_product_reviews_from_admin_grid_page(self, product_name: str | None = None) -> dict:
    import re

    await self.page.goto("/admin/review/product/", wait_until="networkidle")
    if product_name is not None:
        name_filter = self.page.locator("#reviewGrid_filter_name")
        await name_filter.fill(product_name)
        await name_filter.press("Enter")
        await self.page.wait_for_load_state("networkidle")

    rows = self.page.locator("tbody tr")
    row_count = await rows.count()
    records = []
    for i in range(row_count):
        row = rows.nth(i)
        cells = row.locator("td")
        cell_count = await cells.count()
        if cell_count < 5:
            continue
        review_id = (await cells.nth(1).inner_text()).strip()
        title = (await cells.nth(4).inner_text()).strip()
        if review_id:
            records.append({
                "review_id": review_id,
                "title": title,
            })

    html = await self.page.content()
    text = re.sub(r"<[^>]+>", " ", html)
    pager_match = re.search(r"of\s+(\d+)\s+Next page", text, re.I)
    total_pages = int(pager_match.group(1)) if pager_match else None

    return {
        "applied_product_name_filter": product_name,
        "records": records,
        "pagination": {
            "total_pages": total_pages,
            "is_paginated": total_pages is not None,
        },
        "completeness": {
            "page_scope": "current_grid_page",
            "is_complete_result_set": False,
        },
    }
