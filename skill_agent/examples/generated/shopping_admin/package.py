"""Generated candidate package; not promoted."""

class ShoppingAdminAdmin:

    def __init__(self, page):
        self.page = page

    def login_admin_http(self, base_url, username, password):
        from urllib.parse import urlencode
        from urllib.request import build_opener, HTTPCookieProcessor, Request
        from http.cookiejar import CookieJar
        import re
        admin_url = base_url.rstrip('/') + '/admin/'
        cookie_jar = CookieJar()
        opener = build_opener(HTTPCookieProcessor(cookie_jar))
        login_html = opener.open(admin_url, timeout=30).read().decode('utf-8', 'ignore')
        match = re.search('name="form_key"\\s+type="hidden"\\s+value="([^"]+)"', login_html)
        if not match:
            raise ValueError('Could not find Magento form_key on login page')
        form_key = match.group(1)
        payload = urlencode({'form_key': form_key, 'login[username]': username, 'login[password]': password}).encode()
        request = Request(admin_url, data=payload, headers={'Content-Type': 'application/x-www-form-urlencoded'})
        response = opener.open(request, timeout=30)
        dashboard_html = response.read().decode('utf-8', 'ignore')
        return {'authenticated_url': response.geturl(), 'dashboard_contains_pending_reviews_link': 'Pending Reviews' in dashboard_html, 'dashboard_contains_all_reviews_link': 'All Reviews' in dashboard_html}

    async def login_admin_ui(self, base_url, username, password):
        admin_url = base_url.rstrip('/') + '/admin'
        await self.page.goto(admin_url, wait_until='domcontentloaded', timeout=60000)
        password_fields = self.page.locator('input[type="password"]')
        already_authenticated = await password_fields.count() == 0
        if not already_authenticated:
            await self.page.locator('input[name="login[username]"], input[name="username"], input[type="text"]').first.fill(username)
            await self.page.locator('input[name="login[password]"], input[name="password"], input[type="password"]').first.fill(password)
            button = self.page.get_by_role('button', name='Sign in').first
            if await button.count():
                await button.click()
            else:
                await self.page.locator('input[type="password"]').first.press('Enter')
            await self.page.wait_for_load_state('networkidle')
        return {'final_url': self.page.url, 'already_authenticated': already_authenticated}

class ShoppingAdminOrders:

    def __init__(self, page):
        self.page = page

    async def get_sales_orders_report_rows(self, base_url, period_type, from_date, to_date, show_order_statuses, order_status):
        import calendar
        import re
        report_url = base_url.rstrip('/') + '/admin/reports/report_sales/sales/'
        await self.page.goto(report_url, wait_until='domcontentloaded', timeout=60000)
        await self.page.select_option('#sales_report_period_type', period_type)
        await self.page.select_option('#sales_report_show_order_statuses', show_order_statuses)
        await self.page.select_option('#sales_report_order_statuses', order_status)
        await self.page.fill('#sales_report_from', from_date)
        await self.page.fill('#sales_report_to', to_date)
        await self.page.click('#filter_form_submit')
        await self.page.wait_for_timeout(3500)
        raw_rows = await self.page.locator('table.data-grid tbody tr').evaluate_all("trs => trs.map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()))")
        rows = []
        for raw_row in raw_rows:
            if len(raw_row) < 2:
                continue
            match = re.match('^(\\d+)/(\\d{4})$', raw_row[0])
            if not match:
                continue
            month_number = int(match.group(1))
            year = int(match.group(2))
            try:
                order_count = int(raw_row[1])
            except ValueError:
                continue
            rows.append({'period_label': raw_row[0], 'year': year, 'month_number': month_number, 'month_name': calendar.month_name[month_number] if 1 <= month_number <= 12 else raw_row[0], 'order_count': order_count})
        body_text = await self.page.locator('body').inner_text()
        return {'rows': rows, 'records_found_text_present': 'records found' in body_text.lower()}

class ShoppingAdminReviews:

    def __init__(self, page):
        self.page = page

    async def get_review_detail_record(self, base_url, review_id, review_title):
        detail_url = base_url.rstrip('/') + f'/admin/review/product/edit/id/{review_id}/'
        await self.page.goto(detail_url, wait_until='networkidle', timeout=60000)
        product_name = (await self.page.locator('a[href*="catalog/product/edit"], .admin__field:has-text("Product") .admin__field-value').first.inner_text()).strip()
        checked_id = await self.page.locator('input[type="radio"]:checked').first.get_attribute('id')
        rating_widget_style = await self.page.locator('.rating-box .rating').first.get_attribute('style') or ''
        rating = int(checked_id.split('_')[-1]) if checked_id and checked_id.split('_')[-1].isdigit() else None
        return {'review_id': review_id, 'review_title': review_title, 'product_name': product_name, 'rating': rating, 'rating_widget_style': rating_widget_style}

    def list_review_ids_from_review_listing_page(self, listing_url, cookie_header):
        from urllib.parse import urlparse
        from urllib.request import build_opener, HTTPCookieProcessor, Request
        import re
        opener = build_opener(HTTPCookieProcessor())
        headers = {}
        if cookie_header:
            headers['Cookie'] = cookie_header
        response = opener.open(Request(listing_url, headers=headers), timeout=30)
        html = response.read().decode('utf-8', 'ignore')
        review_ids = sorted(set(re.findall('/admin/review/product/edit/id/(\\d+)/', html)))
        page_count_match = re.search('of\\s+(\\d+)\\s+Next page', re.sub('<[^>]+>', ' ', html), re.I)
        title_match = re.search('<title>(.*?)</title>', html, re.S | re.I)
        parsed = urlparse(listing_url)
        return {'review_ids': review_ids, 'page_count': int(page_count_match.group(1)) if page_count_match else None, 'page_title': title_match.group(1).strip() if title_match else None, 'listing_path': parsed.path}

    async def list_reviews_by_product_name_from_grid(self, base_url, product_name):
        reviews_url = base_url.rstrip('/') + '/admin/review/product/'
        await self.page.goto(reviews_url, wait_until='networkidle', timeout=60000)
        name_filter = self.page.locator('#reviewGrid_filter_name')
        await name_filter.fill(product_name)
        await name_filter.press('Enter')
        await self.page.wait_for_load_state('networkidle')
        matching_rows = self.page.locator('tbody tr', has_text=product_name)
        count = await matching_rows.count()
        rows = []
        for index in range(count):
            row = matching_rows.nth(index)
            review_id = (await row.locator('td').nth(1).inner_text()).strip()
            title = (await row.locator('td').nth(4).inner_text()).strip()
            rows.append({'review_id': review_id, 'title': title})
        return {'product_name': product_name, 'rows': rows, 'visible_row_count': count}

class ShoppingAdminSite:

    def __init__(self, page):
        self.admin = ShoppingAdminAdmin(page)
        self.orders = ShoppingAdminOrders(page)
        self.reviews = ShoppingAdminReviews(page)
