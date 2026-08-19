"""Generated candidate package; not promoted."""

class ShoppingAdminCatalog:

    def __init__(self, page):
        self.page = page

    def list_catalog_products_by_quantity_range_from_admin_grid(self, quantity_from: float, quantity_to: float) -> dict:
        import re

        def _goto(url: str):
            response = self.page.goto(url, wait_until='domcontentloaded')
            try:
                self.page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                self.page.wait_for_timeout(1500)
            return response

        def _login_if_needed() -> None:
            body_text = self.page.locator('body').inner_text()
            if re.search('Username|Sign in|Login|password', body_text, re.I):
                if self.page.locator('input[name="login[username]"]').count() > 0:
                    self.page.locator('input[name="login[username]"]').first.fill('admin')
                if self.page.locator('input[name="login[password]"]').count() > 0:
                    self.page.locator('input[name="login[password]"]').first.fill('admin1234')
                login_button = self.page.locator('button.action-login')
                if login_button.count() > 0:
                    login_button.first.click()
                else:
                    sign_in = self.page.get_by_role('button', name=re.compile('sign in|login', re.I))
                    if sign_in.count() > 0:
                        sign_in.first.click()
                try:
                    self.page.wait_for_load_state('networkidle', timeout=10000)
                except Exception:
                    self.page.wait_for_timeout(3000)

        def _parse_rows() -> list:
            js = '() => {\n                const rows = [];\n                const grid = document.querySelector(\'table[data-role="grid"] tbody\') || document.querySelector(\'table tbody\');\n                if (!grid) return rows;\n                for (const tr of Array.from(grid.querySelectorAll(\'tr\'))) {\n                    const tds = Array.from(tr.querySelectorAll(\'td\')).map(td => (td.innerText || td.textContent || \'\').trim());\n                    if (tds.length >= 10 && tds[6] && tds[8]) {\n                        rows.push({\n                            name: tds[3] || \'\',\n                            sku: tds[6],\n                            quantity: tds[8],\n                            salable: tds[9] || \'\'\n                        });\n                    }\n                }\n                return rows;\n            }'
            return self.page.evaluate(js)
        if quantity_from > quantity_to:
            raise ValueError('quantity_from must be less than or equal to quantity_to')
        _goto('http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin')
        _login_if_needed()
        _goto('http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin/catalog/product/')
        filters_btn = self.page.get_by_role('button', name='Filters')
        if filters_btn.count() > 0:
            filters_btn.first.click()
            self.page.wait_for_timeout(800)
        qty_from_input = self.page.locator('input[name="qty[from]"]').first
        qty_to_input = self.page.locator('input[name="qty[to]"]').first
        qty_from_input.fill(str(quantity_from))
        qty_to_input.fill(str(quantity_to))
        apply_filters = self.page.get_by_role('button', name='Apply Filters')
        if apply_filters.count() == 0:
            raise RuntimeError('Apply Filters button not found on products grid')
        apply_filters.first.click()
        try:
            self.page.wait_for_load_state('networkidle', timeout=10000)
        except Exception:
            self.page.wait_for_timeout(6000)
        return {'records': _parse_rows()}

