async def get_order_detail_items(self, order_url: str) -> dict:
    import re
    from urllib.parse import urljoin

    if not order_url:
        raise ValueError('order_url is required')

    await self.page.goto(order_url, wait_until='domcontentloaded')
    await self.page.wait_for_load_state('networkidle')

    def _strip_tags(text: str) -> str:
        text = re.sub(r'<br\s*/?>', ' ', text, flags=re.I)
        text = re.sub(r'<.*?>', ' ', text, flags=re.S)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        return ' '.join(text.split())

    html = await self.page.content()

    title_match = re.search(r'<title>(.*?)</title>', html, re.S | re.I)
    order_title = _strip_tags(title_match.group(1)) if title_match else None

    date_match = re.search(r'Order Date</th>\s*<td[^>]*>\s*(.*?)\s*</td>', html, re.S | re.I)
    order_date = _strip_tags(date_match.group(1)) if date_match else None

    status_match = re.search(r'Order Status</th>\s*<td[^>]*>\s*(.*?)\s*</td>', html, re.S | re.I)
    order_status = _strip_tags(status_match.group(1)) if status_match else None

    items = []
    for block in re.findall(r'<tbody[^>]*>(.*?)</tbody>', html, re.S | re.I):
        if 'id="order_item_' not in block:
            continue
        name_match = re.search(r'<div[^>]*class="product-title"[^>]*>(.*?)</div>', block, re.S | re.I)
        if not name_match:
            continue
        name = _strip_tags(name_match.group(1))
        displayed_money_amounts = re.findall(r'\$\d+[\d,]*\.\d{2}', _strip_tags(block))
        items.append({
            'name': name,
            'displayed_money_amounts': displayed_money_amounts,
        })

    return {
        'order_url': urljoin(self.page.url, self.page.url),
        'order': {
            'title': order_title,
            'order_date': order_date,
            'order_status': order_status,
        },
        'items': items,
    }
