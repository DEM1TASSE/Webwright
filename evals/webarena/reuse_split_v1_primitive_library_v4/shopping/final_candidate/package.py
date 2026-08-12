"""Generated candidate package; not promoted."""

class ShoppingAuth:

    def __init__(self, page):
        self.page = page

    def login_customer_account(self, username: str, password: str) -> dict:
        import re
        from urllib.parse import urljoin
        base_url = 'http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:7770/'
        login_url = urljoin(base_url, 'customer/account/login/')
        self.page.goto(login_url, wait_until='domcontentloaded')
        html = self.page.content()
        form_match = re.search('<form[^>]*id=["\\\']login-form["\\\'][\\s\\S]*?</form>', html, re.I)
        if not form_match:
            raise ValueError('Login form not found')
        form_html = form_match.group(0)
        form_key_match = re.search('name=["\\\']form_key["\\\'][^>]*value=["\\\']([^"\\\']+)["\\\']', form_html, re.I)
        action_match = re.search('action=["\\\']([^"\\\']+)["\\\']', form_html, re.I)
        if not form_key_match:
            raise ValueError('Magento form_key not found')
        form_key = form_key_match.group(1)
        action_url = urljoin(self.page.url, action_match.group(1) if action_match else 'customer/account/loginPost/')
        self.page.evaluate("\n            async ({actionUrl, formKey, username, password}) => {\n                const params = new URLSearchParams();\n                params.set('form_key', formKey);\n                params.set('login[username]', username);\n                params.set('login[password]', password);\n                params.set('send', '');\n                const response = await fetch(actionUrl, {\n                    method: 'POST',\n                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},\n                    body: params.toString(),\n                    credentials: 'same-origin',\n                    redirect: 'follow'\n                });\n                await response.text();\n            }\n            ", {'actionUrl': action_url, 'formKey': form_key, 'username': username, 'password': password})
        self.page.goto(urljoin(base_url, 'customer/account/'), wait_until='domcontentloaded')
        body_text = self.page.locator('body').inner_text()
        authenticated = '/customer/account/' in self.page.url or 'Sign Out' in body_text or 'My Account' in body_text or ('customer/account/logout' in self.page.content())
        return {'authenticated': bool(authenticated), 'account_url': self.page.url, 'login_form_action': action_url}

class ShoppingCatalog:

    def __init__(self, page):
        self.page = page

    def search_products(self, query: str, page_number: int=1, fetch_all_pages: bool=False) -> dict:
        import re
        import html as html_lib
        from urllib.parse import quote, urljoin

        def _clean(text: str) -> str:
            text = re.sub('<[^>]+>', ' ', text)
            return html_lib.unescape(re.sub('\\s+', ' ', text)).strip()

        def _parse_products(page_html: str, current_url: str) -> list:
            products = []
            for block in re.findall('<li[^>]*class=["\\\'][^"\\\']*product-item[^"\\\']*["\\\'][^>]*>(.*?)</li>', page_html, re.I | re.S):
                name_match = re.search('class=["\\\']product-item-link["\\\'][^>]*>(.*?)</a>', block, re.I | re.S)
                href_match = re.search('class=["\\\']product-item-link["\\\'][^>]*href=["\\\']([^"\\\']+)["\\\']', block, re.I | re.S)
                price_matches = re.findall('\\$\\s*([0-9]+(?:\\.[0-9]{2})?)', block)
                if not name_match or not price_matches:
                    continue
                products.append({'name': _clean(name_match.group(1)), 'product_url': urljoin(current_url, href_match.group(1)) if href_match else None, 'price': float(price_matches[0])})
            return products
        base_url = 'http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:7770'
        first_url = f'{base_url}/catalogsearch/result/?q={quote(query)}'
        self.page.goto(first_url, wait_until='domcontentloaded')
        first_html = self.page.content()
        discovered = {1}
        for p in re.findall('catalogsearch/result/(?:index/)?\\?p=(\\d+)&amp;q=', first_html, re.I):
            discovered.add(int(p))
        fetched = sorted(discovered) if fetch_all_pages else [page_number]
        results = []
        seen = set()
        for current_page_number in fetched:
            current_url = first_url if current_page_number == 1 else f'{base_url}/catalogsearch/result/index/?p={current_page_number}&q={quote(query)}'
            if current_page_number != 1:
                self.page.goto(current_url, wait_until='domcontentloaded')
                page_html = self.page.content()
            else:
                page_html = first_html
            for product in _parse_products(page_html, self.page.url):
                key = (product['name'], product['product_url'], product['price'])
                if key in seen:
                    continue
                seen.add(key)
                results.append(product)
        return {'query': query, 'results': results, 'page_numbers_discovered': sorted(discovered), 'fetched_page_numbers': fetched, 'is_complete': fetch_all_pages and set(fetched) == set(discovered)}

