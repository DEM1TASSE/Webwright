async def extract_contact_phone_numbers_from_contact_page(self, base_url: str, contact_link_name: str = 'Contact Us') -> dict:
    await self.page.goto(base_url.rstrip('/') + '/', wait_until='domcontentloaded')
    await self.page.wait_for_timeout(1500)
    footer_link = self.page.locator('footer').get_by_role('link', name=contact_link_name).first
    await footer_link.scroll_into_view_if_needed()
    await footer_link.click()
    await self.page.wait_for_load_state('domcontentloaded')
    await self.page.wait_for_timeout(1500)
    body_text = await self.page.locator('body').inner_text()
    phone_numbers = self._parse_phone_numbers_from_text(body_text)
    return {
        'contact_page_url': self.page.url,
        'page_title': await self.page.title(),
        'phone_numbers': phone_numbers,
    }

def _parse_phone_numbers_from_text(self, text: str) -> list:
    import re
    phone_regex = re.compile(r'(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})')
    matches = phone_regex.findall(text)
    return [{'raw_number': match} for match in matches]
