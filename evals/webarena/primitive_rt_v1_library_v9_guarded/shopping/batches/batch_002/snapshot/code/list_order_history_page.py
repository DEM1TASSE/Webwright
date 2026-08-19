def list_order_history_page(self, base_url):
    import re
    import html as html_lib

    response = self.page.goto(
        f"{base_url.rstrip('/')}/sales/order/history/",
        wait_until="domcontentloaded",
    )
    if response is None:
        raise ValueError("Order history navigation produced no response")
    if response.status >= 400:
        raise ValueError(f"Order history page returned HTTP {response.status}")

    content = self.page.content()
    if "My Orders" not in content:
        raise ValueError("Authenticated order-history page indicator 'My Orders' was not found")

    rows = re.findall(
        r'<tr>\s*<td[^>]*class="col id"[^>]*>(.*?)</td>\s*<td[^>]*class="col date"[^>]*>(.*?)</td>.*?<td[^>]*class="col total"[^>]*>.*?<span class="price">(.*?)</span>.*?</td>\s*<td[^>]*class="col status"[^>]*>(.*?)</td>',
        content,
        re.I | re.S,
    )

    def _clean(text):
        return " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", text)).split())

    orders = []
    for order_id, date_text, total_text, status_text in rows:
        record = {
            "order_id": _clean(order_id),
            "date_text": _clean(date_text),
            "total_text": _clean(total_text),
            "status_text": _clean(status_text),
        }
        if not record["order_id"] or not record["date_text"] or not record["total_text"] or not record["status_text"]:
            raise ValueError("Parsed order-history row was missing one or more required displayed fields")
        orders.append(record)

    return {"orders": orders}
