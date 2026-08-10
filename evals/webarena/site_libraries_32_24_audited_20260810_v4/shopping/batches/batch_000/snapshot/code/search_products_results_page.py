async def search_products_results_page(self, query: str) -> dict:
    await self.page.goto('/', wait_until='domcontentloaded')
    await self.page.get_by_placeholder('Search entire store here...').fill(query)
    await self.page.get_by_role('button', name='Search').click()
    await self.page.wait_for_load_state('domcontentloaded')
    await self.page.wait_for_timeout(2500)
    products = await self.page.locator('li.product-item').evaluate_all("""
    els => els.map(el => {
      const name = el.querySelector('.product-item-link')?.textContent?.trim() || '';
      const price = el.querySelector('.price')?.textContent?.trim() || '';
      const href = el.querySelector('.product-item-link')?.getAttribute('href') || '';
      return {name, price, href};
    }).filter(x => x.name)
    """)
    parsed_products = []
    for item in products:
        price_text = (item.get('price') or '').replace('$', '').replace(',', '').strip()
        price_amount = None
        if price_text:
            try:
                price_amount = float(price_text)
            except Exception:
                price_amount = None
        parsed_products.append({
            'name': (item.get('name') or '').strip(),
            'price_amount': price_amount,
            'product_url': item.get('href') or None,
        })
    return {
        'query': query,
        'results_page_url': self.page.url,
        'completeness': 'visible_results_only',
        'products': parsed_products,
    }
