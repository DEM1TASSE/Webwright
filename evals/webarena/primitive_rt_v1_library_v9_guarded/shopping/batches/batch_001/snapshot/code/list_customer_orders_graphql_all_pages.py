def list_customer_orders_graphql_all_pages(self, page_size: int) -> dict:
    import httpx
    from urllib.parse import urlparse

    if page_size < 1:
        raise ValueError('page_size must be >= 1')

    current_url = self.page.url or ''
    parsed = urlparse(current_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError('self.page must already be on the shopping site origin so /graphql can be resolved')
    graphql_url = f'{parsed.scheme}://{parsed.netloc}/graphql'

    cookies = self.page.context.cookies()
    jar = httpx.Cookies()
    for c in cookies:
        jar.set(c['name'], c['value'], domain=c.get('domain'), path=c.get('path', '/'))

    query = '''query GetOrders($pageSize: Int!, $currentPage: Int!) { customer { orders(pageSize: $pageSize, currentPage: $currentPage) { items { id number order_date status grand_total } page_info { current_page page_size total_pages } total_count } } }'''

    all_items = []
    current_page = 1
    total_pages = 1
    last_page_info = {'current_page': 1, 'page_size': page_size, 'total_pages': 1}
    total_count = 0

    with httpx.Client(cookies=jar, timeout=30.0) as client:
        while current_page <= total_pages:
            response = client.post(
                graphql_url,
                json={'query': query, 'variables': {'pageSize': page_size, 'currentPage': current_page}},
            )
            payload = response.json()
            customer = (payload.get('data') or {}).get('customer')
            if customer is None:
                raise RuntimeError('Customer orders response shape missing')
            orders_node = customer.get('orders') or {}
            page_info = orders_node.get('page_info') or {}
            reported_total_pages = page_info.get('total_pages')
            total_pages = reported_total_pages if isinstance(reported_total_pages, int) and reported_total_pages >= 1 else current_page
            reported_total_count = orders_node.get('total_count')
            total_count = reported_total_count if isinstance(reported_total_count, int) else total_count
            last_page_info = {
                'current_page': page_info.get('current_page'),
                'page_size': page_info.get('page_size'),
                'total_pages': page_info.get('total_pages'),
            }
            for item in orders_node.get('items') or []:
                all_items.append({
                    'id': item.get('id'),
                    'number': item.get('number'),
                    'order_date': item.get('order_date'),
                    'status': item.get('status'),
                    'grand_total': item.get('grand_total'),
                })
            current_page += 1

    return {
        'orders': all_items,
        'page_info': last_page_info,
        'total_count': total_count,
        'collection_mode': 'all_pages',
    }
