"""Generated candidate package; not promoted."""

class ShoppingCatalog:

    def __init__(self, page):
        self.page = page

    async def search_products_graphql(self, search_term: str, page_size: int=50) -> dict:
        from urllib.parse import urlsplit, urljoin
        if page_size < 1:
            raise ValueError('page_size must be >= 1')
        current = urlsplit(self.page.url)
        origin = f'{current.scheme}://{current.netloc}'
        graphql_url = urljoin(origin + '/', 'graphql')
        escaped_search = search_term.replace('\\', '\\\\').replace('"', '\\"')
        query = '{ products(search:"' + escaped_search + f'", pageSize:{int(page_size)}) ' + '{ total_count items { name sku url_key url_suffix price_range { minimum_price { regular_price { value currency } final_price { value currency } } } } } }'
        response = await self.page.request.get(graphql_url, params={'query': query})
        if not response.ok:
            raise RuntimeError(f'GraphQL products search failed with status {response.status}')
        payload = await response.json()
        products = ((payload or {}).get('data') or {}).get('products') or {}
        items = products.get('items') or []
        typed_items = []
        for item in items:
            minimum_price = (item.get('price_range') or {}).get('minimum_price') or {}
            regular_price = minimum_price.get('regular_price') or {}
            final_price = minimum_price.get('final_price') or {}
            url_key = item.get('url_key')
            url_suffix = item.get('url_suffix') or ''
            product_url = urljoin(origin + '/', f'{url_key or ''}{url_suffix}'.lstrip('/'))
            typed_items.append({'name': item.get('name') or '', 'sku': item.get('sku'), 'url_key': url_key, 'url_suffix': item.get('url_suffix'), 'product_url': product_url, 'minimum_price_regular_value': regular_price.get('value'), 'minimum_price_regular_currency': regular_price.get('currency'), 'minimum_price_final_value': final_price.get('value'), 'minimum_price_final_currency': final_price.get('currency')})
        return {'total_count': int(products.get('total_count') or 0), 'items': typed_items}

