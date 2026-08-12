async def get_sales_orders_report_rows(self, period_type: str, from_date: str, to_date: str, status_filter_mode: str = 'all', order_status: str | None = None, include_empty_rows: bool = False) -> dict:
    if status_filter_mode not in ('all', 'specified'):
        raise ValueError("status_filter_mode must be 'all' or 'specified'")
    if status_filter_mode == 'specified' and not order_status:
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
        rows.append({
            'period_label': parts[0],
            'orders_count': orders_count,
        })

    return {
        'report_url': self.page.url,
        'period_type': period_type,
        'from_date': from_date,
        'to_date': to_date,
        'status_filter_mode': status_filter_mode,
        'order_status': order_status,
        'include_empty_rows': include_empty_rows,
        'rows': rows,
        'completeness': 'report_rows_visible_on_page',
    }