class ShoppingOrders:

    def __init__(self, page):
        self.page = page

    def get_order_detail(self, order_detail_url: str, order_number: str | None=None) -> dict:
        import re
        import html as html_lib
        from datetime import datetime
        from urllib.parse import urljoin

        def _clean(text: str) -> str:
            text = re.sub('<script.*?</script>', ' ', text, flags=re.I | re.S)
            text = re.sub('<style.*?</style>', ' ', text, flags=re.I | re.S)
            text = re.sub('<[^>]+>', ' ', text)
            return html_lib.unescape(re.sub('\\s+', ' ', text)).strip()

        def _normalize_date(raw: str):
            raw = raw.strip()
            for fmt in ('%B %d, %Y', '%b %d, %Y', '%m/%d/%Y', '%m/%d/%y'):
                try:
                    return datetime.strptime(raw, fmt).strftime('%Y-%m-%d')
                except Exception:
                    pass
            return None
        base_url = 'http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:7770/'
        self.page.goto(urljoin(base_url, order_detail_url), wait_until='domcontentloaded')
        html = self.page.content()
        body_text = _clean(html)
        extracted_order_number = None
        order_number_match = re.search('Order\\s*#\\s*([0-9]+)', body_text, re.I)
        if order_number_match:
            extracted_order_number = order_number_match.group(1)
        anchor_order_number = order_number or extracted_order_number
        status = None
        if anchor_order_number:
            anchored_status_match = re.search('Order\\s*#\\s*' + re.escape(anchor_order_number) + '\\s+([A-Za-z ]+?)\\s+Order Date:', body_text, re.I)
            if anchored_status_match:
                status = anchored_status_match.group(1).strip()
        if status is None:
            status_match = re.search('Order Status:\\s*([A-Za-z ]+)', body_text, re.I)
            if status_match:
                status = status_match.group(1).strip()
        order_date_long_match = re.search('Order Date:\\s*([A-Za-z]+\\s+\\d{1,2},\\s+\\d{4})', body_text, re.I)
        order_date_short_match = re.search('\\b(\\d{1,2}/\\d{1,2}/\\d{2})\\b', body_text)
        item_rows = re.findall('<tr[^>]*id=["\\\']order-item-row-[^"\\\']*["\\\'][^>]*>(.*?)</tr>', html, re.I | re.S)
        items = []
        for row_html in item_rows:
            row_text = _clean(row_html)
            prices = re.findall('\\$[\\d,]+\\.\\d{2}', row_text)
            name_match = re.search('^(.*?)(?:\\s+SKU\\b|\\s+Qty\\b|\\s+Price\\b)', row_text, re.I)
            item_name = name_match.group(1).strip() if name_match and name_match.group(1).strip() else None
            items.append({'item_name': item_name, 'item_text': row_text, 'item_price_display': prices[0] if prices else None})
        tfoot_match = re.search('<tfoot[^>]*>(.*?)</tfoot>', html, re.I | re.S)
        footer_text = _clean(tfoot_match.group(1)) if tfoot_match else body_text
        subtotal_match = re.search('Subtotal\\s*(\\$[\\d,]+\\.\\d{2})', footer_text, re.I)
        shipping_match = re.search('Shipping\\s*&\\s*Handling\\s*(\\$[\\d,]+\\.\\d{2})', footer_text, re.I)
        grand_total_match = re.search('Grand Total\\s*(\\$[\\d,]+\\.\\d{2})', footer_text, re.I)
        arrival_date = None
        patterns = ['(?:Arrival|Arrives|Estimated Delivery|Delivery Date|Delivered on|Expected by|Expected delivery)[:\\s]+([A-Za-z]+\\s+\\d{1,2},\\s*\\d{4})', '(?:Arrival|Arrives|Estimated Delivery|Delivery Date|Delivered on|Expected by|Expected delivery)[:\\s]+(\\d{1,2}/\\d{1,2}/\\d{2,4})']
        for pattern in patterns:
            match = re.search(pattern, body_text, re.I)
            if match:
                arrival_date = _normalize_date(match.group(1))
                if arrival_date is not None:
                    break
        return {'order_number': extracted_order_number, 'order_date_display': order_date_short_match.group(1) if order_date_short_match else None, 'order_date_long': order_date_long_match.group(1) if order_date_long_match else None, 'status': status, 'subtotal_display': subtotal_match.group(1) if subtotal_match else None, 'shipping_and_handling_display': shipping_match.group(1) if shipping_match else None, 'grand_total_display': grand_total_match.group(1) if grand_total_match else None, 'arrival_date': arrival_date, 'items': items, 'order_detail_url': self.page.url}

    def list_customer_order_history_page(self, page_number: int=1) -> dict:
        import re
        import html as html_lib
        from urllib.parse import urljoin

        def _clean(text: str) -> str:
            text = re.sub('<script.*?</script>', ' ', text, flags=re.I | re.S)
            text = re.sub('<style.*?</style>', ' ', text, flags=re.I | re.S)
            text = re.sub('<[^>]+>', ' ', text)
            return html_lib.unescape(re.sub('\\s+', ' ', text)).strip()
        base_url = 'http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:7770/'
        path = 'sales/order/history/' if page_number == 1 else f'sales/order/history/?p={page_number}'
        url = urljoin(base_url, path)
        self.page.goto(url, wait_until='domcontentloaded')
        html = self.page.content()
        orders = []
        seen = set()
        for match in re.finditer('<tr[^>]*>(.*?)</tr>', html, re.I | re.S):
            row_html = match.group(1)
            if 'sales/order/view/order_id/' not in row_html:
                continue
            href_match = re.search('href=["\\\']([^"\\\']*sales/order/view/order_id/\\d+/?)["\\\']', row_html, re.I)
            cells = [_clean(cell) for cell in re.findall('<td[^>]*>(.*?)</td>', row_html, re.I | re.S)]
            if not href_match or len(cells) < 4:
                continue
            order_number = cells[0]
            if not order_number or order_number in seen:
                continue
            seen.add(order_number)
            orders.append({'order_number': order_number, 'order_date': cells[1], 'order_total_display': cells[2], 'status': cells[3], 'order_detail_url': urljoin(self.page.url, href_match.group(1))})
        has_next_page = None
        next_patterns = [f"""href=["\\'][^"\\']*sales/order/history/\\?p={page_number + 1}[^"\\']*["\\']""", f"""href=["\\'][^"\\']*sales/order/history/index/\\?p={page_number + 1}[^"\\']*["\\']"""]
        for pattern in next_patterns:
            if re.search(pattern, html, re.I):
                has_next_page = True
                break
        if has_next_page is None:
            pager_present = re.search('sales/order/history/(?:index/)?\\?p=\\d+', html, re.I)
            if pager_present:
                has_next_page = False
        return {'orders': orders, 'page_number': page_number, 'has_next_page': has_next_page, 'is_complete_for_page': True}

