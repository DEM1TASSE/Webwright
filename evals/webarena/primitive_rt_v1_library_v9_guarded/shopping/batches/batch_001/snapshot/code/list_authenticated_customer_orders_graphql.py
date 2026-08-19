def list_authenticated_customer_orders_graphql(self, base_url, email, password, page_size, page_number):
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
        'query GetOrders($pageSize: Int!, $currentPage: Int!) {'
        ' customer {'
        '   firstname lastname email'
        '   orders(pageSize: $pageSize, currentPage: $currentPage) {'
        '     total_count'
        '     page_info { current_page page_size total_pages }'
        '     items {'
        '       id number order_date created_at status grand_total'
        '       total { grand_total { value currency } }'
        '     }'
        '   }'
        ' }'
        '}'
    )
    resp = self.page.request.post(
        graphql_url,
        json={
            'query': orders_query,
            'variables': {'pageSize': page_size, 'currentPage': page_number},
        },
        headers={'Authorization': f'Bearer {token}'},
        fail_on_status_code=False,
    )
    payload = resp.json()
    customer = ((payload.get('data') or {}).get('customer')) or {}
    orders_block = customer.get('orders') or {}

    items = []
    for item in orders_block.get('items') or []:
        nested_grand_total = (((item.get('total') or {}).get('grand_total')) or {})
        items.append({
            'id': item.get('id'),
            'number': item.get('number'),
            'order_date': item.get('order_date'),
            'created_at': item.get('created_at'),
            'status': item.get('status'),
            'grand_total': item.get('grand_total'),
            'total': {
                'grand_total': {
                    'value': nested_grand_total.get('value'),
                    'currency': nested_grand_total.get('currency'),
                }
            },
        })

    page_info = orders_block.get('page_info') or {}
    return {
        'customer': {
            'firstname': customer.get('firstname'),
            'lastname': customer.get('lastname'),
            'email': customer.get('email'),
        },
        'orders': {
            'total_count': orders_block.get('total_count'),
            'page_info': {
                'current_page': page_info.get('current_page'),
                'page_size': page_info.get('page_size'),
                'total_pages': page_info.get('total_pages'),
            },
            'items': items,
        },
    }
