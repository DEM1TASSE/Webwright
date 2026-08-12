"""Generated candidate package; not promoted."""

class ShoppingAdminCustomers:

    def __init__(self, page):
        self.page = page

    async def get_customer_detail_from_admin_url(self, customer_edit_url: str) -> dict:
        import re
        if not customer_edit_url:
            raise ValueError('customer_edit_url is required.')
        await self.page.goto(customer_edit_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        current_url = self.page.url
        body_text = await self.page.locator('body').inner_text()
        email = None
        email_match = re.search('([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,})', body_text)
        if email_match:
            email = email_match.group(1)
        return {'customer_edit_url': current_url, 'email': email}

class ShoppingAdminOrders:

    def __init__(self, page):
        self.page = page

    async def get_bestsellers_report_csv(self, period_type: str, from_date: str, to_date: str, show_empty_rows: int=0) -> dict:
        import base64
        import csv
        import io
        import re
        from html import unescape
        from urllib.parse import urlencode, urljoin
        if show_empty_rows not in (0, 1):
            raise ValueError('show_empty_rows must be 0 or 1')
        params = urlencode({'period_type': period_type, 'from': from_date, 'to': to_date, 'show_empty_rows': show_empty_rows})
        encoded = base64.b64encode(params.encode()).decode().replace('+', '-').replace('/', '_')
        report_url = f'/admin/reports/report_sales/bestsellers/filter/{encoded}/'
        await self.page.goto(report_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        html = await self.page.content()
        match = re.search('<option value="([^"]*exportBestsellersCsv[^"]*)"', html)
        if not match:
            raise RuntimeError('Could not find bestseller export CSV URL on report page.')
        export_csv_url = urljoin(self.page.url, unescape(match.group(1)))
        response = await self.page.context.request.get(export_csv_url)
        csv_text = await response.text()
        reader = csv.reader(io.StringIO(csv_text))
        all_rows = list(reader)
        column_headers = all_rows[0] if all_rows else []
        rows = []
        for row in all_rows[1:]:
            if len(row) < 4:
                continue
            try:
                order_quantity = float(row[3])
            except Exception:
                continue
            rows.append({'interval': row[0].strip(), 'product_name': row[1].strip(), 'price': row[2].strip(), 'order_quantity': order_quantity})
        return {'report_url': self.page.url, 'export_csv_url': export_csv_url, 'column_headers': column_headers, 'rows': rows, 'completeness': {'source': 'bestsellers_csv_export', 'filtered_report': True, 'export_based': True}}

    async def get_order_detail(self, order_url: str | None=None, order_id: str | None=None) -> dict:
        import re
        from urllib.parse import urljoin
        if not order_url and (not order_id):
            raise ValueError('Provide order_url or order_id')
        if order_url and order_id:
            raise ValueError('Provide only one of order_url or order_id')
        target_url = order_url or f'/admin/sales/order/view/order_id/{order_id}/'
        await self.page.goto(target_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')

        def _strip_tags(text: str) -> str:
            text = re.sub('<br\\s*/?>', ' ', text, flags=re.I)
            text = re.sub('<.*?>', ' ', text, flags=re.S)
            text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
            return ' '.join(text.split())
        html = await self.page.content()
        body_text = await self.page.locator('body').inner_text()
        current_url = self.page.url
        title_match = re.search('<title>(.*?)</title>', html, re.S | re.I)
        order_title = _strip_tags(title_match.group(1)) if title_match else None
        date_match = re.search('Order Date</th>\\s*<td[^>]*>\\s*(.*?)\\s*</td>', html, re.S | re.I)
        order_date = _strip_tags(date_match.group(1)) if date_match else None
        status_match = re.search('Order Status</th>\\s*<td[^>]*>\\s*(.*?)\\s*</td>', html, re.S | re.I)
        order_status = _strip_tags(status_match.group(1)) if status_match else None
        skus = []
        sku_matches = re.findall('SKU:\\s*([^\\n\\r]+)', body_text)
        for sku in sku_matches:
            sku = sku.strip()
            if sku:
                skus.append({'sku': sku})
        items = []
        for block in re.findall('<tbody[^>]*>(.*?)</tbody>', html, re.S | re.I):
            if 'id="order_item_' not in block:
                continue
            name_match = re.search('<div[^>]*class="product-title"[^>]*>(.*?)</div>', block, re.S | re.I)
            if not name_match:
                continue
            name = _strip_tags(name_match.group(1))
            displayed_money_amounts = re.findall('\\$\\d+[\\d,]*\\.\\d{2}', _strip_tags(block))
            items.append({'name': name, 'displayed_money_amounts': displayed_money_amounts})
        resolved_order_id = str(order_id) if order_id else None
        if resolved_order_id is None:
            id_match = re.search('/order_id/(\\d+)/', current_url)
            if id_match:
                resolved_order_id = id_match.group(1)
        return {'order_id': resolved_order_id, 'order_url': urljoin(current_url, current_url), 'order': {'title': order_title, 'order_date': order_date, 'order_status': order_status}, 'items': items, 'skus': skus, 'is_complete': True}

    async def get_sales_orders_report_rows(self, period_type: str, from_date: str, to_date: str, status_filter_mode: str='all', order_status: str | None=None, include_empty_rows: bool=False) -> dict:
        if status_filter_mode not in ('all', 'specified'):
            raise ValueError("status_filter_mode must be 'all' or 'specified'")
        if status_filter_mode == 'specified' and (not order_status):
            raise ValueError('order_status is required when status_filter_mode is specified')
        await self.page.goto('/admin/reports/report_sales/sales/', wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        await self.page.select_option('#sales_report_period_type', period_type)
        await self.page.fill('#sales_report_from', from_date)
        await self.page.fill('#sales_report_to', to_date)
        await self.page.select_option('#sales_report_show_order_statuses', '1' if status_filter_mode == 'specified' else '0')
        if status_filter_mode == 'specified' and order_status is not None:
            await self.page.select_option('#sales_report_order_statuses', label=order_status)
        await self.page.select_option('#sales_report_show_empty_rows', '0' if include_empty_rows else '1')
        await self.page.click('#filter_form_submit')
        await self.page.wait_for_load_state('networkidle')
        table_text = await self.page.locator('table').first.inner_text()
        lines = [line.strip() for line in table_text.splitlines() if line.strip()]
        rows = []
        for line in lines:
            parts = [part.strip() for part in line.split('\t')]
            if len(parts) < 2:
                continue
            if parts[0].lower() == 'period' or parts[0] == 'Total':
                continue
            try:
                orders_count = int(parts[1].replace(',', ''))
            except Exception:
                continue
            rows.append({'period_label': parts[0], 'orders_count': orders_count})
        return {'report_url': self.page.url, 'period_type': period_type, 'from_date': from_date, 'to_date': to_date, 'status_filter_mode': status_filter_mode, 'order_status': order_status, 'include_empty_rows': include_empty_rows, 'rows': rows, 'completeness': 'report_rows_visible_on_page'}

    async def list_sales_orders_from_grid(self, status: str | None=None, page_number: int=1, page_size: int=200) -> dict:
        import json
        import re
        from urllib.parse import urlencode, urljoin
        if page_number < 1:
            raise ValueError('page_number must be >= 1')
        if page_size < 1:
            raise ValueError('page_size must be >= 1')
        await self.page.goto('/admin/sales/order/', wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        params = {'namespace': 'sales_order_grid', 'paging[pageSize]': str(page_size), 'paging[current]': str(page_number), 'isAjax': 'true'}
        if status is not None:
            params['filters[status]'] = status
        render_url = '/admin/mui/index/render/?' + urlencode(params)
        response = await self.page.context.request.get(urljoin(self.page.url, render_url), headers={'X-Requested-With': 'XMLHttpRequest', 'Referer': urljoin(self.page.url, '/admin/sales/order/')})
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
            script_match = re.search('<script type="text/x-magento-init">(.*?)</script>', raw_text, re.S)
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
            orders.append({'entity_id': str(item.get('entity_id')) if item.get('entity_id') is not None else None, 'increment_id': str(item.get('increment_id')) if item.get('increment_id') is not None else None, 'created_at': item.get('created_at'), 'status': item.get('status'), 'billing_name': item.get('billing_name'), 'view_url': urljoin(self.page.url, href) if href else None})
        is_complete_page = False
        if isinstance(total_records, int) and page_number == 1 and (total_records <= len(orders)):
            is_complete_page = True
        return {'orders': orders, 'page_number': page_number, 'page_size': page_size, 'total_records': total_records, 'is_complete_page': is_complete_page, 'status': status}

class ShoppingAdminReviews:

    def __init__(self, page):
        self.page = page

    async def get_product_review_detail(self, review_id: int) -> dict:
        import re
        from urllib.parse import urljoin
        if review_id < 1:
            raise ValueError('review_id must be >= 1')
        await self.page.goto(f'/admin/review/product/edit/id/{review_id}/', wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')

        async def _first_input_value(selectors):
            for selector in selectors:
                locator = self.page.locator(selector)
                if await locator.count():
                    try:
                        value = (await locator.first.input_value()).strip()
                        if value:
                            return value
                    except Exception:
                        pass
            return None

        async def _first_text(selectors):
            for selector in selectors:
                locator = self.page.locator(selector)
                if await locator.count():
                    try:
                        value = (await locator.first.inner_text()).strip()
                        if value:
                            return value
                    except Exception:
                        pass
            return None
        review_url = self.page.url
        nickname = await _first_input_value(['#nickname', 'input[name="nickname"]'])
        title = await _first_input_value(['#title', 'input[name="title"]'])
        detail_text = await _first_input_value(['#detail', 'textarea[name="detail"]'])
        product_name = await _first_text(['#product_name', 'a[href*="/catalog/product/edit/id/"]'])
        rating = None
        checked_rating = self.page.locator('input[type="radio"][name^="ratings"]:checked').first
        if await checked_rating.count():
            rating_id = await checked_rating.get_attribute('id')
            if rating_id:
                match = re.search('Rating_(\\d+)', rating_id)
                if match:
                    rating = int(match.group(1))
        customer_edit_url = None
        customer_link = self.page.locator('a[href*="/admin/customer/index/edit/id/"]').first
        if await customer_link.count():
            href = await customer_link.get_attribute('href')
            if href:
                customer_edit_url = urljoin(review_url, href)
        body_text = await self.page.locator('body').inner_text()
        displayed_customer_email = None
        email_match = re.search('([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,})', body_text)
        if email_match:
            displayed_customer_email = email_match.group(1)
        return {'review_id': review_id, 'review_url': review_url, 'product_name': product_name, 'nickname': nickname, 'title': title, 'detail_text': detail_text, 'rating': rating, 'customer_edit_url': customer_edit_url, 'displayed_customer_email': displayed_customer_email}

    async def search_product_reviews(self, detail_query: str | None=None, product_name_query: str | None=None, page_number: int=1) -> dict:
        import re
        from urllib.parse import urljoin
        if detail_query is None and product_name_query is None:
            raise ValueError('Provide at least one filter: detail_query or product_name_query.')
        if page_number < 1:
            raise ValueError('page_number must be >= 1')
        await self.page.goto('/admin/review/product/index/', wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        if detail_query is not None:
            detail_input = self.page.locator('#reviewGrid_filter_detail')
            if not await detail_input.count():
                raise RuntimeError('Review detail filter input not found.')
            await detail_input.fill(detail_query)
        if product_name_query is not None:
            product_input = self.page.locator('#reviewGrid_filter_name')
            if not await product_input.count():
                raise RuntimeError('Product filter input not found.')
            await product_input.fill(product_name_query)
        await self.page.get_by_role('button', name='Search').click()
        await self.page.wait_for_load_state('networkidle')
        if page_number > 1:
            pager_link = self.page.locator(f'a[href*="page/{page_number}"]').first
            if not await pager_link.count():
                raise RuntimeError(f'Requested page_number {page_number} is not available from the current result set.')
            await pager_link.click()
            await self.page.wait_for_load_state('networkidle')
        body_text = await self.page.locator('body').inner_text()
        total_match = re.search('(\\d+)\\s+records found', body_text)
        reported_total_matches = int(total_match.group(1)) if total_match else None
        table_rows = self.page.locator('#reviewGrid_table tbody tr')
        row_count = await table_rows.count()
        records = []
        for i in range(row_count):
            row = table_rows.nth(i)
            row_text_raw = await row.inner_text()
            row_text = ' | '.join((part.strip() for part in row_text_raw.splitlines() if part.strip()))
            edit_url = None
            review_id = None
            edit_link = row.locator('a[href*="/admin/review/product/edit/id/"]').first
            if await edit_link.count():
                href = await edit_link.get_attribute('href')
                if href:
                    edit_url = urljoin(self.page.url, href)
                    id_match = re.search('/admin/review/product/edit/id/(\\d+)/', edit_url)
                    if id_match:
                        review_id = int(id_match.group(1))
            records.append({'review_id': review_id, 'edit_url': edit_url, 'row_text': row_text})
        is_complete = False
        if reported_total_matches is not None and reported_total_matches <= len(records) and (page_number == 1):
            is_complete = True
        return {'detail_query': detail_query, 'product_name_query': product_name_query, 'reported_total_matches': reported_total_matches, 'page_number': page_number, 'is_complete': is_complete, 'records': records}

class ShoppingAdminSite:

    def __init__(self, page):
        self.customers = ShoppingAdminCustomers(page)
        self.orders = ShoppingAdminOrders(page)
        self.reviews = ShoppingAdminReviews(page)