class ShoppingReviews:

    def __init__(self, page):
        self.page = page

    def get_product_review_feed_metadata(self, product_url: str) -> dict:
        import re
        import html as html_lib
        from urllib.parse import urljoin
        self.page.goto(product_url, wait_until='domcontentloaded')
        html = self.page.content()
        title_match = re.search('<title>(.*?)</title>', html, re.I | re.S)
        review_url_match = re.search('"productReviewUrl"\\s*:\\s*"(.*?)"', html)
        review_count_match = re.search('<span[^>]*itemprop=["\\\']reviewCount["\\\'][^>]*>(\\d+)</span>', html, re.I)
        review_feed_url = None
        if review_url_match:
            review_feed_url = review_url_match.group(1).encode('utf-8').decode('unicode_escape').replace('\\/', '/')
            review_feed_url = urljoin(self.page.url, review_feed_url)
        product_title = None
        if title_match:
            product_title = html_lib.unescape(re.sub('\\s+', ' ', title_match.group(1))).strip()
        review_count = int(review_count_match.group(1)) if review_count_match else None
        return {'product_url': self.page.url, 'product_title': product_title, 'review_feed_url': review_feed_url, 'review_count': review_count}

    def list_product_reviews(self, product_id: str, page_number: int=1, limit: int=50) -> dict:
        import re
        import html as html_lib
        from urllib.parse import urlencode

        def _clean(text: str) -> str:
            text = re.sub('<[^>]+>', ' ', text)
            return html_lib.unescape(re.sub('\\s+', ' ', text)).strip()
        base_url = 'http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:7770'
        query = {'limit': str(limit)}
        if page_number != 1:
            query['p'] = str(page_number)
        review_url = f'{base_url}/review/product/listAjax/id/{product_id}/?{urlencode(query)}'
        self.page.goto(review_url, wait_until='domcontentloaded')
        html = self.page.content()
        reviews = []
        blocks = re.findall('<li class=["\\\']item review-item["\\\'].*?</li>', html, re.I | re.S)
        for block in blocks:
            title_match = re.search('<div class=["\\\']review-title["\\\'][^>]*>(.*?)</div>', block, re.I | re.S)
            content_match = re.search('<div class=["\\\']review-content["\\\'][^>]*>(.*?)</div>', block, re.I | re.S)
            author_match = re.search('itemprop=["\\\']author["\\\']>\\s*(.*?)</strong>', block, re.I | re.S)
            rating_match = re.search('<div class=["\\\']rating-result["\\\'][^>]*title=["\\\'](\\d+)%["\\\']', block, re.I | re.S)
            rating_percent = int(rating_match.group(1)) if rating_match else None
            reviews.append({'author_name': _clean(author_match.group(1)) if author_match else None, 'review_title': _clean(title_match.group(1)) if title_match else None, 'review_content': _clean(content_match.group(1)) if content_match else None, 'rating_percent': rating_percent, 'stars': int(round(rating_percent / 20.0)) if rating_percent is not None else None})
        return {'product_id': product_id, 'reviews': reviews, 'page_number': page_number, 'limit': limit, 'is_complete_for_page': True}

class ShoppingSite:

    def __init__(self, page):
        self.auth = ShoppingAuth(page)
        self.catalog = ShoppingCatalog(page)
        self.orders = ShoppingOrders(page)
        self.reviews = ShoppingReviews(page)
