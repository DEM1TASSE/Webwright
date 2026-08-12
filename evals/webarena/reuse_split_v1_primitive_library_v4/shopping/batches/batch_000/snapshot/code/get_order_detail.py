def get_order_detail(self, order_detail_url: str) -> dict:
    import re
    import html as html_lib
    from urllib.parse import urljoin

    def _clean(text: str) -> str:
        text = re.sub(r'<script.*?</script>', ' ', text, flags=re.I | re.S)
        text = re.sub(r'<style.*?</style>', ' ', text, flags=re.I | re.S)
        text = re.sub(r'<[^>]+>', ' ', text)
        return html_lib.unescape(re.sub(r'\s+', ' ', text)).strip()

    base_url = "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:7770/"
    self.page.goto(urljoin(base_url, order_detail_url), wait_until="domcontentloaded")
    html = self.page.content()
    body_text = _clean(html)

    order_number_match = re.search(r'Order\s*#\s*([0-9]+)', body_text, re.I)
    order_date_long_match = re.search(r'Order Date:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})', body_text, re.I)
    order_date_short_match = re.search(r'\b(\d{1,2}/\d{1,2}/\d{2})\b', body_text)
    status_match = re.search(r'Order Status:\s*([A-Za-z ]+)', body_text, re.I)

    item_rows = re.findall(r'<tr[^>]*id=["\']order-item-row-[^"\']*["\'][^>]*>(.*?)</tr>', html, re.I | re.S)
    items = []
    for row_html in item_rows:
        row_text = _clean(row_html)
        prices = re.findall(r'\$[\d,]+\.\d{2}', row_text)
        name_match = re.search(r'^(.*?)(?:\s+SKU\b|\s+Qty\b|\s+Price\b)', row_text, re.I)
        item_name = name_match.group(1).strip() if name_match and name_match.group(1).strip() else None
        items.append({
            "item_name": item_name,
            "item_text": row_text,
            "item_price_display": prices[0] if prices else None,
        })

    tfoot_match = re.search(r'<tfoot[^>]*>(.*?)</tfoot>', html, re.I | re.S)
    footer_text = _clean(tfoot_match.group(1)) if tfoot_match else body_text
    subtotal_match = re.search(r'Subtotal\s*(\$[\d,]+\.\d{2})', footer_text, re.I)
    shipping_match = re.search(r'Shipping\s*&\s*Handling\s*(\$[\d,]+\.\d{2})', footer_text, re.I)
    grand_total_match = re.search(r'Grand Total\s*(\$[\d,]+\.\d{2})', footer_text, re.I)

    return {
        "order_number": order_number_match.group(1) if order_number_match else None,
        "order_date_display": order_date_short_match.group(1) if order_date_short_match else None,
        "order_date_long": order_date_long_match.group(1) if order_date_long_match else None,
        "status": status_match.group(1).strip() if status_match else None,
        "subtotal_display": subtotal_match.group(1) if subtotal_match else None,
        "shipping_and_handling_display": shipping_match.group(1) if shipping_match else None,
        "grand_total_display": grand_total_match.group(1) if grand_total_match else None,
        "items": items,
        "order_detail_url": self.page.url,
    }
