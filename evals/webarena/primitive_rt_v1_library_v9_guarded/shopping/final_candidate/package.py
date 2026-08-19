"""Generated candidate package; not promoted."""

class ShoppingAuth:

    def __init__(self, page):
        self.page = page

    def authenticate_customer_session_via_form_key(self, base_url, email, password):
        import re
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError('base_url must be a non-empty string')
        if not isinstance(email, str) or not email.strip():
            raise ValueError('email must be a non-empty string')
        if not isinstance(password, str) or not password:
            raise ValueError('password must be a non-empty string')
        root = base_url.rstrip('/')
        login_url = root + '/customer/account/login/'
        response = self.page.goto(login_url, wait_until='domcontentloaded')
        if response is None:
            raise ValueError('Login navigation produced no response')
        if response.status >= 400:
            raise ValueError(f'Login page returned HTTP {response.status}')
        login_html = self.page.content()
        form_key_match = re.search('name="form_key" type="hidden" value="([^"]+)"', login_html)
        if not form_key_match:
            raise ValueError('Login form_key was not found on the login page')
        form_key = form_key_match.group(1)
        post_response = self.page.request.post(root + '/customer/account/loginPost/', form={'form_key': form_key, 'login[username]': email, 'login[password]': password}, headers={'Referer': login_url, 'User-Agent': 'Mozilla/5.0'}, fail_on_status_code=False)
        if post_response.status >= 400:
            raise ValueError(f'Login POST returned HTTP {post_response.status}')
        account_url = root + '/customer/account/'
        account_response = self.page.goto(account_url, wait_until='domcontentloaded')
        if account_response is None:
            raise ValueError('Authenticated account navigation produced no response')
        if account_response.status >= 400:
            raise ValueError(f'Account page returned HTTP {account_response.status}')
        account_html = self.page.content()
        if 'Sign Out' not in account_html:
            raise ValueError("Authenticated account indicator 'Sign Out' was not found after login")
        return {'authenticated': True, 'cookie_session_established': True, 'account_url': self.page.url, 'document_status': account_response.status}

