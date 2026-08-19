def list_catalog_products_by_quantity_range_from_admin_grid(self, quantity_from: float, quantity_to: float) -> dict:
    import re

    def _goto(url: str):
        response = self.page.goto(url, wait_until="domcontentloaded")
        try:
            self.page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            self.page.wait_for_timeout(1500)
        return response

    def _login_if_needed() -> None:
        body_text = self.page.locator("body").inner_text()
        if re.search(r"Username|Sign in|Login|password", body_text, re.I):
            if self.page.locator('input[name="login[username]"]').count() > 0:
                self.page.locator('input[name="login[username]"]').first.fill("admin")
            if self.page.locator('input[name="login[password]"]').count() > 0:
                self.page.locator('input[name="login[password]"]').first.fill("admin1234")
            login_button = self.page.locator('button.action-login')
            if login_button.count() > 0:
                login_button.first.click()
            else:
                sign_in = self.page.get_by_role("button", name=re.compile(r"sign in|login", re.I))
                if sign_in.count() > 0:
                    sign_in.first.click()
            try:
                self.page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                self.page.wait_for_timeout(3000)

    def _parse_rows() -> list:
        js = '''() => {
            const rows = [];
            const grid = document.querySelector('table[data-role="grid"] tbody') || document.querySelector('table tbody');
            if (!grid) return rows;
            for (const tr of Array.from(grid.querySelectorAll('tr'))) {
                const tds = Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || td.textContent || '').trim());
                if (tds.length >= 10 && tds[6] && tds[8]) {
                    rows.push({
                        name: tds[3] || '',
                        sku: tds[6],
                        quantity: tds[8],
                        salable: tds[9] || ''
                    });
                }
            }
            return rows;
        }'''
        return self.page.evaluate(js)

    if quantity_from > quantity_to:
        raise ValueError("quantity_from must be less than or equal to quantity_to")

    _goto("http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin")
    _login_if_needed()
    _goto("http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin/catalog/product/")

    filters_btn = self.page.get_by_role("button", name="Filters")
    if filters_btn.count() > 0:
        filters_btn.first.click()
        self.page.wait_for_timeout(800)

    qty_from_input = self.page.locator('input[name="qty[from]"]').first
    qty_to_input = self.page.locator('input[name="qty[to]"]').first
    qty_from_input.fill(str(quantity_from))
    qty_to_input.fill(str(quantity_to))

    apply_filters = self.page.get_by_role("button", name="Apply Filters")
    if apply_filters.count() == 0:
        raise RuntimeError("Apply Filters button not found on products grid")
    apply_filters.first.click()
    try:
        self.page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        self.page.wait_for_timeout(6000)

    return {"records": _parse_rows()}