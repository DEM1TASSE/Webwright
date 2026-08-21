"""Generated candidate package; not promoted."""

class ShoppingAdminAuth:

    def __init__(self, page):
        self.page = page

    async def login_admin_dashboard(self, username, password):
        from urllib.parse import urlsplit, urljoin
        origin = f'{urlsplit(self.page.url).scheme}://{urlsplit(self.page.url).netloc}'
        admin_url = urljoin(origin + '/', 'admin')
        response = await self.page.goto(admin_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('domcontentloaded')
        login_form_present = await self.page.locator('input[name="login[username]"], input#username').count() > 0
        login_submitted = False
        if login_form_present:
            await self.page.locator('input[name="login[username]"], input#username').first.fill(username)
            await self.page.locator('input[name="login[password]"], input#login').first.fill(password)
            await self.page.locator('button.action-login, .actions .action-primary, button:has-text("Sign in")').first.click()
            login_submitted = True
            await self.page.wait_for_load_state('domcontentloaded')
            await self.page.wait_for_timeout(1000)
        current_url = self.page.url
        title = await self.page.title()
        page_text = await self.page.locator('body').inner_text()
        is_authenticated = '/dashboard/' in current_url or 'Dashboard / Magento Admin' in title or 'Dashboard / Magento Admin' in page_text
        return {'is_authenticated': bool(is_authenticated), 'current_url': current_url, 'page_title': title, 'login_form_present': bool(login_form_present), 'login_submitted': bool(login_submitted), 'document_status': response.status if response else None}

class ShoppingAdminCatalog:

    def __init__(self, page):
        self.page = page

    async def filter_product_grid_by_quantity_range_and_extract_products(self, min_quantity: float, max_quantity: float) -> dict:
        from urllib.parse import urlsplit, urljoin
        if min_quantity > max_quantity:
            raise ValueError('min_quantity must be less than or equal to max_quantity')
        split = urlsplit(self.page.url)
        origin = f'{split.scheme}://{split.netloc}'
        target_url = urljoin(origin + '/', 'admin/catalog/product/')
        await self.page.goto(target_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        filters_button = self.page.get_by_role('button', name='Filters')
        if not await filters_button.count():
            raise RuntimeError('Filters button was not found on the products grid')
        await filters_button.first.click()
        await self.page.wait_for_timeout(800)
        qty_from = self.page.locator('input[name="qty[from]"]')
        qty_to = self.page.locator('input[name="qty[to]"]')
        if not await qty_from.count() or not await qty_to.count():
            raise RuntimeError('Quantity range filter inputs were not found')
        await qty_from.first.fill(str(min_quantity))
        await qty_to.first.fill(str(max_quantity))
        apply_filters_button = self.page.get_by_role('button', name='Apply Filters')
        if not await apply_filters_button.count():
            raise RuntimeError('Apply Filters button was not found on the products grid')
        await apply_filters_button.first.click()
        await self.page.wait_for_load_state('networkidle')
        await self.page.wait_for_timeout(1000)
        rows = await self.page.evaluate('() => {\n                const out = [];\n                const grid = document.querySelector(\'table[data-role="grid"] tbody\') || document.querySelector(\'table tbody\');\n                if (!grid) return out;\n                for (const tr of Array.from(grid.querySelectorAll(\'tr\'))) {\n                    const tds = Array.from(tr.querySelectorAll(\'td\')).map(td => (td.innerText || td.textContent || \'\').trim());\n                    if (tds.length >= 10 && tds[6] && tds[8]) {\n                        out.push({\n                            name: tds[3] || null,\n                            sku: tds[6],\n                            quantity_text: tds[8],\n                            salable_text: tds[9] || \'\'\n                        });\n                    }\n                }\n                return out;\n            }')
        products = []
        for row in rows:
            quantity_value = None
            try:
                quantity_value = float(str(row.get('quantity_text', '')).strip())
            except Exception:
                quantity_value = None
            products.append({'name': row.get('name'), 'sku': row.get('sku'), 'quantity_text': row.get('quantity_text'), 'quantity_value': quantity_value, 'salable_text': row.get('salable_text')})
        return {'products': products}

class ShoppingAdminCustomers:

    def __init__(self, page):
        self.page = page

    async def search_customers_by_phone_in_admin_grid(self, phone_number: str) -> dict:
        from urllib.parse import urlsplit, urljoin
        import re
        if not phone_number:
            raise ValueError('phone_number is required')
        split = urlsplit(self.page.url)
        origin = f'{split.scheme}://{split.netloc}'
        target_url = urljoin(origin + '/', 'admin/customer/index/')
        await self.page.goto(target_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        phone_input = self.page.locator('input[name="billing_telephone"]:visible')
        if not await phone_input.count():
            raise RuntimeError('Customer billing telephone filter input was not found')
        await phone_input.first.fill(phone_number)
        apply_filters_button = self.page.get_by_role('button', name='Apply Filters')
        if not await apply_filters_button.count():
            raise RuntimeError('Apply Filters button was not found')
        await apply_filters_button.first.click()
        await self.page.wait_for_load_state('networkidle')
        await self.page.wait_for_timeout(1500)
        row_texts = await self.page.locator('tbody tr').evaluate_all("rows => rows.map(r => (r.innerText || '').trim()).filter(t => t)")
        email_pattern = re.compile('^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\\\.[A-Za-z]{2,}$')
        customers = []
        for row_text in row_texts:
            if phone_number not in row_text:
                continue
            parts = [part.strip() for part in row_text.split('\t') if part.strip()]
            name = parts[0] if len(parts) > 0 else None
            email = parts[1] if len(parts) > 1 and email_pattern.match(parts[1]) else None
            parsed_phone_number = None
            for part in parts:
                if part == phone_number:
                    parsed_phone_number = part
                    break
            if parsed_phone_number is None:
                match = re.search(f'(?<!\\d){re.escape(phone_number)}(?!\\d)', row_text)
                if match:
                    parsed_phone_number = match.group(0)
            customers.append({'name': name, 'email': email, 'phone_number': parsed_phone_number})
        return {'customers': customers}

class ShoppingAdminDashboard:

    def __init__(self, page):
        self.page = page

    async def get_dashboard_last_orders(self):
        from html import unescape
        import re
        await self.page.wait_for_load_state('domcontentloaded')
        html = await self.page.content()
        match = re.search('Last Orders</div>\\s*<div class="dashboard-item-content">\\s*<table.*?<tbody>(.*?)</tbody>', html, re.S | re.I)
        if not match:
            return {'orders': []}
        rows_html = match.group(1)
        row_matches = re.findall('<tr[^>]*title="([^"]+)"[^>]*>\\s*<td[^>]*>(.*?)</td>\\s*<td[^>]*>(.*?)</td>\\s*<td[^>]*>(.*?)</td>\\s*</tr>', rows_html, re.S | re.I)

        def clean(x):
            x = re.sub('<[^>]+>', ' ', x)
            x = unescape(x)
            x = re.sub('\\s+', ' ', x).strip()
            return x
        orders = []
        for title_url, customer, items, total in row_matches:
            orders.append({'order_view_url': unescape(title_url), 'customer': clean(customer), 'items': int(clean(items)), 'total_text': clean(total)})
        return {'orders': orders}

class ShoppingAdminOrders:

    def __init__(self, page):
        self.page = page

    async def list_orders_grid_rows(self):
        from urllib.parse import urlsplit, urljoin
        origin = f'{urlsplit(self.page.url).scheme}://{urlsplit(self.page.url).netloc}'
        orders_url = urljoin(origin + '/', 'admin/sales/order/')
        await self.page.goto(orders_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('domcontentloaded')
        rows = self.page.locator('table.data-grid tbody tr')
        count = await rows.count()
        orders = []
        for i in range(count):
            row = rows.nth(i)
            cells = row.locator('td')
            ccount = await cells.count()
            texts = []
            for j in range(ccount):
                txt = ' '.join((await cells.nth(j).inner_text()).split())
                texts.append(txt)
            orders.append({'row_index': i + 1, 'cells_text': texts, 'row_text': ' | '.join(texts), 'order_id_text': texts[1] if len(texts) > 1 else None, 'purchase_date_text': texts[3] if len(texts) > 3 else None, 'status_text': texts[8] if len(texts) > 8 else None})
        return {'orders': orders}

class ShoppingAdminReviews:

    def __init__(self, page):
        self.page = page

    async def export_product_reviews_report_csv(self, created_at_from, created_at_to):
        from urllib.parse import urlsplit, urljoin
        import csv
        import io
        origin = f'{urlsplit(self.page.url).scheme}://{urlsplit(self.page.url).netloc}'
        report_page_url = urljoin(origin + '/', 'admin/reports/report_review/product/')
        await self.page.goto(report_page_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        await self.page.fill('input[name="created_at[from]"]', created_at_from)
        await self.page.fill('input[name="created_at[to]"]', created_at_to)
        await self.page.locator('button[title="Search"]').click()
        await self.page.wait_for_load_state('networkidle')
        export_value = await self.page.locator('select[name="gridProducts_export"]').input_value()
        export_url = urljoin(origin + '/', export_value.lstrip('/')) if export_value else ''
        response = await self.page.context.request.get(export_url)
        csv_text = await response.text()
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        records = []
        for row in rows:
            reviews_count_text = (row.get('Reviews') or '').strip()
            records.append({'product_name': (row.get('Product') or '').strip(), 'sku': (row.get('SKU') or '').strip(), 'reviews_count': int(reviews_count_text), 'reviews_count_text': reviews_count_text, 'last_review_text': (row.get('Last Review') or '').strip()})
        return {'export_url': export_url, 'records': records, 'row_count': len(records)}

    async def get_product_review_detail(self, review_url: str) -> dict:
        from urllib.parse import urlsplit, urljoin
        if not isinstance(review_url, str) or not review_url.strip():
            raise ValueError('review_url must be a non-empty string')
        split = urlsplit(self.page.url)
        if not split.scheme or not split.netloc:
            raise RuntimeError('self.page.url must already be on the shopping_admin site')
        origin = f'{split.scheme}://{split.netloc}'
        target_url = review_url if review_url.startswith('http://') or review_url.startswith('https://') else urljoin(origin + '/', review_url.lstrip('/'))
        response = await self.page.goto(target_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('domcontentloaded')
        await self.page.wait_for_timeout(800)
        nickname_locator = self.page.locator('#nickname, input[name="nickname"]').first
        title_locator = self.page.locator('#title, input[name="title"]').first
        detail_locator = self.page.locator('#detail, textarea[name="detail"]').first
        if await nickname_locator.count() == 0 or await title_locator.count() == 0 or await detail_locator.count() == 0:
            raise RuntimeError('Expected review detail form fields were not found')
        product_text = ''
        product_name = None
        product_locator = self.page.locator('div.admin__field:has(label:text("Product"))')
        if await product_locator.count() > 0:
            product_text = ' '.join((await product_locator.first.inner_text()).split())
            product_name = product_text or None
        rating = 0
        for i in range(1, 6):
            rating_locator = self.page.locator(f'#Rating_{i}')
            if await rating_locator.count() > 0 and await rating_locator.is_checked():
                rating = i
                break
        status_locator = self.page.locator('#status_id').first
        status_id = await status_locator.input_value() if await status_locator.count() > 0 else ''
        return {'url': self.page.url, 'http_status': response.status if response else None, 'product_text': product_text, 'product_name': product_name, 'title': await title_locator.input_value(), 'nickname': await nickname_locator.input_value(), 'review_text': await detail_locator.input_value(), 'rating': rating, 'status_id': status_id}

    async def get_product_review_page_count(self, page_variant: str, username: str=None, password: str=None) -> dict:
        import re
        from urllib.parse import urlsplit, urljoin
        if not isinstance(page_variant, str) or not page_variant.strip():
            raise ValueError('page_variant must be a non-empty string')
        normalized = page_variant.strip().lower()
        variant_map = {'all': {'path': 'admin/review/product/index/', 'kind': 'all_reviews'}, 'all_reviews': {'path': 'admin/review/product/index/', 'kind': 'all_reviews'}, 'pending': {'path': 'admin/review/product/pending/', 'kind': 'pending_reviews'}, 'pending_reviews': {'path': 'admin/review/product/pending/', 'kind': 'pending_reviews'}}
        if normalized not in variant_map:
            raise ValueError('page_variant must be one of: all_reviews, pending_reviews')
        split = urlsplit(self.page.url)
        if not split.scheme or not split.netloc:
            raise RuntimeError('self.page.url must already be on the shopping_admin site')
        origin = f'{split.scheme}://{split.netloc}'
        admin_url = urljoin(origin + '/', 'admin')
        target_url = urljoin(origin + '/', variant_map[normalized]['path'])
        await self.page.goto(admin_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('domcontentloaded')
        username_locator = self.page.locator('input[name="login[username]"], input#username')
        password_locator = self.page.locator('input[name="login[password]"], input#login')
        if await username_locator.count() > 0 or await password_locator.count() > 0:
            if not username or not password:
                raise RuntimeError('Admin credentials are required because the login form is present')
            await username_locator.first.fill(username)
            await password_locator.first.fill(password)
            login_button = self.page.locator('button.action-login, .actions .action-primary, button:has-text("Sign in")').first
            if await login_button.count() == 0:
                raise RuntimeError('Could not locate Magento admin login button')
            await login_button.click()
            await self.page.wait_for_load_state('networkidle')
        response = await self.page.goto(target_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        page_kind = variant_map[normalized]['kind']
        if page_kind == 'pending_reviews':
            count_locator = self.page.locator('#reviewGrid-total-count')
            if not await count_locator.count():
                raise RuntimeError('Pending Product Reviews total-count element is missing')
            count_text = (await count_locator.first.inner_text()).strip()
            match = re.fullmatch('\\d+', count_text)
            if not match:
                raise RuntimeError('Could not parse integer from Pending Product Reviews total-count element')
            count_value = int(match.group(0))
            title = await self.page.title()
            return {'page_variant': 'pending_reviews', 'page_kind': 'pending_reviews', 'review_count': count_value, 'pending_review_count': count_value, 'total_reviews': count_value, 'source_page_url': self.page.url, 'reviews_url': self.page.url, 'reviews_page_title': title, 'display_count_text': count_text, 'document_status': response.status if response else None}
        body_text = await self.page.locator('body').inner_text()
        match = re.search('(\\d+)\\s+records\\s+found', body_text, re.I)
        if not match:
            raise RuntimeError('Could not find total review record count on the All Reviews page')
        count_value = int(match.group(1))
        title = await self.page.title()
        return {'page_variant': 'all_reviews', 'page_kind': 'all_reviews', 'review_count': count_value, 'pending_review_count': count_value, 'total_reviews': count_value, 'source_page_url': self.page.url, 'reviews_url': self.page.url, 'reviews_page_title': title, 'display_count_text': match.group(0), 'document_status': response.status if response else None}

    async def get_review_grid_result_count_by_status(self, status: str, username: str=None, password: str=None) -> dict:
        import re
        from urllib.parse import urlsplit, urljoin
        if not isinstance(status, str) or not status.strip():
            raise ValueError('status must be a non-empty string')
        split = urlsplit(self.page.url)
        if not split.scheme or not split.netloc:
            raise RuntimeError('self.page.url must already be on the shopping_admin site')
        origin = f'{split.scheme}://{split.netloc}'
        admin_url = urljoin(origin + '/', 'admin')
        reviews_url = urljoin(origin + '/', 'admin/review/product/index/')
        await self.page.goto(admin_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('domcontentloaded')
        username_locator = self.page.locator('input[name="login[username]"], input#username')
        password_locator = self.page.locator('input[name="login[password]"], input#login')
        if await username_locator.count() > 0 or await password_locator.count() > 0:
            if not username or not password:
                raise RuntimeError('Admin credentials are required because the login form is present')
            await username_locator.first.fill(username)
            await password_locator.first.fill(password)
            login_button = self.page.locator('button.action-login, .actions .action-primary, button:has-text("Sign in")').first
            if await login_button.count() == 0:
                raise RuntimeError('Could not locate Magento admin login button')
            await login_button.click()
            await self.page.wait_for_load_state('networkidle')
        await self.page.goto(reviews_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        direct_status_select = self.page.locator('#reviewGrid_filter_status')
        if await direct_status_select.count() > 0:
            await direct_status_select.first.select_option(label=status)
        else:
            rows = self.page.locator('table.data-grid tr')
            filter_row = rows.nth(1)
            fallback_select = filter_row.locator('select').nth(1)
            if await fallback_select.count() == 0:
                raise RuntimeError('Could not locate reviews-grid status filter control')
            await fallback_select.select_option(label=status)
        search_button = self.page.get_by_role('button', name='Search')
        if await search_button.count() == 0:
            raise RuntimeError('Search button was not found on the reviews grid')
        await search_button.first.click()
        await self.page.wait_for_load_state('networkidle')
        await self.page.wait_for_timeout(1000)
        summary_texts = await self.page.locator('.admin__data-grid-header .admin__control-support-text').all_inner_texts()
        summary_text = ' | '.join((text.strip() for text in summary_texts if text.strip()))
        body_text = await self.page.locator('body').inner_text()
        match = re.search('(\\d+)\\s+records\\s+found', summary_text, re.I)
        if not match:
            match = re.search('(\\d+)\\s+records\\s+found', body_text, re.I)
        if not match:
            raise RuntimeError(f'Could not extract records-found count for review status {status!r}')
        observed_summary = summary_text if summary_text else match.group(0)
        count = int(match.group(1))
        return {'status_filter': status, 'status': status, 'result_count': count, 'records_found': count, 'summary_text': observed_summary, 'records_found_text': match.group(0), 'grid_url': self.page.url, 'page_url': self.page.url}

    async def list_product_review_grid_rows(self, product_name: str) -> dict:
        from urllib.parse import urlsplit, urljoin
        if not isinstance(product_name, str) or not product_name.strip():
            raise ValueError('product_name must be a non-empty string')
        split = urlsplit(self.page.url)
        if not split.scheme or not split.netloc:
            raise RuntimeError('self.page.url must already be on the shopping_admin site')
        origin = f'{split.scheme}://{split.netloc}'
        target_url = urljoin(origin + '/', 'admin/review/product/index/')
        await self.page.goto(target_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        filter_input = self.page.locator('#reviewGrid_filter_name')
        if await filter_input.count() == 0:
            raise RuntimeError('Product-name filter input was not found on the reviews grid')
        await filter_input.first.fill(product_name)
        search_button = self.page.get_by_role('button', name='Search')
        if await search_button.count() == 0:
            raise RuntimeError('Search button was not found on the reviews grid')
        await search_button.first.click()
        await self.page.wait_for_load_state('networkidle')
        await self.page.wait_for_timeout(1000)
        rows_locator = self.page.locator('#reviewGrid_table tbody tr')
        row_count = await rows_locator.count()
        rows = []
        for idx in range(row_count):
            row = rows_locator.nth(idx)
            row_text = ' '.join((await row.inner_text()).split())
            edit_link = row.locator('a').filter(has_text='Edit').first
            edit_link_text = None
            edit_url = None
            if await edit_link.count() > 0:
                href = await edit_link.get_attribute('href')
                text = ' '.join((await edit_link.inner_text()).split())
                edit_link_text = text or 'Edit'
                if href:
                    edit_url = href if href.startswith('http://') or href.startswith('https://') else urljoin(origin + '/', href.lstrip('/'))
            rows.append({'row_text': row_text, 'edit_link_text': edit_link_text, 'edit_url': edit_url})
        return {'product_name': product_name, 'rows': rows, 'reviews': [{'edit_link_text': row['edit_link_text'], 'edit_url': row['edit_url']} for row in rows if row.get('edit_url')]}

    async def list_product_reviews_by_created_date_range(self, created_from_text: str, created_to_text: str) -> dict:
        from urllib.parse import urlsplit, urljoin
        import re
        if not created_from_text or not created_to_text:
            raise ValueError('created_from_text and created_to_text are required')
        split = urlsplit(self.page.url)
        origin = f'{split.scheme}://{split.netloc}'
        target_url = urljoin(origin + '/', 'admin/review/product/index/')
        await self.page.goto(target_url, wait_until='domcontentloaded')
        await self.page.wait_for_load_state('networkidle')
        from_input = self.page.locator('input[name="created_at[from]"]')
        to_input = self.page.locator('input[name="created_at[to]"]')
        if not await from_input.count() or not await to_input.count():
            raise RuntimeError('Created-date filter inputs were not found on the reviews grid')
        await from_input.first.fill(created_from_text)
        await to_input.first.fill(created_to_text)
        search_button = self.page.get_by_role('button', name='Search')
        if not await search_button.count():
            raise RuntimeError('Search button was not found on the reviews grid')
        await search_button.first.click()
        await self.page.wait_for_load_state('networkidle')
        await self.page.wait_for_timeout(1000)
        body_text = await self.page.locator('body').inner_text()
        summary_match = re.search('(\\d+) records found', body_text)
        summary_text = summary_match.group(0) if summary_match else None
        total_count = int(summary_match.group(1)) if summary_match else None
        records = await self.page.locator('tbody tr').evaluate_all("rows => rows.map(r => {\n                const cells = Array.from(r.querySelectorAll('td')).map(td => (td.innerText || '').trim());\n                return cells.some(Boolean) ? {cells} : null;\n            }).filter(Boolean)")
        reviews = []
        for record in records:
            reviews.append({'cells': record.get('cells', [])})
        return {'reviews': reviews, 'summary_text': summary_text, 'total_count': total_count, 'grid_url': self.page.url}

class ShoppingAdminSite:

    def __init__(self, page):
        self.auth = ShoppingAdminAuth(page)
        self.catalog = ShoppingAdminCatalog(page)
        self.customers = ShoppingAdminCustomers(page)
        self.dashboard = ShoppingAdminDashboard(page)
        self.orders = ShoppingAdminOrders(page)
        self.reviews = ShoppingAdminReviews(page)
