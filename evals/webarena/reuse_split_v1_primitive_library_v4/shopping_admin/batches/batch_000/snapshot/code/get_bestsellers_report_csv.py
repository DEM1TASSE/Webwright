async def get_bestsellers_report_csv(self, period_type: str, from_date: str, to_date: str, show_empty_rows: int = 0) -> dict:
    import base64
    import csv
    import io
    import re
    from html import unescape
    from urllib.parse import urlencode, urljoin

    if show_empty_rows not in (0, 1):
        raise ValueError('show_empty_rows must be 0 or 1')

    params = urlencode({
        'period_type': period_type,
        'from': from_date,
        'to': to_date,
        'show_empty_rows': show_empty_rows,
    })
    encoded = base64.b64encode(params.encode()).decode().replace('+', '-').replace('/', '_')
    report_url = f'/admin/reports/report_sales/bestsellers/filter/{encoded}/'

    await self.page.goto(report_url, wait_until='domcontentloaded')
    await self.page.wait_for_load_state('networkidle')

    html = await self.page.content()
    match = re.search(r'<option value="([^"]*exportBestsellersCsv[^"]*)"', html)
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
        rows.append({
            'interval': row[0].strip(),
            'product_name': row[1].strip(),
            'price': row[2].strip(),
            'order_quantity': order_quantity,
        })

    return {
        'report_url': self.page.url,
        'export_csv_url': export_csv_url,
        'column_headers': column_headers,
        'rows': rows,
        'completeness': {
            'source': 'bestsellers_csv_export',
            'filtered_report': True,
            'export_based': True,
        },
    }
