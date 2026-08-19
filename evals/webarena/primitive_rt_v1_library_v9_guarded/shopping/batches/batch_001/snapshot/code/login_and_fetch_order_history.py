def login_and_fetch_order_history(self, base_url, username, password):
    import re

    root = base_url.rstrip('/')
    login_url = root + '/customer/account/login/'
    login_resp = self.page.request.get(
        login_url,
        headers={'User-Agent': 'Mozilla/5.0'},
        fail_on_status_code=False,
    )
    login_html = login_resp.text()
    form_key_match = re.search(r'name="form_key" type="hidden" value="([^"]+)"', login_html)
    if not form_key_match:
        raise RuntimeError('Login form_key not found on customer login page')
    form_key = form_key_match.group(1)

    self.page.request.post(
        root + '/customer/account/loginPost/',
        form={
            'form_key': form_key,
            'login[username]': username,
            'login[password]': password,
        },
        headers={
            'User-Agent': 'Mozilla/5.0',
            'Referer': login_url,
        },
        fail_on_status_code=False,
    )

    orders_url = root + '/sales/order/history/'
    orders_resp = self.page.request.get(
        orders_url,
        headers={'User-Agent': 'Mozilla/5.0'},
        fail_on_status_code=False,
    )
    orders_html = orders_resp.text()
    final_url = orders_resp.url
    authenticated = bool(
        ('<title>My Orders</title>' in orders_html)
        or ('My Orders' in orders_html)
        or ('/sales/order/history/' in (final_url or ''))
    )

    return {
        'final_url': final_url,
        'document_status': orders_resp.status,
        'html': orders_html,
        'response_headers': dict(orders_resp.headers),
        'authenticated': authenticated,
    }
