def search_product_reviews_by_product_name(self, product_name: str) -> dict:
    if not isinstance(product_name, str) or not product_name.strip():
        raise ValueError('product_name must be a non-empty string')

    self.page.goto('http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin/review/product/index/', wait_until='domcontentloaded')
    self.page.locator('#reviewGrid_filter_name').fill(product_name)
    self.page.get_by_role('button', name='Search').click()
    self.page.wait_for_load_state('domcontentloaded')
    self.page.wait_for_timeout(1500)

    link_locator = self.page.locator('a', has_text='Edit')
    link_count = link_locator.count()
    reviews = []
    for i in range(link_count):
        link = link_locator.nth(i)
        href = link.get_attribute('href')
        text = (link.inner_text() or '').strip()
        if href:
            reviews.append({
                'edit_url': href,
                'link_text': text,
            })

    return {
        'reviews': reviews,
    }
