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
        parsed_row = {
            'reviews': int(row['Reviews']),
        }
        if 'Product' in row:
            parsed_row['product'] = row.get('Product', '')
        if 'Last Review' in row:
            parsed_row['last_review'] = row.get('Last Review', '')
        report_rows.append(parsed_row)

    return {
        'report_rows': report_rows,
        'filtered_report_url': self.page.url,
        'export_url': export_url,
    }
