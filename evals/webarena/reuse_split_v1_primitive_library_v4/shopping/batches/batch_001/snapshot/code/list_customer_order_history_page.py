def list_customer_order_history_page(self, page_number: int = 1) -> dict:
    import re
    import html as html_lib
    from urllib.parse import urljoin

    def _clean(text: str) -> str:
        text = re.sub(r'<script.*?</script>', ' ', text, flags=re.I | re.S)
        text = re.sub(r'<style.*?</style>', ' ', text, flags=re.I | re.S)
        text = re.sub(r'<[^>]+>', ' ', text)
        return html_lib.unescape(re.sub(r'\s+', ' ', text)).strip()

    base_url = "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:7770/"
    path = "sales/order/history/" if page_number == 1 else f"sales/order/history/?p={page_number}"
    url = urljoin(base_url, path)
    self.page.goto(url, wait_until="domcontentloaded")
    html = self.page.content()

    orders = []
    seen = set()
    for match in re.finditer(r'<tr[^>]*>(.*?)</tr>', html, re.I | re.S):
        row_html = match.group(1)
        if 'sales/order/view/order_id/' not in row_html:
            continue

        href_match = re.search(r'href=["\']([^"\']*sales/order/view/order_id/\d+/?)["\']', row_html, re.I)
        cells = [_clean(cell) for cell in re.findall(r'<td[^>]*>(.*?)</td>', row_html, re.I | re.S)]
        if not href_match or len(cells) < 4:
            continue

        order_number = cells[0]
        if not order_number or order_number in seen:
            continue
        seen.add(order_number)

        orders.append({
            "order_number": order_number,
            "order_date": cells[1],
            "order_total_display": cells[2],
            "status": cells[3],
            "order_detail_url": urljoin(self.page.url, href_match.group(1)),
        })

    has_next_page = None
    next_patterns = [
        rf'href=["\'][^"\']*sales/order/history/\?p={page_number + 1}[^"\']*["\']',
        rf'href=["\'][^"\']*sales/order/history/index/\?p={page_number + 1}[^"\']*["\']',
    ]
    for pattern in next_patterns:
        if re.search(pattern, html, re.I):
            has_next_page = True
            break
    if has_next_page is None:
        pager_present = re.search(r'sales/order/history/(?:index/)?\?p=\d+', html, re.I)
        if pager_present:
            has_next_page = False

    return {
        "orders": orders,
        "page_number": page_number,
        "has_next_page": has_next_page,
        "is_complete_for_page": True,
    }
