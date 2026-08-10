"""Generated candidate package; not promoted."""

class ShoppingCatalogSearch:

    def __init__(self, page):
        self.page = page

    async def search_products_results_page(self, query: str) -> dict:
        await self.page.goto('/', wait_until='domcontentloaded')
        await self.page.get_by_placeholder('Search entire store here...').fill(query)
        await self.page.get_by_role('button', name='Search').click()
        await self.page.wait_for_load_state('domcontentloaded')
        await self.page.wait_for_timeout(2500)
        products = await self.page.locator('li.product-item').evaluate_all("\n        els => els.map(el => {\n          const name = el.querySelector('.product-item-link')?.textContent?.trim() || '';\n          const price = el.querySelector('.price')?.textContent?.trim() || '';\n          const href = el.querySelector('.product-item-link')?.getAttribute('href') || '';\n          return {name, price, href};\n        }).filter(x => x.name)\n        ")
        parsed_products = []
        for item in products:
            price_text = (item.get('price') or '').replace('$', '').replace(',', '').strip()
            price_amount = None
            if price_text:
                try:
                    price_amount = float(price_text)
                except Exception:
                    price_amount = None
            parsed_products.append({'name': (item.get('name') or '').strip(), 'price_amount': price_amount, 'product_url': item.get('href') or None})
        return {'query': query, 'results_page_url': self.page.url, 'completeness': 'visible_results_only', 'products': parsed_products}

class ShoppingContact:

    def __init__(self, page):
        self.page = page

    async def extract_contact_phone_numbers_from_contact_page(self, base_url: str, contact_link_name: str='Contact Us') -> dict:
        await self.page.goto(base_url.rstrip('/') + '/', wait_until='domcontentloaded')
        await self.page.wait_for_timeout(1500)
        footer_link = self.page.locator('footer').get_by_role('link', name=contact_link_name).first
        await footer_link.scroll_into_view_if_needed()
        await footer_link.click()
        await self.page.wait_for_load_state('domcontentloaded')
        await self.page.wait_for_timeout(1500)
        body_text = await self.page.locator('body').inner_text()
        phone_numbers = self._extract_contact_phone_numbers_from_contact_page__parse_phone_numbers_from_text(body_text)
        return {'contact_page_url': self.page.url, 'page_title': await self.page.title(), 'phone_numbers': phone_numbers}

    def _extract_contact_phone_numbers_from_contact_page__parse_phone_numbers_from_text(self, text: str) -> list:
        import re
        phone_regex = re.compile('(?:\\+?1[-.\\s]?)?(?:\\(?\\d{3}\\)?[-.\\s]?\\d{3}[-.\\s]?\\d{4})')
        matches = phone_regex.findall(text)
        return [{'raw_number': match} for match in matches]