class ShoppingAdminCustomers:

    def __init__(self, page):
        self.page = page

    def filter_customers_by_billing_phone_in_admin_grid(self, billing_phone: str) -> dict:
        import re

        def _goto(url: str):
            response = self.page.goto(url, wait_until='domcontentloaded')
            try:
                self.page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                self.page.wait_for_timeout(1500)
            return response

        def _login_if_needed() -> None:
            body_text = self.page.locator('body').inner_text()
            if re.search('Username|Sign in|Login|password', body_text, re.I):
                username_candidates = [self.page.get_by_label('Username'), self.page.locator('input[name="login[username]"]'), self.page.locator('input[name="username"]'), self.page.locator('#username'), self.page.locator('input[type="email"]'), self.page.locator('input[type="text"]')]
                password_candidates = [self.page.get_by_label('Password'), self.page.locator('input[name="login[password]"]'), self.page.locator('input[name="password"]'), self.page.locator('input[type="password"]')]
                for loc in username_candidates:
                    try:
                        if loc.count() > 0:
                            loc.first.fill('admin')
                            break
                    except Exception:
                        pass
                for loc in password_candidates:
                    try:
                        if loc.count() > 0:
                            loc.first.fill('admin1234')
                            break
                    except Exception:
                        pass
                login_buttons = [self.page.get_by_role('button', name=re.compile('sign in|login', re.I)), self.page.locator('button[type="submit"]'), self.page.locator('.action-login')]
                for loc in login_buttons:
                    try:
                        if loc.count() > 0:
                            loc.first.click()
                            break
                    except Exception:
                        pass
                try:
                    self.page.wait_for_load_state('networkidle', timeout=10000)
                except Exception:
                    self.page.wait_for_timeout(3000)

        def _open_filters_if_needed() -> None:
            filters_btn = self.page.get_by_role('button', name='Filters')
            try:
                if filters_btn.count() > 0:
                    filters_btn.first.click()
                    self.page.wait_for_timeout(800)
            except Exception:
                pass

        def _parse_rows(phone_value: str) -> list:
            row_texts = self.page.locator('tbody tr').evaluate_all("rows => rows.map(r => (r.innerText || '').trim()).filter(Boolean)")
            customers = []
            for row_text in row_texts:
                if phone_value not in row_text:
                    continue
                parts = [part.strip() for part in row_text.split('\t') if part.strip()]
                name = parts[0] if len(parts) > 0 else None
                email = parts[1] if len(parts) > 1 else None
                customers.append({'name': name, 'email': email, 'billing_phone': phone_value})
            return customers
        _goto('http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin')
        _login_if_needed()
        _goto('http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin/customer/index/')
        clear_all = self.page.get_by_role('button', name='Clear all')
        try:
            if clear_all.count() > 0:
                clear_all.first.click()
                try:
                    self.page.wait_for_load_state('networkidle', timeout=10000)
                except Exception:
                    self.page.wait_for_timeout(1000)
        except Exception:
            pass
        _open_filters_if_needed()
        phone_input = self.page.locator('input[name="billing_telephone"]:visible').first
        phone_input.fill(billing_phone)
        apply_filters = self.page.get_by_role('button', name='Apply Filters')
        if apply_filters.count() == 0:
            raise RuntimeError('Apply Filters button not found on customer grid')
        apply_filters.first.click()
        try:
            self.page.wait_for_load_state('networkidle', timeout=10000)
        except Exception:
            self.page.wait_for_timeout(1500)
        return {'customers': _parse_rows(billing_phone)}

class ShoppingAdminOrders:

    def __init__(self, page):
        self.page = page

    def get_recent_dashboard_orders(self) -> dict:
        import re
        from html import unescape
        html = self.page.content()
        match = re.search('Last Orders</div>\\s*<div class="dashboard-item-content">\\s*<table.*?<tbody>(.*?)</tbody>', html, re.S | re.I)
        if not match:
            raise RuntimeError('Could not locate Last Orders table tbody on current page')
        rows_html = match.group(1)
        row_matches = re.findall('<tr[^>]*title="([^"]+)"[^>]*>\\s*<td[^>]*>(.*?)</td>\\s*<td[^>]*>(.*?)</td>\\s*<td[^>]*>(.*?)</td>\\s*</tr>', rows_html, re.S | re.I)

        def clean(x: str) -> str:
            x = re.sub('<[^>]+>', ' ', x)
            x = unescape(x)
            x = re.sub('\\s+', ' ', x).strip()
            return x
        orders = []
        for (title_url, customer, items, total) in row_matches:
            orders.append({'order_view_url': unescape(title_url), 'customer': clean(customer), 'items': int(clean(items)), 'total': clean(total)})
        return {'orders': orders, 'page_url': self.page.url}

    def list_orders_from_admin_orders_grid_page(self, orders_page_url: str, max_rows: int) -> dict:
        import re
        if not isinstance(orders_page_url, str) or not orders_page_url.strip():
            raise ValueError('orders_page_url must be a non-empty string')
        if not isinstance(max_rows, int) or max_rows < 1:
            raise ValueError('max_rows must be an integer >= 1')
        self.page.goto(orders_page_url, wait_until='domcontentloaded')
        self.page.wait_for_timeout(3000)
        rows = self.page.locator('table.data-grid tbody tr')
        row_count = rows.count()
        limit = min(row_count, max_rows)
        orders = []
        for i in range(limit):
            row = rows.nth(i)
            cells = row.locator('td')
            cell_count = cells.count()
            texts = []
            for j in range(cell_count):
                txt = cells.nth(j).inner_text()
                txt = re.sub('\\s+', ' ', txt).strip()
                texts.append(txt)
            orders.append({'row_index': i + 1, 'order_id': texts[1] if len(texts) > 1 else None, 'purchase_date': texts[3] if len(texts) > 3 else None, 'status': texts[8] if len(texts) > 8 else None, 'cells': texts, 'row_text': ' | '.join(texts)})
        return {'orders': orders, 'page_url': self.page.url}

