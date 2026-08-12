async def get_customer_detail_from_admin_url(self, customer_edit_url: str) -> dict:
    import re

    if not customer_edit_url:
        raise ValueError('customer_edit_url is required.')

    await self.page.goto(customer_edit_url, wait_until='domcontentloaded')
    await self.page.wait_for_load_state('networkidle')

    current_url = self.page.url
    body_text = await self.page.locator('body').inner_text()

    email = None
    email_match = re.search(r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', body_text)
    if email_match:
        email = email_match.group(1)

    return {
        'customer_edit_url': current_url,
        'email': email,
    }
