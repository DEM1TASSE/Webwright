def get_recent_dashboard_orders(self) -> dict:
    import re
    from html import unescape

    html = self.page.content()
    match = re.search(r'Last Orders</div>\s*<div class="dashboard-item-content">\s*<table.*?<tbody>(.*?)</tbody>', html, re.S | re.I)
    if not match:
        raise RuntimeError('Could not locate Last Orders table tbody on current page')

    rows_html = match.group(1)
    row_matches = re.findall(
        r'<tr[^>]*title="([^"]+)"[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>',
        rows_html,
        re.S | re.I,
    )

    def clean(x: str) -> str:
        x = re.sub(r'<[^>]+>', ' ', x)
        x = unescape(x)
        x = re.sub(r'\s+', ' ', x).strip()
        return x

    orders = []
    for title_url, customer, items, total in row_matches:
        orders.append({
            'order_view_url': unescape(title_url),
            'customer': clean(customer),
            'items': int(clean(items)),
            'total': clean(total),
        })

    return {
        'orders': orders,
        'page_url': self.page.url,
    }
