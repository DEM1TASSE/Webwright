def get_product_review_details(self, review_url: str) -> dict:
    if not isinstance(review_url, str) or not review_url.strip():
        raise ValueError('review_url must be a non-empty string')

    response = self.page.goto(review_url, wait_until='domcontentloaded')
    self.page.wait_for_timeout(800)

    title = self.page.locator('#title').input_value()
    nickname = self.page.locator('#nickname').input_value()
    review_text = self.page.locator('#detail').input_value()

    product_locator = self.page.locator('div.admin__field:has(label:text("Product"))')
    product = product_locator.inner_text().strip() if product_locator.count() > 0 else ''

    rating = 0
    for i in range(1, 6):
        if self.page.locator(f'#Rating_{i}').is_checked():
            rating = i

    status_id = self.page.locator('#status_id').input_value()

    return {
        'url': self.page.url,
        'http_status': response.status if response else None,
        'product': product,
        'title': title,
        'nickname': nickname,
        'review': review_text,
        'rating': rating,
        'status_id': status_id,
    }
