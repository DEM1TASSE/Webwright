async def get_sales_orders_report_rows(self, period_type: str, from_date: str, to_date: str, show_order_statuses: str, order_status: str | None = None) -> dict:
    import re

    await self.page.goto("/admin/reports/report_sales/sales/", wait_until="domcontentloaded")
    await self.page.select_option("#sales_report_period_type", period_type)
    await self.page.select_option("#sales_report_show_order_statuses", show_order_statuses)
    if order_status is not None:
        await self.page.select_option("#sales_report_order_statuses", order_status)
    await self.page.fill("#sales_report_from", from_date)
    await self.page.fill("#sales_report_to", to_date)
    await self.page.click("#filter_form_submit")
    await self.page.wait_for_load_state("networkidle")

    rows = await self.page.locator("table.data-grid tbody tr").evaluate_all(
        "trs => trs.map(tr => Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()))"
    )

    records = []
    for row in rows:
        if len(row) < 2:
            continue
        period_label = row[0]
        orders_count = int(row[1])
        period_month = None
        period_year = None
        match = re.match(r"^(\d+)/(\d{4})$", period_label)
        if match:
            period_month = int(match.group(1))
            period_year = int(match.group(2))
        records.append({
            "period_label": period_label,
            "period_month": period_month,
            "period_year": period_year,
            "orders_count": orders_count,
        })

    return {
        "records": records,
        "row_count": len(records),
    }
