async def list_customer_orders_history_page(self, page_number: int = 1) -> dict:
    from urllib.parse import urlparse

    if not isinstance(page_number, int) or page_number < 1:
        raise ValueError("page_number must be a positive integer")
    if page_number != 1:
        raise ValueError("Only the demonstrated first orders-history page is supported")

    parsed = urlparse(self.page.url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("self.page.url must contain the shopping site origin before calling this method")
    orders_history_url = f"{parsed.scheme}://{parsed.netloc}/sales/order/history/"

    response = await self.page.goto(orders_history_url, wait_until="domcontentloaded")
    await self.page.wait_for_load_state("networkidle")

    rows = self.page.locator("table tbody tr")
    records = []
    count = await rows.count()
    for i in range(count):
        cells = [c.strip() for c in await rows.nth(i).locator("td").all_inner_texts()]
        if len(cells) >= 4:
            records.append({
                "order_number": cells[0],
                "order_date": cells[1],
                "ship_to": cells[2],
                "order_total_text": cells[3],
                "display_cells": cells,
            })
        elif cells:
            records.append({
                "order_number": cells[0] if len(cells) > 0 else None,
                "order_date": cells[1] if len(cells) > 1 else None,
                "ship_to": cells[2] if len(cells) > 2 else None,
                "order_total_text": cells[3] if len(cells) > 3 else None,
                "display_cells": cells,
            })

    return {
        "orders_history_url": self.page.url,
        "document_status": response.status if response else None,
        "page_number": page_number,
        "records": records,
    }
