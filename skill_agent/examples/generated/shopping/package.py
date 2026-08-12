"""Generated candidate package; not promoted."""

class ShoppingContact:

    def __init__(self, page):
        self.page = page

    def get_contact_page_phone_numbers(self, base_url: str) -> dict:
        import re
        self.page.goto(base_url.rstrip('/') + '/', wait_until='domcontentloaded')
        self.page.wait_for_timeout(1500)
        footer_link = self.page.locator('footer').get_by_role('link', name='Contact Us').first
        footer_link.scroll_into_view_if_needed()
        footer_link.click()
        self.page.wait_for_load_state('domcontentloaded')
        self.page.wait_for_timeout(1500)
        body_text = re.sub('\\s+', ' ', self.page.locator('body').inner_text())
        phone_regex = re.compile('(?:\\+?1[-.\\s]?)?(?:\\(?\\d{3}\\)?[-.\\s]?\\d{3}[-.\\s]?\\d{4})')
        return {'phone_numbers': phone_regex.findall(body_text)}

class ShoppingOrders:

    def __init__(self, page):
        self.page = page

    def get_order_detail_totals(self, order_url: str) -> dict:
        import re
        self.page.goto(order_url, wait_until='domcontentloaded')
        detail_text = self.page.locator('body').inner_text()
        order_match = re.search('Order\\s+#?\\s*(\\d+)', detail_text)
        grand_total_match = re.search('Grand Total\\s*\\$([\\d,]+\\.\\d{2})', detail_text)
        shipping_match = re.search('Shipping\\s*&\\s*Handling\\s*\\$([\\d,]+\\.\\d{2})', detail_text)
        date_match = re.search('([A-Z][a-z]+\\s+\\d{1,2},\\s+\\d{4})', detail_text)
        status_text = 'Canceled' if 'Canceled' in detail_text else None
        return {'order_detail': {'order_number': order_match.group(1) if order_match else None, 'status_text': status_text, 'displayed_date_text': date_match.group(1) if date_match else None, 'shipping_amount': float(shipping_match.group(1).replace(',', '')) if shipping_match else None, 'grand_total': float(grand_total_match.group(1).replace(',', '')) if grand_total_match else None}}

    def list_orders_from_account_orders_page(self, base_url: str, username: str, password: str) -> dict:
        self.page.goto(base_url.rstrip('/') + '/customer/account/login/', wait_until='domcontentloaded')
        self.page.locator('input[name="login[username]"]').fill(username)
        self.page.locator('input[name="login[password]"]').fill(password)
        self.page.get_by_role('button', name='Sign In').click()
        self.page.wait_for_load_state('domcontentloaded')
        self.page.get_by_role('link', name='My Orders').click()
        self.page.wait_for_load_state('domcontentloaded')
        rows = self.page.locator('table tbody tr').all()
        orders = []
        for row in rows:
            row_text = row.inner_text().strip()
            detail_url = row.get_by_role('link', name='View Order').get_attribute('href')
            if detail_url and detail_url.startswith('/'):
                detail_url = base_url.rstrip('/') + detail_url
            order_number = None
            for token in row_text.split():
                if token.isdigit():
                    order_number = token
                    break
            orders.append({'order_number': order_number, 'row_text': row_text, 'detail_url': detail_url})
        return {'orders': orders}

class ShoppingReviews:

    def __init__(self, page):
        self.page = page

    def list_product_reviews_from_current_product_page(self, product_url: str) -> dict:
        import re

        def _normalize(text: str) -> str:
            return re.sub('\\s+', ' ', text).strip()
        self.page.goto(product_url, wait_until='networkidle')
        self.page.locator('#tab-label-reviews, #tab-label-reviews-title').first.click()
        self.page.wait_for_timeout(2500)
        body_text = self.page.locator('body').inner_text().replace('\r', '')
        pattern = re.compile('(?P<title>.+?)\\nRating\\s*\\n(?P<rating>\\d+)%\\s*\\n(?P<body>.*?)\\nReview by (?P<name>.+?)\\n\\nPosted on (?P<date>.+?)(?=\\n\\n.+?\\nRating\\s*\\n\\d+%\\s*\\n|\\Z)', re.S)
        reviews = []
        for match in pattern.finditer(body_text):
            reviews.append({'title': _normalize(match.group('title')), 'rating_percent': int(_normalize(match.group('rating'))), 'body': _normalize(match.group('body')), 'reviewer_name': _normalize(match.group('name')), 'posted_date': _normalize(match.group('date'))})
        return {'reviews': reviews}

class ShoppingSearch:

    def __init__(self, page):
        self.page = page

    def search_products_from_results_page(self, base_url: str, query: str) -> dict:
        self.page.goto(base_url, wait_until='domcontentloaded')
        self.page.wait_for_timeout(1500)
        self.page.get_by_placeholder('Search entire store here...').fill(query)
        self.page.get_by_role('button', name='Search').click()
        self.page.wait_for_load_state('domcontentloaded')
        self.page.wait_for_timeout(2500)
        products = self.page.locator('li.product-item').evaluate_all("\n            els => els.map(el => {\n              const name = el.querySelector('.product-item-link')?.textContent?.trim() || '';\n              const price = el.querySelector('.price')?.textContent?.trim() || '';\n              return {name, price};\n            }).filter(x => x.name)\n            ")
        parsed = []
        for item in products:
            price_text = item['price'].replace('$', '').replace(',', '').strip()
            if not price_text:
                continue
            try:
                price = float(price_text)
            except Exception:
                continue
            parsed.append({'name': item['name'], 'price': price})
        return {'products': parsed}

class ShoppingSite:

    def __init__(self, page):
        self.contact = ShoppingContact(page)
        self.orders = ShoppingOrders(page)
        self.reviews = ShoppingReviews(page)
        self.search = ShoppingSearch(page)
