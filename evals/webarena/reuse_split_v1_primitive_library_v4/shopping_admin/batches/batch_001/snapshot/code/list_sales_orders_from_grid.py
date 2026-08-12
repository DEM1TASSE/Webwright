async def list_sales_orders_from_grid(self, status: str | None = None, page_number: int = 1, page_size: int = 200) -> dict:
    import json
    import re
    from urllib.parse import urlencode, urljoin

    if page_number < 1:
        raise ValueError("page_number must be >= 1")
    if page_size < 1:
        raise ValueError("page_size must be >= 1")

    await self.page.goto('/admin/sales/order/', wait_until='domcontentloaded')
    await self.page.wait_for_load_state('networkidle')

    params = {
        'namespace': 'sales_order_grid',
        'paging[pageSize]': str(page_size),
        'paging[current]': str(page_number),
        'isAjax': 'true',
    }
    if status is not None:
        params['filters[status]'] = status

    render_url = '/admin/mui/index/render/?' + urlencode(params)
    response = await self.page.context.request.get(
        urljoin(self.page.url, render_url),
        headers={
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': urljoin(self.page.url, '/admin/sales/order/'),
        },
    )
    if not response.ok:
        raise RuntimeError(f'Failed to fetch sales order grid: HTTP {response.status}')

    raw_text = await response.text()
    content_type = (response.headers.get('content-type') or '').lower()

    payload = None
    if 'application/json' in content_type:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict) and 'items' in parsed:
            payload = parsed
        else:
            raise RuntimeError('Unexpected JSON payload for sales order grid.')
    else:
        script_match = re.search(r'<script type="text/x-magento-init">(.*?)</script>', raw_text, re.S)
        if script_match:
            app = json.loads(script_match.group(1))['*']['Magento_Ui/js/core/app']
            payload = app['components']['sales_order_grid']['children']['sales_order_grid_data_source']['config']['data']
        else:
            marker = '"sales_order_grid_data_source":'
            start = raw_text.find(marker)
            if start == -1:
                raise RuntimeError('Could not locate sales order grid payload in response.')
            idx = start + len(marker)
            while idx < len(raw_text) and raw_text[idx].isspace():
                idx += 1
            if idx >= len(raw_text) or raw_text[idx] != '{':
                raise RuntimeError('Embedded sales order grid payload did not start with an object.')
            depth = 0
            end = None
            for pos in range(idx, len(raw_text)):
                ch = raw_text[pos]
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = pos + 1
                        break
            if end is None:
                raise RuntimeError('Could not parse embedded sales order grid payload.')
            payload = json.loads(raw_text[idx:end])['config']['data']

    items = payload.get('items', [])
    total_records = payload.get('totalRecords')
    orders = []
    for item in items:
        actions = item.get('actions') or {}
        view = actions.get('view') or {}
        href = view.get('href')
        orders.append({
            'entity_id': str(item.get('entity_id')) if item.get('entity_id') is not None else None,
            'increment_id': str(item.get('increment_id')) if item.get('increment_id') is not None else None,
            'created_at': item.get('created_at'),
            'status': item.get('status'),
            'billing_name': item.get('billing_name'),
            'view_url': urljoin(self.page.url, href) if href else None,
        })

    is_complete_page = False
    if isinstance(total_records, int) and page_number == 1 and total_records <= len(orders):
        is_complete_page = True

    return {
        'orders': orders,
        'page_number': page_number,
        'page_size': page_size,
        'total_records': total_records,
        'is_complete_page': is_complete_page,
        'status': status,
    }