class ShoppingCatalog:

    def __init__(self, page):
        self.page = page

    async def multi_search_products_graphql_dedup_by_sku(self, queries: list[str], page_size: int=100) -> dict:
        import json
        from urllib.parse import quote, urlparse
        if not isinstance(queries, list) or not queries:
            raise ValueError('queries must be a non-empty list of strings')
        if not isinstance(page_size, int) or page_size <= 0:
            raise ValueError('page_size must be a positive integer')
        for query in queries:
            if not isinstance(query, str) or not query.strip():
                raise ValueError('each query must be a non-empty string')
        parsed = urlparse(self.page.url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError('self.page.url must contain the shopping site origin before calling this method')
        base_url = f'{parsed.scheme}://{parsed.netloc}'
        merged = {}
        executed_queries = []
        for query in queries:
            graphql_query = '{ products(search:"%s", pageSize:%d) { total_count items { name sku url_key url_suffix price_range { minimum_price { regular_price { value currency } final_price { value currency } } } } } }' % (query.replace('"', '\\"'), page_size)
            graphql_url = base_url + '/graphql?query=' + quote(graphql_query, safe='/:?=&{}"')
            response = await self.page.goto(graphql_url, wait_until='domcontentloaded')
            await self.page.wait_for_load_state('networkidle')
            payload = json.loads(await self.page.locator('body').inner_text())
            products_root = (payload.get('data', {}) or {}).get('products', {}) or {}
            items = products_root.get('items', []) or []
            executed_queries.append({'query': query, 'graphql_url': graphql_url, 'document_status': response.status if response else None, 'total_count': products_root.get('total_count'), 'returned_items_count': len(items)})
            for item in items:
                sku = item.get('sku')
                if not sku:
                    continue
                minimum_price = (item.get('price_range') or {}).get('minimum_price') or {}
                regular_price = minimum_price.get('regular_price') or {}
                final_price = minimum_price.get('final_price') or {}
                url_key = item.get('url_key')
                url_suffix = item.get('url_suffix')
                merged[sku] = {'sku': sku, 'name': item.get('name'), 'url_key': url_key, 'url_suffix': url_suffix, 'product_url': base_url + '/' + url_key + (url_suffix or '') if url_key else None, 'price_range': {'minimum_price': {'regular_price': {'value': regular_price.get('value'), 'currency': regular_price.get('currency')}, 'final_price': {'value': final_price.get('value'), 'currency': final_price.get('currency')}}}}
        records = sorted(merged.values(), key=lambda r: r['sku'])
        return {'records': records, 'executed_queries': executed_queries}

class ShoppingOrders:

    def __init__(self, page):
        self.page = page

    async def get_customer_order_detail(self, order_id: str) -> dict:
        import re
        from urllib.parse import urlparse
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError('order_id must be a non-empty string')
        parsed = urlparse(self.page.url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError('self.page.url must contain the shopping site origin before calling this method')
        base_url = f'{parsed.scheme}://{parsed.netloc}'
        detail_url = f'{base_url}/sales/order/view/order_id/{order_id}/'
        response = await self.page.goto(detail_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        main_text = await self.page.locator('main').inner_text()
        order_number_match = re.search('Order #\\s*(\\d+)', main_text)
        status_match = re.search('Order #\\s*\\d+\\s*(\\w+)', main_text)
        date_match = re.search('Order Date:\\s*([A-Za-z]+ \\d{1,2}, \\d{4})', main_text)
        total_match = re.search('Grand Total\\s*\\$(\\d+[\\d,]*\\.\\d{2})', main_text)
        item_names = []
        product_cells = await self.page.locator('table tbody tr td.col.name').all_inner_texts()
        if product_cells:
            item_names = [re.sub('\\s+', ' ', t).strip() for t in product_cells]
        else:
            for m in re.finditer('Product Name\\s*SKU\\s*Price\\s*Qty\\s*Subtotal\\s*(.*?)\\s+B[0-9A-Z]+', main_text, re.S):
                item_names.append(re.sub('\\s+', ' ', m.group(1)).strip())
        if not (order_number_match and status_match and date_match and total_match):
            return {'detail_url': detail_url, 'document_status': response.status if response else None, 'record': None}
        return {'detail_url': detail_url, 'document_status': response.status if response else None, 'record': {'order_id': str(order_id), 'order_number': order_number_match.group(1), 'status': status_match.group(1), 'order_date': date_match.group(1), 'grand_total': float(total_match.group(1).replace(',', '')), 'currency_symbol': '$', 'item_names': item_names}}

    def list_authenticated_customer_orders_graphql(self, base_url, email, password, retrieval_mode='single_page', page_size=20, page_number=1, order_number_filter=None):
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError('base_url must be a non-empty string')
        if not isinstance(email, str) or not email.strip():
            raise ValueError('email must be a non-empty string')
        if not isinstance(password, str) or not password:
            raise ValueError('password must be a non-empty string')
        if retrieval_mode not in ('single_page', 'all_pages'):
            raise ValueError("retrieval_mode must be 'single_page' or 'all_pages'")
        if not isinstance(page_size, int) or page_size < 1:
            raise ValueError('page_size must be a positive integer')
        if not isinstance(page_number, int) or page_number < 1:
            raise ValueError('page_number must be a positive integer')
        if order_number_filter is not None and (not isinstance(order_number_filter, str) or not order_number_filter.strip()):
            raise ValueError('order_number_filter must be null or a non-empty string')
        root = base_url.rstrip('/')
        graphql_url = root + '/graphql'
        token_query = 'mutation GenerateCustomerToken($email: String!, $password: String!) { generateCustomerToken(email: $email, password: $password) { token }}'
        token_resp = self.page.request.post(graphql_url, json={'query': token_query, 'variables': {'email': email, 'password': password}}, fail_on_status_code=False)
        token_payload = token_resp.json()
        token = ((token_payload.get('data') or {}).get('generateCustomerToken') or {}).get('token')
        if not token:
            raise RuntimeError('Customer GraphQL authentication failed')
        filter_clause = 'filter: { number: { match: $match } }, ' if order_number_filter is not None else ''
        orders_query = 'query GetOrders($pageSize: Int!, $currentPage: Int!' + (', $match: String!' if order_number_filter is not None else '') + ') { customer {   firstname lastname email   orders(' + filter_clause + 'pageSize: $pageSize, currentPage: $currentPage) {     total_count     page_info { current_page page_size total_pages }     items {       id number order_date created_at status grand_total       total { grand_total { value currency } }     }   } }}'

        def _fetch_page(requested_page):
            variables = {'pageSize': page_size, 'currentPage': requested_page}
            if order_number_filter is not None:
                variables['match'] = order_number_filter
            resp = self.page.request.post(graphql_url, json={'query': orders_query, 'variables': variables}, headers={'Authorization': f'Bearer {token}'}, fail_on_status_code=False)
            payload = resp.json()
            customer = (payload.get('data') or {}).get('customer') or {}
            orders_block = customer.get('orders') or {}
            page_info = orders_block.get('page_info') or {}
            items = []
            for item in orders_block.get('items') or []:
                nested_grand_total = (item.get('total') or {}).get('grand_total') or {}
                items.append({'id': item.get('id'), 'number': item.get('number'), 'order_date': item.get('order_date'), 'created_at': item.get('created_at'), 'status': item.get('status'), 'grand_total': item.get('grand_total'), 'total': {'grand_total': {'value': nested_grand_total.get('value'), 'currency': nested_grand_total.get('currency')}}})
            return {'customer': {'firstname': customer.get('firstname'), 'lastname': customer.get('lastname'), 'email': customer.get('email')}, 'orders': {'total_count': orders_block.get('total_count'), 'page_info': {'current_page': page_info.get('current_page'), 'page_size': page_info.get('page_size'), 'total_pages': page_info.get('total_pages')}, 'items': items}}
        first_page = _fetch_page(page_number)
        if retrieval_mode == 'single_page':
            return {'customer': first_page['customer'], 'orders': first_page['orders'], 'retrieval_mode': 'single_page', 'pages_fetched': 1, 'order_number_filter': order_number_filter}
        total_pages = first_page['orders']['page_info'].get('total_pages') or 0
        aggregated_items = list(first_page['orders']['items'])
        pages_fetched = 1
        current_page = page_number + 1
        while current_page <= total_pages:
            next_page = _fetch_page(current_page)
            if next_page['orders']['page_info'].get('current_page') != current_page:
                raise ValueError('Paginated GraphQL response current_page did not match requested page')
            if next_page['orders']['page_info'].get('total_pages') != total_pages:
                raise ValueError('Paginated GraphQL response total_pages changed during traversal')
            aggregated_items.extend(next_page['orders']['items'])
            pages_fetched += 1
            current_page += 1
        return {'customer': first_page['customer'], 'orders': {'total_count': first_page['orders']['total_count'], 'page_info': {'current_page': first_page['orders']['page_info']['current_page'], 'page_size': first_page['orders']['page_info']['page_size'], 'total_pages': first_page['orders']['page_info']['total_pages']}, 'items': aggregated_items}, 'retrieval_mode': 'all_pages', 'pages_fetched': pages_fetched, 'order_number_filter': order_number_filter}

    async def list_customer_orders_history_page(self, page_number: int=1) -> dict:
        from urllib.parse import urlparse
        if not isinstance(page_number, int) or page_number < 1:
            raise ValueError('page_number must be a positive integer')
        if page_number != 1:
            raise ValueError('Only the demonstrated first orders-history page is supported')
        parsed = urlparse(self.page.url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError('self.page.url must contain the shopping site origin before calling this method')
        orders_history_url = f'{parsed.scheme}://{parsed.netloc}/sales/order/history/'
        response = await self.page.goto(orders_history_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        rows = self.page.locator('table tbody tr')
        records = []
        count = await rows.count()
        for i in range(count):
            cells = [c.strip() for c in await rows.nth(i).locator('td').all_inner_texts()]
            if len(cells) >= 4:
                records.append({'order_number': cells[0], 'order_date': cells[1], 'ship_to': cells[2], 'order_total_text': cells[3], 'display_cells': cells})
            elif cells:
                records.append({'order_number': cells[0] if len(cells) > 0 else None, 'order_date': cells[1] if len(cells) > 1 else None, 'ship_to': cells[2] if len(cells) > 2 else None, 'order_total_text': cells[3] if len(cells) > 3 else None, 'display_cells': cells})
        return {'orders_history_url': self.page.url, 'document_status': response.status if response else None, 'page_number': page_number, 'records': records}

    def list_order_history_page_html(self, base_url):
        import re
        import html as html_lib
        from datetime import datetime
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError('base_url must be a non-empty string')
        response = self.page.goto(f"{base_url.rstrip('/')}/sales/order/history/", wait_until='domcontentloaded')
        if response is None:
            raise ValueError('Order history navigation produced no response')
        if response.status >= 400:
            raise ValueError(f'Order history page returned HTTP {response.status}')
        content = self.page.content()
        if 'My Orders' not in content:
            raise ValueError("Authenticated order-history page indicator 'My Orders' was not found")
        row_pattern = re.compile('<tr>\\s*<td[^>]*class="col id"[^>]*>(.*?)</td>\\s*<td[^>]*class="col date"[^>]*>(.*?)</td>.*?<td[^>]*class="col total"[^>]*>.*?<span class="price">(.*?)</span>.*?</td>\\s*<td[^>]*class="col status"[^>]*>(.*?)</td>', re.I | re.S)

        def _clean(text):
            return ' '.join(html_lib.unescape(re.sub('<[^>]+>', ' ', text or '')).split())
        orders = []
        for (order_id, date_text, total_text, status_text) in row_pattern.findall(content):
            oid = _clean(order_id)
            dtx = _clean(date_text)
            ttx = _clean(total_text)
            stx = _clean(status_text)
            if not oid or not dtx or (not ttx) or (not stx):
                raise ValueError('Parsed order-history row was missing one or more required displayed fields')
            parsed_date = None
            try:
                parsed_date = datetime.strptime(dtx, '%m/%d/%y').date().isoformat()
            except Exception:
                parsed_date = None
            amount = None
            try:
                amount = float(ttx.replace('$', '').replace(',', ''))
            except Exception:
                amount = None
            orders.append({'order_id': oid, 'date_text': dtx, 'date': parsed_date, 'total_text': ttx, 'amount': amount, 'status': stx})
        return {'orders_history_url': self.page.url, 'document_status': response.status, 'orders': orders}

class ShoppingReviews:

    def __init__(self, page):
        self.page = page

    async def extract_product_review_texts_from_product_page(self, url: str) -> dict:
        import re
        response = await self.page.goto(url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        reviews_tab = self.page.locator('#tab-label-reviews-title')
        if await reviews_tab.count() > 0:
            await reviews_tab.first.click()
            await self.page.wait_for_timeout(1200)
        review_nodes = self.page.locator('.review-content')
        reviews = []
        count = await review_nodes.count()
        for i in range(count):
            text = await review_nodes.nth(i).inner_text()
            reviews.append({'content_text': re.sub('\\s+', ' ', text).strip()})
        return {'product_url': self.page.url, 'document_status': response.status if response else None, 'reviews': reviews}

class ShoppingSite:

    def __init__(self, page):
        self.auth = ShoppingAuth(page)
        self.catalog = ShoppingCatalog(page)
        self.orders = ShoppingOrders(page)
        self.reviews = ShoppingReviews(page)
