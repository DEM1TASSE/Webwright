def list_orders_from_admin_orders_grid_page(self, orders_page_url: str, max_rows: int) -> dict:
    import re

    if not isinstance(orders_page_url, str) or not orders_page_url.strip():
        raise ValueError('orders_page_url must be a non-empty string')
    if not isinstance(max_rows, int) or max_rows < 1:
        raise ValueError('max_rows must be an integer >= 1')

    self.page.goto(orders_page_url, wait_until='domcontentloaded')
    self.page.wait_for_timeout(3000)

    rows = self.page.locator('table.data-grid tbody tr')
    row_count = rows.count()
    limit = min(row_count, max_rows)
    orders = []

    for i in range(limit):
        row = rows.nth(i)
        cells = row.locator('td')
        cell_count = cells.count()
        texts = []
        for j in range(cell_count):
            txt = cells.nth(j).inner_text()
            txt = re.sub(r'\s+', ' ', txt).strip()
            texts.append(txt)
        orders.append({
            'row_index': i + 1,
            'order_id': texts[1] if len(texts) > 1 else None,
            'purchase_date': texts[3] if len(texts) > 3 else None,
            'status': texts[8] if len(texts) > 8 else None,
            'cells': texts,
            'row_text': ' | '.join(texts),
        })

    return {
        'orders': orders,
        'page_url': self.page.url,
    }