class ShoppingOrders:

    def __init__(self, page):
        self.page = page

    async def get_order_detail(self, order_id: str) -> dict:
        import re
        from urllib.parse import urlsplit, urljoin
        current = urlsplit(self.page.url)
        origin = f'{current.scheme}://{current.netloc}'
        detail_url = urljoin(origin + '/', f'sales/order/view/order_id/{order_id}/')
        await self.page.goto(detail_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        main_text = await self.page.locator('main').inner_text()
        order_number_match = re.search('Order #\\s*(\\d+)', main_text)
        status_word_match = re.search('Order #\\s*\\d+\\s*(\\w+)', main_text)
        date_match = re.search('Order Date:\\s*([A-Za-z]+ \\d{1,2}, \\d{4})', main_text)
        grand_total_match = re.search('Grand Total\\s*\\$(\\d+[\\d,]*\\.\\d{2})', main_text)
        if not (order_number_match and date_match and grand_total_match):
            raise ValueError('Order detail page did not match the demonstrated parsing pattern')
        product_cells = await self.page.locator('table tbody tr td.col.name').all_inner_texts()
        item_names = [re.sub('\\s+', ' ', t).strip() for t in product_cells if t.strip()]
        grand_total_text = f'${grand_total_match.group(1)}'
        grand_total_amount = float(grand_total_match.group(1).replace(',', ''))
        return {'order_id': order_id, 'order_number': order_number_match.group(1), 'status_word': status_word_match.group(1) if status_word_match else None, 'order_date_text': date_match.group(1), 'grand_total_text': grand_total_text, 'grand_total_amount': grand_total_amount, 'item_names': item_names}

    async def get_order_history_page(self, username: str, password: str) -> dict:
        import re
        from urllib.parse import urlsplit, urljoin
        current_url = self.page.url
        parts = urlsplit(current_url)
        if not parts.scheme or not parts.netloc:
            raise RuntimeError('Cannot derive site origin from self.page.url')
        origin = f'{parts.scheme}://{parts.netloc}'
        login_url = urljoin(origin + '/', 'customer/account/login/')
        login_post_url = urljoin(origin + '/', 'customer/account/loginPost/')
        orders_url = urljoin(origin + '/', 'sales/order/history/')
        login_resp = await self.page.request.get(login_url)
        login_html = await login_resp.text()
        form_key_match = re.search('name="form_key"\\s+type="hidden"\\s+value="([^"]+)"', login_html)
        if not form_key_match:
            raise RuntimeError('Login form_key not found on customer login page')
        form_key = form_key_match.group(1)
        post_resp = await self.page.request.post(login_post_url, form={'form_key': form_key, 'login[username]': username, 'login[password]': password}, headers={'Referer': login_url})
        await post_resp.text()
        orders_resp = await self.page.request.get(orders_url)
        orders_page_html = await orders_resp.text()
        orders_page_url = str(orders_resp.url)
        http_status = orders_resp.status
        if '<title>My Orders</title>' not in orders_page_html and 'My Orders' not in orders_page_html:
            raise RuntimeError('Authenticated orders history page was not returned')
        return {'orders_page_url': orders_page_url, 'http_status': http_status, 'orders_page_html': orders_page_html}

    async def list_authenticated_customer_orders(self, base_url: str, email: str, password: str, page_number: int=1, page_size: int=20, fetch_all_pages: bool=False):
        import json
        from urllib.parse import urljoin
        if page_number < 1:
            raise ValueError('page_number must be >= 1')
        if page_size < 1:
            raise ValueError('page_size must be >= 1')
        token_url = urljoin(base_url.rstrip('/') + '/', 'rest/V1/integration/customer/token')
        graphql_url = urljoin(base_url.rstrip('/') + '/', 'graphql')
        token_response = await self.page.request.post(token_url, data={'username': email, 'password': password})
        if token_response.status != 200:
            raise RuntimeError(f'Token request failed with status {token_response.status}')
        token_text = await token_response.text()
        try:
            token = json.loads(token_text)
        except Exception as exc:
            raise RuntimeError('Token response was not valid JSON') from exc
        if not isinstance(token, str) or not token:
            raise RuntimeError('Token response did not contain a bearer token string')
        query = 'query($page:Int!, $pageSize:Int!){ customer { firstname lastname email orders(pageSize: $pageSize, currentPage: $page) { items { number order_date status total { grand_total { value currency } } } total_count page_info { current_page total_pages } } } }'
        collected_orders = []
        customer_obj = None
        current = page_number
        final_total_pages = None
        final_total_count = None
        fetched_all_pages = False
        while True:
            gql_response = await self.page.request.post(graphql_url, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, data={'query': query, 'variables': {'page': current, 'pageSize': page_size}})
            if gql_response.status != 200:
                raise RuntimeError(f'GraphQL request failed with status {gql_response.status} on page {current}')
            payload = await gql_response.json()
            if payload.get('errors'):
                raise RuntimeError(f'GraphQL returned errors on page {current}: {payload['errors']}')
            customer = payload.get('data', {}).get('customer')
            if customer is None:
                raise RuntimeError('GraphQL response did not include data.customer')
            customer_obj = {'firstname': customer.get('firstname'), 'lastname': customer.get('lastname'), 'email': customer.get('email')}
            orders = customer.get('orders') or {}
            page_info = orders.get('page_info') or {}
            final_total_pages = page_info.get('total_pages')
            final_total_count = orders.get('total_count')
            for item in orders.get('items') or []:
                grand_total = (item.get('total') or {}).get('grand_total') or {}
                collected_orders.append({'order_number': item.get('number'), 'order_date_utc': item.get('order_date'), 'status': item.get('status'), 'grand_total_value': grand_total.get('value'), 'grand_total_currency': grand_total.get('currency')})
            if not fetch_all_pages:
                break
            if not isinstance(final_total_pages, int) or final_total_pages < current:
                raise RuntimeError('GraphQL page_info.total_pages was missing or invalid')
            if current >= final_total_pages:
                fetched_all_pages = True
                break
            current += 1
        return {'customer': customer_obj, 'orders': collected_orders, 'pagination': {'current_page': current if fetch_all_pages else page_number, 'total_pages': final_total_pages, 'total_count': final_total_count, 'fetched_all_pages': fetched_all_pages}}

    async def list_authenticated_customer_orders_graphql(self, email: str, password: str, query_mode: str='page', page_size: int=200, page_number: int=1, order_number_match: str | None=None) -> dict:
        import json
        from urllib.parse import urlsplit, urljoin
        if query_mode not in {'page', 'order_number_match'}:
            raise ValueError("query_mode must be 'page' or 'order_number_match'")
        if page_size < 1:
            raise ValueError('page_size must be >= 1')
        if page_number < 1:
            raise ValueError('page_number must be >= 1')
        if query_mode == 'order_number_match' and (not order_number_match):
            raise ValueError("order_number_match is required when query_mode='order_number_match'")
        current_url = self.page.url
        parts = urlsplit(current_url)
        if not parts.scheme or not parts.netloc:
            raise RuntimeError('Cannot derive site origin from self.page.url')
        origin = f'{parts.scheme}://{parts.netloc}'
        graphql_url = urljoin(origin + '/', 'graphql')
        token_query = 'mutation GenerateCustomerToken($email: String!, $password: String!) { generateCustomerToken(email: $email, password: $password) { token } }'
        token_resp = await self.page.request.post(graphql_url, data={'query': token_query, 'variables': json.dumps({'email': email, 'password': password})})
        if not token_resp.ok:
            raise RuntimeError(f'Customer GraphQL authentication failed with status {token_resp.status}')
        token_payload = await token_resp.json()
        token = ((token_payload or {}).get('data') or {}).get('generateCustomerToken', {}).get('token')
        if not token:
            raise RuntimeError('Customer GraphQL authentication failed')
        if query_mode == 'order_number_match':
            orders_query = 'query GetCustomerOrdersByNumber($match: String!) { customer { firstname lastname email orders(filter: {number: {match: $match}}) { total_count items { number order_date status total { grand_total { value currency } } } } } }'
            variables = json.dumps({'match': order_number_match})
        else:
            orders_query = 'query GetCustomerOrders($pageSize: Int!, $currentPage: Int!) { customer { firstname lastname email orders(pageSize: $pageSize, currentPage: $currentPage) { total_count page_info { current_page page_size total_pages } items { number status created_at grand_total total { grand_total { value currency } } } } } }'
            variables = json.dumps({'pageSize': page_size, 'currentPage': page_number})
        orders_resp = await self.page.request.post(graphql_url, data={'query': orders_query, 'variables': variables}, headers={'Authorization': f'Bearer {token}'})
        if not orders_resp.ok:
            raise RuntimeError(f'Customer orders GraphQL query failed with status {orders_resp.status}')
        orders_payload = await orders_resp.json()
        customer = ((orders_payload or {}).get('data') or {}).get('customer')
        if customer is None or 'orders' not in customer:
            raise RuntimeError('Customer orders were not returned by GraphQL')
        orders_obj = customer.get('orders') or {}
        page_info = orders_obj.get('page_info') or {}
        items_out = []
        for item in orders_obj.get('items') or []:
            total_obj = item.get('total') or {}
            grand_total_obj = total_obj.get('grand_total') or {}
            items_out.append({'number': item.get('number'), 'status': item.get('status'), 'created_at': item.get('created_at'), 'order_date': item.get('order_date'), 'grand_total': item.get('grand_total'), 'total': {'grand_total': {'value': grand_total_obj.get('value'), 'currency': grand_total_obj.get('currency')}}})
        return {'customer': {'firstname': customer.get('firstname'), 'lastname': customer.get('lastname'), 'email': customer.get('email')}, 'orders': {'total_count': orders_obj.get('total_count'), 'page_info': {'current_page': page_info.get('current_page'), 'page_size': page_info.get('page_size'), 'total_pages': page_info.get('total_pages')}, 'items': items_out}}

    async def list_customer_orders_page(self) -> dict:
        from urllib.parse import urlsplit, urljoin
        current = urlsplit(self.page.url)
        origin = f'{current.scheme}://{current.netloc}'
        orders_url = urljoin(origin + '/', 'sales/order/history/')
        await self.page.goto(orders_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        rows = self.page.locator('table tbody tr')
        count = await rows.count()
        orders = []
        for i in range(count):
            row = rows.nth(i)
            cells = [c.strip() for c in await row.locator('td').all_inner_texts()]
            if len(cells) >= 4:
                orders.append({'order_number': cells[0], 'order_date_text': cells[1], 'ship_to_text': cells[2], 'order_total_text': cells[3]})
        return {'orders': orders}

    async def list_orders_from_order_history_page(self, orders_page_html: str) -> dict:
        import re
        from datetime import datetime

        def _strip_tags(html: str) -> str:
            return re.sub('<[^>]+>', ' ', html)
        row_pattern = re.compile('<tr>\\s*<td[^>]*class="col id"[^>]*>(.*?)</td>\\s*<td[^>]*class="col date"[^>]*>(.*?)</td>.*?<td[^>]*class="col total"[^>]*>.*?<span class="price">(.*?)</span>.*?</td>\\s*<td[^>]*class="col status"[^>]*>(.*?)</td>', re.S)
        orders = []
        for order_id_html, date_html, total_html, status_html in row_pattern.findall(orders_page_html):
            order_id = re.sub('\\s+', ' ', _strip_tags(order_id_html)).strip()
            order_date_text = re.sub('\\s+', ' ', _strip_tags(date_html)).strip()
            total_text = re.sub('\\s+', ' ', _strip_tags(total_html)).strip()
            status_text = re.sub('\\s+', ' ', _strip_tags(status_html)).strip()
            try:
                order_date_iso = datetime.strptime(order_date_text, '%m/%d/%y').date().isoformat()
            except Exception:
                continue
            total_amount = float(total_text.replace('$', '').replace(',', ''))
            orders.append({'order_id': order_id, 'order_date_text': order_date_text, 'order_date_iso': order_date_iso, 'total_text': total_text, 'total_amount': total_amount, 'status_text': status_text})
        return {'orders': orders}

class ShoppingReviews:

    def __init__(self, page):
        self.page = page

    async def get_product_review_texts_from_reviews_tab(self, product_url: str) -> dict:
        from urllib.parse import urlsplit
        if not urlsplit(product_url).scheme or not urlsplit(product_url).netloc:
            raise ValueError('product_url must be an absolute URL')
        await self.page.goto(product_url, wait_until='networkidle')
        await self.page.locator('#tab-label-reviews-title').click()
        reviews_container = self.page.locator('#reviews')
        if await reviews_container.count() == 0:
            raise ValueError("Reviews container '#reviews' was not found after opening the Reviews tab")
        reviews_section_text = (await reviews_container.inner_text()).strip()
        review_texts = [text.strip() for text in await self.page.locator('.review-content').all_inner_texts()]
        return {'product_url': self.page.url, 'reviews_section_text': reviews_section_text, 'review_texts': review_texts}

class ShoppingSite:

    def __init__(self, page):
        self.catalog = ShoppingCatalog(page)
        self.orders = ShoppingOrders(page)
        self.reviews = ShoppingReviews(page)
