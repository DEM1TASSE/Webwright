def list_reviews_by_created_date_range_from_reviews_grid(self, start_date: str, end_date: str) -> dict:
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
            field_values = [
                ('input[name="username"]', 'admin'),
                ('input[name="password"]', 'admin1234'),
                ('input[name="login[username]"]', 'admin'),
                ('input[name="login[password]"]', 'admin1234'),
            ]
            for selector, value in field_values:
                loc = self.page.locator(selector)
                try:
                    if loc.count() > 0:
                        loc.first.fill(value)
                except Exception:
                    pass
            sign_in = self.page.get_by_role("button", name=re.compile(r"sign in|login", re.I))
            if sign_in.count() > 0:
                sign_in.first.click()
            else:
                submit = self.page.locator('button[type="submit"]')
                if submit.count() > 0:
                    submit.first.click()
            try:
                self.page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                self.page.wait_for_timeout(1500)

    def _parse_records() -> list:
        js = '''() => {
            const records = [];
            const tbody = document.querySelector('table[data-role="grid"] tbody') || document.querySelector('table tbody');
            if (!tbody) return records;
            const headers = Array.from(document.querySelectorAll('table thead th')).map(th => (th.innerText || th.textContent || '').trim().toLowerCase());
            for (const tr of Array.from(tbody.querySelectorAll('tr'))) {
                const cells = Array.from(tr.querySelectorAll('td')).map(td => (td.innerText || td.textContent || '').trim());
                if (!cells.length) continue;
                const record = { row_text: cells.join(' | ') };
                for (let i = 0; i < Math.min(headers.length, cells.length); i++) {
                    const h = headers[i];
                    const v = cells[i];
                    if (!h) continue;
                    if (h.includes('created')) record.created_at = v;
                    else if (h === 'id' || h.endsWith(' id')) record.review_id = v;
                    else if (h.includes('title')) record.title = v;
                    else if (h.includes('nickname')) record.nickname = v;
                    else if (h.includes('review')) record.review_text = v;
                    else if (h.includes('status')) record.status = v;
                    else if (h.includes('sku')) record.sku = v;
                    else if (h.includes('product')) record.product = v;
                    else if (h.includes('visibility')) record.visibility = v;
                    else if (h.includes('type')) record.review_type = v;
                }
                records.push(record);
            }
            return records;
        }'''
        return self.page.evaluate(js)

    _goto("http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin")
    _login_if_needed()
    _goto("http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin/review/product/index/")

    from_input = self.page.locator('input[name="created_at[from]"]').first
    to_input = self.page.locator('input[name="created_at[to]"]').first
    from_input.fill(start_date)
    to_input.fill(end_date)

    search_button = self.page.get_by_role("button", name="Search")
    if search_button.count() == 0:
        raise RuntimeError("Search button not found on reviews grid")
    search_button.first.click()
    try:
        self.page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        self.page.wait_for_timeout(1000)

    body_text = self.page.locator("body").inner_text()
    count_match = re.search(r"(\d+) records found", body_text)
    summary_count = int(count_match.group(1)) if count_match else None

    return {
        "records": _parse_records(),
        "applied_filters": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "summary_count": summary_count,
        "source_page": self.page.url,
    }