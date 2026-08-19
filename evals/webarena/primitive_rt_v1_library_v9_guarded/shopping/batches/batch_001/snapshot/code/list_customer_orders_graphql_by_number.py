def list_customer_orders_graphql_by_number(self, email: str, password: str, order_number_match: str) -> dict:
    from urllib.parse import urlparse

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

    orders_query = '''query GetOrdersByNumber($match: String!) { customer { orders(filter: {number: {match: $match}}) { items { number order_date status total { grand_total { value currency } } } total_count } } }'''
    orders_resp = self.page.request.post(
        graphql_url,
        data={'query': orders_query, 'variables': {'match': order_number_match}},
        headers={'Authorization': f'Bearer {token}'},
    )
    payload = orders_resp.json()
    customer = (payload.get('data') or {}).get('customer')
    if customer is None:
        raise RuntimeError('Customer orders response shape missing')

    orders_node = customer.get('orders') or {}
    items = []
    for item in orders_node.get('items') or []:
        grand_total = ((item.get('total') or {}).get('grand_total') or {})
        items.append({
            'number': item.get('number'),
            'order_date': item.get('order_date'),
            'status': item.get('status'),
            'grand_total_value': grand_total.get('value'),
            'grand_total_currency': grand_total.get('currency'),
        })

    return {
        'is_authenticated': True,
        'orders': items,
        'total_count': orders_node.get('total_count'),
        'query_filter': {
            'order_number_match': order_number_match,
        },
    }
