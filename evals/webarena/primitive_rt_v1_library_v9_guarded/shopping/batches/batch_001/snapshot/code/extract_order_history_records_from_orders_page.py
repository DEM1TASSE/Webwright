def extract_order_history_records_from_orders_page(self, html):
    import re
    from datetime import datetime

    def _strip_tags(text):
        return re.sub(r'<[^>]+>', ' ', text or '')

    row_pattern = re.compile(
        r'<tr>\s*<td[^>]*class="col id"[^>]*>(.*?)</td>\s*<td[^>]*class="col date"[^>]*>(.*?)</td>.*?<td[^>]*class="col total"[^>]*>.*?<span class="price">(.*?)</span>.*?</td>\s*<td[^>]*class="col status"[^>]*>(.*?)</td>',
        re.S,
    )

    orders = []
    for order_id, date_text, total_text, status_text in row_pattern.findall(html or ''):
        oid = re.sub(r'\s+', ' ', _strip_tags(order_id)).strip()
        dtx = re.sub(r'\s+', ' ', _strip_tags(date_text)).strip()
        ttx = re.sub(r'\s+', ' ', _strip_tags(total_text)).strip()
        stx = re.sub(r'\s+', ' ', _strip_tags(status_text)).strip()
        try:
            parsed_date = datetime.strptime(dtx, '%m/%d/%y').date().isoformat()
        except Exception:
            continue
        try:
            amount = float(ttx.replace('$', '').replace(',', ''))
        except Exception:
            continue
        orders.append({
            'order_id': oid,
            'date_text': dtx,
            'date': parsed_date,
            'total_text': ttx,
            'amount': amount,
            'status': stx,
        })

    return {'orders': orders}
