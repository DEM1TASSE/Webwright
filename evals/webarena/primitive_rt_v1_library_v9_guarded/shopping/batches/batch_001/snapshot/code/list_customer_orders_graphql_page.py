def list_customer_orders_graphql_page(self, email: str, password: str, page_size: int, page_number: int) -> dict:
    from urllib.parse import urlparse

    if page_size < 1 or page_number < 1:
        raise ValueError('page_size and page_number must be >= 1')

    current_url = self.page.url or ''
    parsed = urlparse(current_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError('self.page must already be on the shopping site origin so /graphql can be resolved')
    graphql_url = f'{parsed.scheme}://{parsed.netloc}/graphql'

    token_query = '''mutation GenerateCustomerToken($email: String!, $password: String!) { generateCustomerToken(email: $email, password: $password) { token } }'''
    token_resp = self.page.request.post(
        graphql_url,
        data={'query': token_query, 'variables': {'email': email, 'password': password}},
    )
    token_json = token_resp.json()
    token = ((token_json.get('data') or {}).get('generateCustomerToken') or {}).get('token')
    if not token:
        raise RuntimeError('Customer GraphQL authentication failed')

    orders_query = '''query GetOrders($pageSize: Int!, $currentPage: Int!) { customer { firstname lastname email orders(pageSize: $pageSize, currentPage: $currentPage) { total_count page_info { current_page page_size total_pages } items { number status created_at grand_total total { grand_total { value currency } } } } } }'''
    orders_resp = self.page.request.post(
        graphql_url,
        data={'query': orders_query, 'variables': {'pageSize': page_size, 'currentPage': page_number}},
        headers={'Authorization': f'Bearer {token}'},
    )
    payload = orders_resp.json()
    customer = (payload.get('data') or {}).get('customer')
    if customer is None:
        raise RuntimeError('Customer orders response shape missing')

    orders_node = customer.get('orders') or {}
    page_info = orders_node.get('page_info') or {}
    items = []
    for item in orders_node.get('items') or []:
        nested = ((item.get('total') or {}).get('grand_total') or {})
        items.append({
            'number': item.get('number'),
            'status': item.get('status'),
            'created_at': item.get('created_at'),
            'grand_total': item.get('grand_total'),
            'total': {
                'grand_total': {
                    'value': nested.get('value'),
                    'currency': nested.get('currency'),
                }
            },
        })

    return {
        'is_authenticated': True,
        'customer': {
            'firstname': customer.get('firstname'),
            'lastname': customer.get('lastname'),
            'email': customer.get('email'),
        },
        'orders': {
            'total_count': orders_node.get('total_count'),
            'page_info': {
                'current_page': page_info.get('current_page'),
                'page_size': page_info.get('page_size'),
                'total_pages': page_info.get('total_pages'),
            },
            'items': items,
        },
    }
