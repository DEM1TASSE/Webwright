def get_order_detail_status_and_arrival(self, order_detail_url: str, order_number: str) -> dict:
    import re
    import html as html_lib
    from datetime import datetime
    from urllib.parse import urljoin

    def _clean(text: str) -> str:
        text = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', text, flags=re.I | re.S)
        text = re.sub(r'<[^>]+>', ' ', text)
        return html_lib.unescape(re.sub(r'\s+', ' ', text)).strip()

    def _normalize_date(raw: str):
        raw = raw.strip()
        for fmt in ('%B %d, %Y', '%b %d, %Y', '%m/%d/%Y', '%m/%d/%y'):
            try:
                return datetime.strptime(raw, fmt).strftime('%Y-%m-%d')
            except Exception:
                pass
        return None

    base_url = 'http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:7770/'
    self.page.goto(urljoin(base_url, order_detail_url), wait_until='domcontentloaded')
    detail_text = _clean(self.page.content())

    status_match = re.search(
        r'Order\s+#\s*' + re.escape(order_number) + r'\s+([A-Za-z]+)\s+Order Date:',
        detail_text,
        re.I,
    )
    status = status_match.group(1) if status_match else None

    arrival_date = None
    patterns = [
        r'(?:Arrival|Arrives|Estimated Delivery|Delivery Date|Delivered on|Expected by|Expected delivery)[:\s]+([A-Za-z]+\s+\d{1,2},\s*\d{4})',
        r'(?:Arrival|Arrives|Estimated Delivery|Delivery Date|Delivered on|Expected by|Expected delivery)[:\s]+(\d{1,2}/\d{1,2}/\d{2,4})',
    ]
    for pattern in patterns:
        match = re.search(pattern, detail_text, re.I)
        if match:
            arrival_date = _normalize_date(match.group(1))
            if arrival_date is not None:
                break

    return {
        'order_number': order_number,
        'status': status,
        'arrival_date': arrival_date,
        'order_detail_url': self.page.url,
    }
