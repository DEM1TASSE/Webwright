async def extract_product_review_texts_from_product_page(self, url: str) -> dict:
    import re

    response = await self.page.goto(url, wait_until="domcontentloaded")
    await self.page.wait_for_load_state("networkidle")

    reviews_tab = self.page.locator("#tab-label-reviews-title")
    if await reviews_tab.count() > 0:
        await reviews_tab.first.click()
        await self.page.wait_for_timeout(1200)

    review_nodes = self.page.locator(".review-content")
    reviews = []
    count = await review_nodes.count()
    for i in range(count):
        text = await review_nodes.nth(i).inner_text()
        reviews.append({"content_text": re.sub(r"\s+", " ", text).strip()})

    return {
        "product_url": self.page.url,
        "document_status": response.status if response else None,
        "reviews": reviews,
    }
