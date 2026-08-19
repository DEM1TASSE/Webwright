def list_customer_orders_by_number_graphql(self, base_url, email, password, order_number_match):
    root = base_url.rstrip('/')
    graphql_url = root + '/graphql'

    token_query = (
        'mutation GenerateCustomerToken($email: String!, $password: String!) {'
        ' generateCustomerToken(email: $email, password: $password) { token }'
        '}'
    )
    token_resp = self.page.request.post(
        graphql_url,
        json={
            'query': token_query,
            'variables': {'email': email, 'password': password},
        },
        fail_on_status_code=False,
    )
    token_payload = token_resp.json()
    token = (((token_payload.get('data') or {}).get('generateCustomerToken') or {}).get('token'))
    if not token:
        raise RuntimeError('Customer GraphQL authentication failed')

    orders_query = (
        'query GetOrdersByNumber($match: String!) {'
        ' customer {'
        '   orders(filter: { number: { match: $match } }) {'
        '     items {'
        '       number'
        '       order_date'
        '       status'
        '       total { grand_total { value currency } }'
        '     }'
        '     total_count'
        '   }'
        ' }'
        '}'
    )
    orders_resp = self.page.request.post(
        graphql_url,
        json={
            'query': orders_query,
            'variables': {'match': order_number_match},
        },
        headers={'Authorization': f'Bearer {token}'},
        fail_on_status_code=False,
    )
    payload = orders_resp.json()
    orders_block = ((((payload.get('data') or {}).get('customer')) or {}).get('orders')) or {}

    orders = []
    for item in orders_block.get('items') or []:
        grand_total = (((item.get('total') or {}).get('grand_total')) or {})
        orders.append({
            'number': item.get('number'),
            'order_date': item.get('order_date'),
            'status': item.get('status'),
            'grand_total_value': grand_total.get('value'),
            'grand_total_currency': grand_total.get('currency'),
        })

    return {
        'orders': orders,
        'total_count': orders_block.get('total_count'),
    }
