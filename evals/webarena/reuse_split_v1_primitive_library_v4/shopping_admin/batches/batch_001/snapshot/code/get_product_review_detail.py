async def get_product_review_detail(self, review_id: int) -> dict:
    import re
    from urllib.parse import urljoin

    if review_id < 1:
        raise ValueError("review_id must be >= 1")

    await self.page.goto(f"/admin/review/product/edit/id/{review_id}/", wait_until="domcontentloaded")
    await self.page.wait_for_load_state("networkidle")

    async def _first_input_value(selectors):
        for selector in selectors:
            locator = self.page.locator(selector)
            if await locator.count():
                try:
                    value = (await locator.first.input_value()).strip()
                    if value:
                        return value
                except Exception:
                    pass
        return None

    async def _first_text(selectors):
        for selector in selectors:
            locator = self.page.locator(selector)
            if await locator.count():
                try:
                    value = (await locator.first.inner_text()).strip()
                    if value:
                        return value
                except Exception:
                    pass
        return None

    review_url = self.page.url
    nickname = await _first_input_value(["#nickname", 'input[name="nickname"]'])
    title = await _first_input_value(["#title", 'input[name="title"]'])
    detail_text = await _first_input_value(["#detail", 'textarea[name="detail"]'])
    product_name = await _first_text(["#product_name", 'a[href*="/catalog/product/edit/id/"]'])

    rating = None
    checked_rating = self.page.locator('input[type="radio"][name^="ratings"]:checked').first
    if await checked_rating.count():
        rating_id = await checked_rating.get_attribute("id")
        if rating_id:
            match = re.search(r"Rating_(\d+)", rating_id)
            if match:
                rating = int(match.group(1))

    customer_edit_url = None
    customer_link = self.page.locator('a[href*="/admin/customer/index/edit/id/"]').first
    if await customer_link.count():
        href = await customer_link.get_attribute("href")
        if href:
            customer_edit_url = urljoin(review_url, href)

    body_text = await self.page.locator("body").inner_text()
    displayed_customer_email = None
    email_match = re.search(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", body_text)
    if email_match:
        displayed_customer_email = email_match.group(1)

    return {
        "review_id": review_id,
        "review_url": review_url,
        "product_name": product_name,
        "nickname": nickname,
        "title": title,
        "detail_text": detail_text,
        "rating": rating,
        "customer_edit_url": customer_edit_url,
        "displayed_customer_email": displayed_customer_email,
    }
