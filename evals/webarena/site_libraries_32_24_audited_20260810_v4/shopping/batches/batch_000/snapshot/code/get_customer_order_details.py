async def get_customer_order_details(self, detail_url: str) -> dict:
    await self.page.goto(detail_url, wait_until='domcontentloaded')
    detail_text = await self.page.locator('body').inner_text()
    return {
        'order': {
            'order_number': self._extract_order_number_from_order_detail(detail_text),
            'status': self._extract_order_status_from_order_detail(detail_text),
            'order_date_text': self._extract_full_order_date_from_order_detail(detail_text),
            'shipping_and_handling_amount': self._extract_shipping_amount_from_order_detail(detail_text),
            'grand_total_amount': self._extract_grand_total_from_order_detail(detail_text),
            'detail_url': self.page.url,
        }
    }

def _extract_order_number_from_order_detail(self, text: str) -> str:
    import re
    match = re.search(r'\b(\d{9})\b', text)
    return match.group(1) if match else ''

def _extract_order_status_from_order_detail(self, text: str) -> str:
    known_statuses = ['Pending', 'Processing', 'Complete', 'Closed', 'Canceled', 'Cancelled', 'Holded']
    for status in known_statuses:
        if status in text:
            return status
    return ''

def _extract_full_order_date_from_order_detail(self, text: str) -> str:
    import re
    match = re.search(r'([A-Z][a-z]+ \d{1,2}, \d{4})', text)
    return match.group(1) if match else ''

def _extract_shipping_amount_from_order_detail(self, text: str):
    import re
    match = re.search(r'Shipping\s*&\s*Handling\s*\$([\d,]+\.\d{2})', text)
    return float(match.group(1).replace(',', '')) if match else None

def _extract_grand_total_from_order_detail(self, text: str):
    import re
    match = re.search(r'Grand Total\s*\$([\d,]+\.\d{2})', text)
    return float(match.group(1).replace(',', '')) if match else None
