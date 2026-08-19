async def get_customer_order_detail(self, order_id: str) -> dict:
    import re
    from urllib.parse import urlparse

    if not isinstance(order_id, str) or not order_id.strip():
        raise ValueError("order_id must be a non-empty string")

    parsed = urlparse(self.page.url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("self.page.url must contain the shopping site origin before calling this method")
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    detail_url = f"{base_url}/sales/order/view/order_id/{order_id}/"

    response = await self.page.goto(detail_url, wait_until="domcontentloaded")
    await self.page.wait_for_load_state("networkidle")
    main_text = await self.page.locator("main").inner_text()

    order_number_match = re.search(r"Order #\s*(\d+)", main_text)
    status_match = re.search(r"Order #\s*\d+\s*(\w+)", main_text)
    date_match = re.search(r"Order Date:\s*([A-Za-z]+ \d{1,2}, \d{4})", main_text)
    total_match = re.search(r"Grand Total\s*\$(\d+[\d,]*\.\d{2})", main_text)

    item_names = []
    product_cells = await self.page.locator("table tbody tr td.col.name").all_inner_texts()
    if product_cells:
        item_names = [re.sub(r"\s+", " ", t).strip() for t in product_cells]
    else:
        for m in re.finditer(r"Product Name\s*SKU\s*Price\s*Qty\s*Subtotal\s*(.*?)\s+B[0-9A-Z]+", main_text, re.S):
            item_names.append(re.sub(r"\s+", " ", m.group(1)).strip())

    if not (order_number_match and status_match and date_match and total_match):
        return {
            "detail_url": detail_url,
            "document_status": response.status if response else None,
            "record": None,
        }

    return {
        "detail_url": detail_url,
        "document_status": response.status if response else None,
        "record": {
            "order_id": str(order_id),
            "order_number": order_number_match.group(1),
            "status": status_match.group(1),
            "order_date": date_match.group(1),
            "grand_total": float(total_match.group(1).replace(",", "")),
            "currency_symbol": "$",
            "item_names": item_names,
        },
    }
