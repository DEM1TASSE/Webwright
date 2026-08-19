def filter_customers_by_billing_phone_in_admin_grid(self, billing_phone: str) -> dict:
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
            username_candidates = [
                self.page.get_by_label("Username"),
                self.page.locator('input[name="login[username]"]'),
                self.page.locator('input[name="username"]'),
                self.page.locator('#username'),
                self.page.locator('input[type="email"]'),
                self.page.locator('input[type="text"]'),
            ]
            password_candidates = [
                self.page.get_by_label("Password"),
                self.page.locator('input[name="login[password]"]'),
                self.page.locator('input[name="password"]'),
                self.page.locator('input[type="password"]'),
            ]
            for loc in username_candidates:
                try:
                    if loc.count() > 0:
                        loc.first.fill("admin")
                        break
                except Exception:
                    pass
            for loc in password_candidates:
                try:
                    if loc.count() > 0:
                        loc.first.fill("admin1234")
                        break
                except Exception:
                    pass
            login_buttons = [
                self.page.get_by_role("button", name=re.compile(r"sign in|login", re.I)),
                self.page.locator('button[type="submit"]'),
                self.page.locator('.action-login'),
            ]
            for loc in login_buttons:
                try:
                    if loc.count() > 0:
                        loc.first.click()
                        break
                except Exception:
                    pass
            try:
                self.page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                self.page.wait_for_timeout(3000)

    def _open_filters_if_needed() -> None:
        filters_btn = self.page.get_by_role("button", name="Filters")
        try:
            if filters_btn.count() > 0:
                filters_btn.first.click()
                self.page.wait_for_timeout(800)
        except Exception:
            pass

    def _parse_rows(phone_value: str) -> list:
        row_texts = self.page.locator("tbody tr").evaluate_all(
            "rows => rows.map(r => (r.innerText || '').trim()).filter(Boolean)"
        )
        customers = []
        for row_text in row_texts:
            if phone_value not in row_text:
                continue
            parts = [part.strip() for part in row_text.split("\t") if part.strip()]
            name = parts[0] if len(parts) > 0 else None
            email = parts[1] if len(parts) > 1 else None
            customers.append({
                "name": name,
                "email": email,
                "billing_phone": phone_value,
            })
        return customers

    _goto("http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin")
    _login_if_needed()
    _goto("http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin/customer/index/")

    clear_all = self.page.get_by_role("button", name="Clear all")
    try:
        if clear_all.count() > 0:
            clear_all.first.click()
            try:
                self.page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                self.page.wait_for_timeout(1000)
    except Exception:
        pass

    _open_filters_if_needed()
    phone_input = self.page.locator('input[name="billing_telephone"]:visible').first
    phone_input.fill(billing_phone)

    apply_filters = self.page.get_by_role("button", name="Apply Filters")
    if apply_filters.count() == 0:
        raise RuntimeError("Apply Filters button not found on customer grid")
    apply_filters.first.click()
    try:
        self.page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        self.page.wait_for_timeout(1500)

    return {"customers": _parse_rows(billing_phone)}