class ShoppingAdminReviews:

    def __init__(self, page):
        self.page = page

    def export_product_review_report_csv(self, from_date: str, to_date: str) -> dict:
        import csv
        import io
        if not isinstance(from_date, str) or not from_date.strip():
            raise ValueError('from_date must be a non-empty string')
        if not isinstance(to_date, str) or not to_date.strip():
            raise ValueError('to_date must be a non-empty string')
        report_url = 'http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin/reports/report_review/product/'
        self.page.goto(report_url, wait_until='domcontentloaded')
        self.page.wait_for_load_state('networkidle')
        self.page.fill('input[name="created_at[from]"]', from_date)
        self.page.fill('input[name="created_at[to]"]', to_date)
        self.page.get_by_role('button', name='Search').click()
        self.page.wait_for_load_state('networkidle')
        export_url = self.page.locator('select[name="gridProducts_export"]').input_value()
        if not export_url:
            raise RuntimeError('Report export URL was empty after applying filters')
        response = self.page.context.request.get(export_url)
        if response.status != 200:
            raise RuntimeError(f'Export request failed with status {response.status}')
        csv_text = response.text()
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        report_rows = []
        for row in rows:
            if 'Reviews' not in row:
                raise RuntimeError('CSV export did not include Reviews column')
            parsed_row = {'reviews': int(row['Reviews'])}
            if 'Product' in row:
                parsed_row['product'] = row.get('Product', '')
            if 'Last Review' in row:
                parsed_row['last_review'] = row.get('Last Review', '')
            report_rows.append(parsed_row)
        return {'report_rows': report_rows, 'filtered_report_url': self.page.url, 'export_url': export_url}

    def get_admin_reviews_total_count_via_http_session(self, base_url: str, username: str, password: str) -> dict:
        import html
        import http.cookiejar
        import re
        import urllib.parse
        import urllib.request
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError('base_url must be a non-empty string')
        if not isinstance(username, str) or not username:
            raise ValueError('username must be a non-empty string')
        if not isinstance(password, str) or not password:
            raise ValueError('password must be a non-empty string')
        base_url = base_url.rstrip('/')
        start_url = base_url + '/admin'
        reviews_url = base_url + '/admin/review/product/index/'
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        login_resp = opener.open(start_url)
        login_html = login_resp.read().decode('utf-8', 'ignore')
        form_inputs = dict(re.findall('<input[^>]+name=["\\\']([^"\\\']+)["\\\'][^>]*value=["\\\']([^"\\\']*)["\\\']', login_html, re.I))
        form_inputs['login[username]'] = username
        form_inputs['login[password]'] = password
        dashboard_req = urllib.request.Request(start_url, data=urllib.parse.urlencode(form_inputs).encode())
        dashboard_resp = opener.open(dashboard_req)
        dashboard_html = dashboard_resp.read().decode('utf-8', 'ignore')
        dashboard_text = re.sub('<script.*?</script>|<style.*?</style>', ' ', dashboard_html, flags=re.I | re.S)
        dashboard_text = re.sub('<[^>]+>', ' ', dashboard_text)
        dashboard_text = re.sub('\\s+', ' ', html.unescape(dashboard_text)).strip()
        if 'Dashboard / Magento Admin' not in dashboard_html and 'Dashboard' not in dashboard_text:
            raise RuntimeError('Login did not reach dashboard')
        reviews_resp = opener.open(reviews_url)
        reviews_html = reviews_resp.read().decode('utf-8', 'ignore')
        reviews_text = re.sub('<script.*?</script>|<style.*?</style>', ' ', reviews_html, flags=re.I | re.S)
        reviews_text = re.sub('<[^>]+>', ' ', reviews_text)
        reviews_text = re.sub('\\s+', ' ', html.unescape(reviews_text)).strip()
        match = re.search('(\\d+)\\s+records\\s+found', reviews_text, re.I)
        if not match:
            raise RuntimeError('Could not find total review record count on All Reviews page')
        title_match = re.search('<title>(.*?)</title>', reviews_html, re.I | re.S)
        page_title = html.unescape(title_match.group(1).strip()) if title_match else ''
        return {'reviews_total_count': int(match.group(1)), 'reviews_url': reviews_resp.geturl(), 'reviews_status': getattr(reviews_resp, 'status', None), 'page_title': page_title}

    def get_pending_review_grid_summary(self, username: str, password: str) -> dict:
        import http.cookiejar
        import re
        import urllib.parse
        import urllib.request
        if not isinstance(username, str) or not username:
            raise ValueError('username must be a non-empty string')
        if not isinstance(password, str) or not password:
            raise ValueError('password must be a non-empty string')
        base = 'http://GCRSANDBOX410.redmond.corp.microsoft.com:7780'
        login_url = base + '/admin'
        pending_url = base + '/admin/review/product/pending/'
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        resp = opener.open(login_url)
        login_html = resp.read().decode('utf-8', 'ignore')
        form_key_match = re.search('name="form_key" type="hidden" value="([^"]+)"', login_html)
        if not form_key_match:
            raise RuntimeError('Could not extract login form_key')
        form_key = form_key_match.group(1)
        post = urllib.parse.urlencode({'form_key': form_key, 'login[username]': username, 'login[password]': password}).encode()
        login_resp = opener.open(login_url, post)
        login_resp.read().decode('utf-8', 'ignore')
        resp = opener.open(pending_url)
        final_url = resp.geturl()
        pending_html = resp.read().decode('utf-8', 'ignore')
        m = re.search('id="reviewGrid-total-count"[^>]*>\\s*(\\d+)\\s*<', pending_html)
        if not m:
            raise RuntimeError('Could not find reviewGrid-total-count on Pending Reviews page')
        return {'review_status': 'pending', 'total_count': int(m.group(1)), 'page_url': final_url, 'authenticated': True}

    async def get_product_review_details(self, review_urls: list[str] | None=None, review_ids: list[int] | None=None) -> dict:
        import re
        base = 'http://gcrsandbox410.redmond.corp.microsoft.com:7780'
        page = self.page
        if review_urls is None:
            review_urls = []
        if review_ids is None:
            review_ids = []
        if not isinstance(review_urls, list) or not all((isinstance(x, str) and x.strip() for x in review_urls)):
            raise ValueError('review_urls must be a list of non-empty strings')
        if not isinstance(review_ids, list) or not all((isinstance(x, int) for x in review_ids)):
            raise ValueError('review_ids must be a list of integers')
        if not review_urls and (not review_ids):
            return {'records': []}

        async def _goto(url: str):
            response = await page.goto(url, wait_until='domcontentloaded')
            try:
                await page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                await page.wait_for_timeout(1200)
            return response

        async def _ensure_logged_in() -> None:
            await _goto(f'{base}/admin')
            try:
                body = (await page.locator('body').inner_text()).lower()
            except Exception:
                body = ''
            if re.search('username|sign in|login|password', body, re.I):
                user_locators = [page.locator('input[name="login[username]"]'), page.locator('input[name="username"]'), page.locator('#username'), page.locator('input[type="text"]')]
                pass_locators = [page.locator('input[name="login[password]"]'), page.locator('input[name="password"]'), page.locator('input[type="password"]')]
                for loc in user_locators:
                    try:
                        if await loc.count() > 0:
                            await loc.first.fill('admin')
                            break
                    except Exception:
                        pass
                for loc in pass_locators:
                    try:
                        if await loc.count() > 0:
                            await loc.first.fill('admin1234')
                            break
                    except Exception:
                        pass
                login_buttons = [page.locator('button.action-login'), page.locator('button[type="submit"]'), page.get_by_role('button', name=re.compile('sign in|login', re.I))]
                for loc in login_buttons:
                    try:
                        if await loc.count() > 0:
                            await loc.first.click()
                            break
                    except Exception:
                        pass
                try:
                    await page.wait_for_load_state('networkidle', timeout=10000)
                except Exception:
                    await page.wait_for_timeout(2000)

        async def _read_optional_value(selector: str):
            loc = page.locator(selector).first
            if await loc.count() == 0:
                return None
            try:
                return await loc.input_value()
            except Exception:
                return None

        async def _read_product_text() -> str:
            product_locator = page.locator('div.admin__field:has(label:text("Product"))').first
            try:
                if await product_locator.count() > 0:
                    return ' '.join((await product_locator.inner_text() or '').split())
            except Exception:
                pass
            return ''

        async def _read_rating() -> int:
            rating = 0
            for i in range(1, 6):
                try:
                    loc = page.locator(f'#Rating_{i}')
                    if await loc.count() > 0 and await loc.is_checked():
                        rating = i
                except Exception:
                    pass
            return rating
        targets = []
        for rid in review_ids:
            targets.append({'review_id': rid, 'target_url': f'{base}/admin/review/product/edit/id/{rid}/'})
        for url in review_urls:
            target = url if url.startswith('http') else base + url
            targets.append({'review_id': None, 'target_url': target})
        await _ensure_logged_in()
        records = []
        for item in targets:
            response = await _goto(item['target_url'])
            nickname = await _read_optional_value('#nickname, input[name="nickname"]')
            title = await _read_optional_value('#title, input[name="title"]')
            review_text = await _read_optional_value('#detail, textarea[name="detail"]')
            status_value = await _read_optional_value('#status_id')
            product = await _read_product_text()
            rating = await _read_rating()
            if nickname is None or title is None or review_text is None:
                raise RuntimeError(f'Review detail form fields not available on loaded page: {page.url}')
            records.append({'review_id': item['review_id'], 'review_url': page.url, 'http_status': response.status if response else None, 'product': product, 'title': title, 'nickname': nickname, 'review': review_text, 'rating': rating, 'status_id': status_value})
        return {'records': records}

    async def get_review_grid_record_count_by_status(self, status: str) -> dict:
        import re
        if not isinstance(status, str) or not status.strip():
            raise ValueError('status must be a non-empty string')
        status = status.strip()
        base = 'http://gcrsandbox410.redmond.corp.microsoft.com:7780'
        page = self.page

        async def _goto(url: str):
            await page.goto(url, wait_until='domcontentloaded')
            try:
                await page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                await page.wait_for_timeout(1500)

        async def _ensure_logged_in() -> None:
            await _goto(f'{base}/admin')
            try:
                body = (await page.locator('body').inner_text()).lower()
            except Exception:
                body = ''
            if re.search('username|sign in|login|password', body, re.I):
                user_locators = [page.locator('input[name="login[username]"]'), page.locator('input[name="username"]'), page.locator('#username'), page.locator('input[type="text"]')]
                pass_locators = [page.locator('input[name="login[password]"]'), page.locator('input[name="password"]'), page.locator('input[type="password"]')]
                for loc in user_locators:
                    try:
                        if await loc.count() > 0:
                            await loc.first.fill('admin')
                            break
                    except Exception:
                        pass
                for loc in pass_locators:
                    try:
                        if await loc.count() > 0:
                            await loc.first.fill('admin1234')
                            break
                    except Exception:
                        pass
                login_buttons = [page.locator('button.action-login'), page.locator('button[type="submit"]'), page.get_by_role('button', name=re.compile('sign in|login', re.I))]
                for loc in login_buttons:
                    try:
                        if await loc.count() > 0:
                            await loc.first.click()
                            break
                    except Exception:
                        pass
                try:
                    await page.wait_for_load_state('networkidle', timeout=10000)
                except Exception:
                    await page.wait_for_timeout(2000)
        await _ensure_logged_in()
        await _goto(f'{base}/admin/review/product/index/')
        used_filter = False
        select_by_id = page.locator('#reviewGrid_filter_status')
        if await select_by_id.count() > 0:
            await select_by_id.first.select_option(label=status)
            used_filter = True
        else:
            rows = page.locator('table.data-grid tr')
            if await rows.count() >= 2:
                filter_row = rows.nth(1)
                status_select = filter_row.locator('select').nth(1)
                if await status_select.count() > 0:
                    await status_select.select_option(label=status)
                    used_filter = True
        if not used_filter:
            raise RuntimeError('Status filter control not available on reviews grid')
        search_button = page.get_by_role('button', name='Search')
        if await search_button.count() == 0:
            raise RuntimeError('Search button not found on reviews grid')
        await search_button.first.click()
        try:
            await page.wait_for_load_state('networkidle', timeout=10000)
        except Exception:
            await page.wait_for_timeout(2000)
        summary_texts = []
        try:
            summary_texts = await page.locator('.admin__data-grid-header .admin__control-support-text').all_inner_texts()
        except Exception:
            summary_texts = []
        summary_text = ' | '.join((t.strip() for t in summary_texts if t and t.strip()))
        body_text = await page.locator('body').inner_text()
        match = re.search('(\\d+)\\s+records\\s+found', summary_text, re.I)
        if not match:
            match = re.search('(\\d+)\\s+records\\s+found', body_text, re.I)
        if not match:
            raise RuntimeError('Could not parse filtered review grid record count')
        return {'status': status, 'record_count': int(match.group(1)), 'summary_text': summary_text, 'grid_url': page.url}

    def list_reviews_by_created_date_range_from_reviews_grid(self, start_date: str, end_date: str) -> dict:
        import re

        def _goto(url: str):
            response = self.page.goto(url, wait_until='domcontentloaded')
            try:
                self.page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                self.page.wait_for_timeout(1500)
            return response

        def _login_if_needed() -> None:
            body_text = self.page.locator('body').inner_text()
            if re.search('Username|Sign in|Login|password', body_text, re.I):
                field_values = [('input[name="username"]', 'admin'), ('input[name="password"]', 'admin1234'), ('input[name="login[username]"]', 'admin'), ('input[name="login[password]"]', 'admin1234')]
                for (selector, value) in field_values:
                    loc = self.page.locator(selector)
                    try:
                        if loc.count() > 0:
                            loc.first.fill(value)
                    except Exception:
                        pass
                sign_in = self.page.get_by_role('button', name=re.compile('sign in|login', re.I))
                if sign_in.count() > 0:
                    sign_in.first.click()
                else:
                    submit = self.page.locator('button[type="submit"]')
                    if submit.count() > 0:
                        submit.first.click()
                try:
                    self.page.wait_for_load_state('networkidle', timeout=10000)
                except Exception:
                    self.page.wait_for_timeout(1500)

        def _parse_records() -> list:
            js = '() => {\n                const records = [];\n                const tbody = document.querySelector(\'table[data-role="grid"] tbody\') || document.querySelector(\'table tbody\');\n                if (!tbody) return records;\n                const headers = Array.from(document.querySelectorAll(\'table thead th\')).map(th => (th.innerText || th.textContent || \'\').trim().toLowerCase());\n                for (const tr of Array.from(tbody.querySelectorAll(\'tr\'))) {\n                    const cells = Array.from(tr.querySelectorAll(\'td\')).map(td => (td.innerText || td.textContent || \'\').trim());\n                    if (!cells.length) continue;\n                    const record = { row_text: cells.join(\' | \') };\n                    for (let i = 0; i < Math.min(headers.length, cells.length); i++) {\n                        const h = headers[i];\n                        const v = cells[i];\n                        if (!h) continue;\n                        if (h.includes(\'created\')) record.created_at = v;\n                        else if (h === \'id\' || h.endsWith(\' id\')) record.review_id = v;\n                        else if (h.includes(\'title\')) record.title = v;\n                        else if (h.includes(\'nickname\')) record.nickname = v;\n                        else if (h.includes(\'review\')) record.review_text = v;\n                        else if (h.includes(\'status\')) record.status = v;\n                        else if (h.includes(\'sku\')) record.sku = v;\n                        else if (h.includes(\'product\')) record.product = v;\n                        else if (h.includes(\'visibility\')) record.visibility = v;\n                        else if (h.includes(\'type\')) record.review_type = v;\n                    }\n                    records.push(record);\n                }\n                return records;\n            }'
            return self.page.evaluate(js)
        _goto('http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin')
        _login_if_needed()
        _goto('http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin/review/product/index/')
        from_input = self.page.locator('input[name="created_at[from]"]').first
        to_input = self.page.locator('input[name="created_at[to]"]').first
        from_input.fill(start_date)
        to_input.fill(end_date)
        search_button = self.page.get_by_role('button', name='Search')
        if search_button.count() == 0:
            raise RuntimeError('Search button not found on reviews grid')
        search_button.first.click()
        try:
            self.page.wait_for_load_state('networkidle', timeout=10000)
        except Exception:
            self.page.wait_for_timeout(1000)
        body_text = self.page.locator('body').inner_text()
        count_match = re.search('(\\d+) records found', body_text)
        summary_count = int(count_match.group(1)) if count_match else None
        return {'records': _parse_records(), 'applied_filters': {'start_date': start_date, 'end_date': end_date}, 'summary_count': summary_count, 'source_page': self.page.url}

    async def search_product_reviews_by_product_name(self, product_name: str) -> dict:
        import re
        if not isinstance(product_name, str) or not product_name.strip():
            raise ValueError('product_name must be a non-empty string')
        base = 'http://gcrsandbox410.redmond.corp.microsoft.com:7780'
        page = self.page

        async def _goto(url: str):
            await page.goto(url, wait_until='domcontentloaded')
            try:
                await page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                await page.wait_for_timeout(1500)

        async def _ensure_logged_in() -> None:
            await _goto(f'{base}/admin')
            try:
                body = (await page.locator('body').inner_text()).lower()
            except Exception:
                body = ''
            if re.search('username|sign in|login|password', body, re.I):
                user_locators = [page.locator('input[name="login[username]"]'), page.locator('input[name="username"]'), page.locator('#username'), page.locator('input[type="text"]')]
                pass_locators = [page.locator('input[name="login[password]"]'), page.locator('input[name="password"]'), page.locator('input[type="password"]')]
                for loc in user_locators:
                    try:
                        if await loc.count() > 0:
                            await loc.first.fill('admin')
                            break
                    except Exception:
                        pass
                for loc in pass_locators:
                    try:
                        if await loc.count() > 0:
                            await loc.first.fill('admin1234')
                            break
                    except Exception:
                        pass
                login_buttons = [page.locator('button.action-login'), page.locator('button[type="submit"]'), page.get_by_role('button', name=re.compile('sign in|login', re.I))]
                for loc in login_buttons:
                    try:
                        if await loc.count() > 0:
                            await loc.first.click()
                            break
                    except Exception:
                        pass
                try:
                    await page.wait_for_load_state('networkidle', timeout=10000)
                except Exception:
                    await page.wait_for_timeout(2500)
        await _ensure_logged_in()
        await _goto(f'{base}/admin/review/product/index/')
        filter_input = page.locator('#reviewGrid_filter_name').first
        if await filter_input.count() == 0:
            raise RuntimeError('Product-name filter input not found on reviews grid')
        await filter_input.fill(product_name)
        search_button = page.get_by_role('button', name='Search')
        if await search_button.count() == 0:
            raise RuntimeError('Search button not found on reviews grid')
        await search_button.first.click()
        try:
            await page.wait_for_load_state('networkidle', timeout=10000)
        except Exception:
            await page.wait_for_timeout(2500)
        rows = page.locator('#reviewGrid_table tbody tr, table.data-grid tbody tr, table[data-role="grid"] tbody tr')
        row_count = await rows.count()
        records = []
        reviews = []
        for idx in range(row_count):
            row = rows.nth(idx)
            cells = row.locator('td')
            cell_count = await cells.count()
            cell_texts = []
            for cell_idx in range(cell_count):
                txt = await cells.nth(cell_idx).inner_text()
                cell_texts.append(' '.join((txt or '').split()))
            edit_link = row.locator('a').filter(has_text='Edit').first
            detail_url = None
            try:
                if await edit_link.count() > 0:
                    href = await edit_link.get_attribute('href')
                    if href:
                        detail_url = href if href.startswith('http') else base + href
            except Exception:
                detail_url = None
            product_name_value = cell_texts[0] if len(cell_texts) > 0 and cell_texts[0] else None
            records.append({'product_name': product_name_value, 'detail_url': detail_url, 'cells': cell_texts})
            if detail_url:
                reviews.append({'edit_url': detail_url, 'link_text': 'Edit'})
        return {'records': records, 'reviews': reviews, 'source_page': page.url}

class ShoppingAdminSite:

    def __init__(self, page):
        self.catalog = ShoppingAdminCatalog(page)
        self.customers = ShoppingAdminCustomers(page)
        self.orders = ShoppingAdminOrders(page)
        self.reviews = ShoppingAdminReviews(page)