class ShoppingOrders:

    def __init__(self, page):
        self.page = page

    async def get_customer_order_details(self, detail_url: str) -> dict:
        await self.page.goto(detail_url, wait_until='domcontentloaded')
        detail_text = await self.page.locator('body').inner_text()
        return {'order': {'order_number': self._get_customer_order_details__extract_order_number_from_order_detail(detail_text), 'status': self._get_customer_order_details__extract_order_status_from_order_detail(detail_text), 'order_date_text': self._get_customer_order_details__extract_full_order_date_from_order_detail(detail_text), 'shipping_and_handling_amount': self._get_customer_order_details__extract_shipping_amount_from_order_detail(detail_text), 'grand_total_amount': self._get_customer_order_details__extract_grand_total_from_order_detail(detail_text), 'detail_url': self.page.url}}

    def _get_customer_order_details__extract_order_number_from_order_detail(self, text: str) -> str:
        import re
        match = re.search('\\b(\\d{9})\\b', text)
        return match.group(1) if match else ''

    def _get_customer_order_details__extract_order_status_from_order_detail(self, text: str) -> str:
        known_statuses = ['Pending', 'Processing', 'Complete', 'Closed', 'Canceled', 'Cancelled', 'Holded']
        for status in known_statuses:
            if status in text:
                return status
        return ''

    def _get_customer_order_details__extract_full_order_date_from_order_detail(self, text: str) -> str:
        import re
        match = re.search('([A-Z][a-z]+ \\d{1,2}, \\d{4})', text)
        return match.group(1) if match else ''

    def _get_customer_order_details__extract_shipping_amount_from_order_detail(self, text: str):
        import re
        match = re.search('Shipping\\s*&\\s*Handling\\s*\\$([\\d,]+\\.\\d{2})', text)
        return float(match.group(1).replace(',', '')) if match else None

    def _get_customer_order_details__extract_grand_total_from_order_detail(self, text: str):
        import re
        match = re.search('Grand Total\\s*\\$([\\d,]+\\.\\d{2})', text)
        return float(match.group(1).replace(',', '')) if match else None

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
            orders.append({'order_number': self._list_customer_orders__extract_order_number_from_orders_row(row_text), 'order_date_text': self._list_customer_orders__extract_short_date_from_orders_row(row_text), 'status': self._list_customer_orders__extract_status_from_orders_row(row_text), 'detail_url': await self._list_customer_orders__resolve_url(detail_href)})
        return {'orders_page_url': self.page.url, 'completeness': 'visible_results_only', 'orders': orders}

    def _list_customer_orders__extract_order_number_from_orders_row(self, row_text: str) -> str:
        import re
        match = re.search('\\b(\\d{9})\\b', row_text)
        return match.group(1) if match else ''

    def _list_customer_orders__extract_short_date_from_orders_row(self, row_text: str) -> str:
        import re
        match = re.search('\\b\\d{1,2}/\\d{1,2}/\\d{2}\\b', row_text)
        return match.group(0) if match else ''

    def _list_customer_orders__extract_status_from_orders_row(self, row_text: str) -> str:
        known_statuses = ['Pending', 'Processing', 'Complete', 'Closed', 'Canceled', 'Cancelled', 'Holded']
        for status in known_statuses:
            if status in row_text:
                return status
        return ''

    async def _list_customer_orders__resolve_url(self, href: str | None) -> str | None:
        if not href:
            return None
        return await self.page.evaluate('([base, href]) => new URL(href, base).toString()', [self.page.url, href])

class ShoppingReviews:

    def __init__(self, page):
        self.page = page

    async def extract_product_reviews_from_product_page(self, url: str) -> dict:
        await self.page.goto(url, wait_until='networkidle')
        await self.page.locator('#tab-label-reviews, #tab-label-reviews-title').first.click()
        await self.page.wait_for_timeout(2500)
        body_text = await self.page.locator('body').inner_text()
        reviews = self._extract_product_reviews_from_product_page__parse_product_reviews_from_text(body_text)
        return {'product_url': self.page.url, 'review_source': 'product_reviews_tab_rendered_text', 'reviews': reviews}

    def _extract_product_reviews_from_product_page__normalize_review_text(self, value: str) -> str:
        import re
        return re.sub('\\s+', ' ', value).strip()

    def _extract_product_reviews_from_product_page__parse_product_reviews_from_text(self, raw_text: str) -> list:
        import re
        text = raw_text.replace('\r', '')
        pattern = re.compile('(?P<title>.+?)\\nRating\\s*\\n(?P<rating>\\d+)%\\s*\\n(?P<body>.*?)\\nReview by (?P<name>.+?)\\n\\nPosted on (?P<date>.+?)(?=\\n\\n.+?\\nRating\\s*\\n\\d+%\\s*\\n|\\Z)', re.S)
        reviews = []
        for match in pattern.finditer(text):
            reviews.append({'title': self._extract_product_reviews_from_product_page__normalize_review_text(match.group('title')), 'rating_percent': int(self._extract_product_reviews_from_product_page__normalize_review_text(match.group('rating'))), 'body': self._extract_product_reviews_from_product_page__normalize_review_text(match.group('body')), 'reviewer_name': self._extract_product_reviews_from_product_page__normalize_review_text(match.group('name')), 'posted_date': self._extract_product_reviews_from_product_page__normalize_review_text(match.group('date'))})
        return reviews

class ShoppingSite:

    def __init__(self, page):
        self.catalog_search = ShoppingCatalogSearch(page)
        self.contact = ShoppingContact(page)
        self.orders = ShoppingOrders(page)
        self.reviews = ShoppingReviews(page)
