async def list_customer_orders(self, username: str, password: str) -> dict:
    await self.page.goto('/customer/account/login/', wait_until='domcontentloaded')
    await self.page.locator('input[name="login[username]"]').fill(username)
    await self.page.locator('input[name="login[password]"]').fill(password)
    await self.page.get_by_role('button', name='Sign In').click()
    await self.page.wait_for_load_state('domcontentloaded')
    await self.page.get_by_role('link', name='My Orders').click()
    await self.page.wait_for_load_state('domcontentloaded')
    rows = await self.page.locator('table tbody tr').all()
    orders = []
    for row in rows:
        row_text = (await row.inner_text()).strip()
        detail_href = await row.get_by_role('link', name='View Order').get_attribute('href')
        orders.append({
            'order_number': self._extract_order_number_from_orders_row(row_text),
            'order_date_text': self._extract_short_date_from_orders_row(row_text),
            'status': self._extract_status_from_orders_row(row_text),
            'detail_url': await self._resolve_url(detail_href),
        })
    return {
        'orders_page_url': self.page.url,
        'completeness': 'visible_results_only',
        'orders': orders,
    }

def _extract_order_number_from_orders_row(self, row_text: str) -> str:
    import re
    match = re.search(r'\b(\d{9})\b', row_text)
    return match.group(1) if match else ''

def _extract_short_date_from_orders_row(self, row_text: str) -> str:
    import re
    match = re.search(r'\b\d{1,2}/\d{1,2}/\d{2}\b', row_text)
    return match.group(0) if match else ''

def _extract_status_from_orders_row(self, row_text: str) -> str:
    known_statuses = ['Pending', 'Processing', 'Complete', 'Closed', 'Canceled', 'Cancelled', 'Holded']
    for status in known_statuses:
        if status in row_text:
            return status
    return ''

async def _resolve_url(self, href: str | None) -> str | None:
    if not href:
        return None
    return await self.page.evaluate("""([base, href]) => new URL(href, base).toString()""", [self.page.url, href])
