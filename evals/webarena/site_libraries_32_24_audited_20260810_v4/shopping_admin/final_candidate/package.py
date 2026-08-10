"""Generated candidate package; not promoted."""

class ShoppingAdminOrders:

    def __init__(self, page):
        self.page = page

    async def get_sales_orders_report_rows(self, period_type: str, from_date: str, to_date: str, show_order_statuses: str, order_status: str | None=None) -> dict:
        import re
        await self.page.goto('/admin/reports/report_sales/sales/', wait_until='domcontentloaded')
        await self.page.select_option('#sales_report_period_type', period_type)
        await self.page.select_option('#sales_report_show_order_statuses', show_order_statuses)
        if order_status is not None:
            await self.page.select_option('#sales_report_order_statuses', order_status)
        await self.page.fill('#sales_report_from', from_date)
        await self.page.fill('#sales_report_to', to_date)
        await self.page.click('#filter_form_submit')
        await self.page.wait_for_load_state('networkidle')
        rows = await self.page.locator('table.data-grid tbody tr').evaluate_all("trs => trs.map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()))")
        records = []
        for row in rows:
            if len(row) < 2:
                continue
            period_label = row[0]
            orders_count = int(row[1])
            period_month = None
            period_year = None
            match = re.match('^(\\d+)/(\\d{4})$', period_label)
            if match:
                period_month = int(match.group(1))
                period_year = int(match.group(2))
            records.append({'period_label': period_label, 'period_month': period_month, 'period_year': period_year, 'orders_count': orders_count})
        return {'records': records, 'row_count': len(records)}

class ShoppingAdminReviews:

    def __init__(self, page):
        self.page = page

    async def get_product_review_detail_from_admin(self, review_id: str) -> dict:
        detail_url = f'/admin/review/product/edit/id/{review_id}/'
        await self.page.goto(detail_url, wait_until='networkidle')
        product_name = (await self.page.locator('a[href*="catalog/product/edit"], .admin__field:has-text("Product") .admin__field-value').first.inner_text()).strip()
        checked_id = await self.page.locator('input[type="radio"]:checked').first.get_attribute('id')
        rating = int(checked_id.split('_')[-1]) if checked_id else None
        return {'review': {'review_id': review_id, 'product_name': product_name, 'rating': rating}}

    async def list_product_review_records(self, scope: str, page_number: int | None=None) -> dict:
        import re
        scope_to_path = {'all': '/admin/review/product/index/', 'pending': '/admin/review/product/pending/'}
        if scope not in scope_to_path:
            raise ValueError('scope must be one of: all, pending')
        if page_number is not None:
            raise ValueError('page_number is not supported by current evidence for this primitive')
        await self.page.goto(scope_to_path[scope], wait_until='networkidle')
        html = await self.page.content()
        review_ids = sorted(set(re.findall('/admin/review/product/edit/id/(\\d+)/', html)))
        text = re.sub('<[^>]+>', ' ', html)
        pager_match = re.search('of\\s+(\\d+)\\s+Next page', text, re.I)
        total_pages = int(pager_match.group(1)) if pager_match else None
        return {'scope': scope, 'page_number': page_number, 'records': [{'review_id': review_id} for review_id in review_ids], 'pagination': {'total_pages': total_pages, 'is_paginated': total_pages is not None}, 'completeness': {'page_scope': 'current_listing_page', 'is_complete_result_set': False}}

    async def list_product_reviews_from_admin_grid_page(self, product_name: str | None=None) -> dict:
        import re
        await self.page.goto('/admin/review/product/', wait_until='networkidle')
        if product_name is not None:
            name_filter = self.page.locator('#reviewGrid_filter_name')
            await name_filter.fill(product_name)
            await name_filter.press('Enter')
            await self.page.wait_for_load_state('networkidle')
        rows = self.page.locator('tbody tr')
        row_count = await rows.count()
        records = []
        for i in range(row_count):
            row = rows.nth(i)
            cells = row.locator('td')
            cell_count = await cells.count()
            if cell_count < 5:
                continue
            review_id = (await cells.nth(1).inner_text()).strip()
            title = (await cells.nth(4).inner_text()).strip()
            if review_id:
                records.append({'review_id': review_id, 'title': title})
        html = await self.page.content()
        text = re.sub('<[^>]+>', ' ', html)
        pager_match = re.search('of\\s+(\\d+)\\s+Next page', text, re.I)
        total_pages = int(pager_match.group(1)) if pager_match else None
        return {'applied_product_name_filter': product_name, 'records': records, 'pagination': {'total_pages': total_pages, 'is_paginated': total_pages is not None}, 'completeness': {'page_scope': 'current_grid_page', 'is_complete_result_set': False}}

class ShoppingAdminSite:

    def __init__(self, page):
        self.orders = ShoppingAdminOrders(page)
        self.reviews = ShoppingAdminReviews(page)
