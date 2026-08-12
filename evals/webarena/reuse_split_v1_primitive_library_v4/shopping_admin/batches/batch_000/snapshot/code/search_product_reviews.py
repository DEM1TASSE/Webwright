async def search_product_reviews(self, detail_query: str | None = None, product_name_query: str | None = None, page_number: int = 1) -> dict:
    import re
    from urllib.parse import urljoin

    if detail_query is None and product_name_query is None:
        raise ValueError("Provide at least one filter: detail_query or product_name_query.")
    if page_number < 1:
        raise ValueError("page_number must be >= 1")

    await self.page.goto('/admin/review/product/index/', wait_until='domcontentloaded')
    await self.page.wait_for_load_state('networkidle')

    if detail_query is not None:
        detail_input = self.page.locator('#reviewGrid_filter_detail')
        if not await detail_input.count():
            raise RuntimeError('Review detail filter input not found.')
        await detail_input.fill(detail_query)

    if product_name_query is not None:
        product_input = self.page.locator('#reviewGrid_filter_name')
        if not await product_input.count():
            raise RuntimeError('Product filter input not found.')
        await product_input.fill(product_name_query)

    await self.page.get_by_role('button', name='Search').click()
    await self.page.wait_for_load_state('networkidle')

    if page_number > 1:
        pager_link = self.page.locator(f'a[href*="page/{page_number}"]').first
        if not await pager_link.count():
            raise RuntimeError(f'Requested page_number {page_number} is not available from the current result set.')
        await pager_link.click()
        await self.page.wait_for_load_state('networkidle')

    body_text = await self.page.locator('body').inner_text()
    total_match = re.search(r'(\d+)\s+records found', body_text)
    reported_total_matches = int(total_match.group(1)) if total_match else None

    table_rows = self.page.locator('#reviewGrid_table tbody tr')
    row_count = await table_rows.count()
    records = []

    for i in range(row_count):
        row = table_rows.nth(i)
        row_text_raw = await row.inner_text()
        row_text = ' | '.join(part.strip() for part in row_text_raw.splitlines() if part.strip())

        edit_url = None
        review_id = None
        edit_link = row.locator('a[href*="/admin/review/product/edit/id/"]').first
        if await edit_link.count():
            href = await edit_link.get_attribute('href')
            if href:
                edit_url = urljoin(self.page.url, href)
                id_match = re.search(r'/admin/review/product/edit/id/(\d+)/', edit_url)
                if id_match:
                    review_id = int(id_match.group(1))

        records.append({
            "review_id": review_id,
            "edit_url": edit_url,
            "row_text": row_text,
        })

    is_complete = False
    if reported_total_matches is not None and reported_total_matches <= len(records) and page_number == 1:
        is_complete = True

    return {
        "detail_query": detail_query,
        "product_name_query": product_name_query,
        "reported_total_matches": reported_total_matches,
        "page_number": page_number,
        "is_complete": is_complete,
        "records": records,
    }
