def find_customers_by_phone_from_customer_grid(self, phone_number: str) -> dict:
    import re
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    def _wait_settled(timeout_ms: int = 10000) -> None:
        try:
            self.page.wait_for_load_state('networkidle', timeout=timeout_ms)
        except PlaywrightTimeoutError:
            self.page.wait_for_timeout(1500)

    def _is_login_page() -> bool:
        try:
            body_text = self.page.locator('body').inner_text(timeout=5000)
        except Exception:
            body_text = ''
        if re.search(r'Username|Sign in|Login|password', body_text, re.I):
            return True
        for sel in [
            'input[name="login[username]"]',
            'input[name="username"]',
            '#username',
            'input[type="password"]',
        ]:
            try:
                if self.page.locator(sel).count() > 0:
                    return True
            except Exception:
                pass
        return False

    def _login_if_needed() -> None:
        self.page.goto('http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin', wait_until='domcontentloaded')
        self.page.wait_for_timeout(1500)
        if not _is_login_page():
            return

        for sel in [
            'input[name="login[username]"]',
            'input[name="username"]',
            '#username',
            'input[type="email"]',
            'input[type="text"]',
        ]:
            try:
                loc = self.page.locator(sel).first
                if loc.count() > 0:
                    loc.fill('admin')
                    break
            except Exception:
                continue

        for sel in [
            'input[name="login[password]"]',
            'input[name="password"]',
            'input[type="password"]',
        ]:
            try:
                loc = self.page.locator(sel).first
                if loc.count() > 0:
                    loc.fill('admin1234')
                    break
            except Exception:
                continue

        for sel in [
            'button[type="submit"]',
            '.action-login',
            'button:has-text("Sign in")',
            'button:has-text("Login")',
        ]:
            try:
                loc = self.page.locator(sel).first
                if loc.count() > 0:
                    loc.click()
                    break
            except Exception:
                continue

        _wait_settled()

    def _parse_filtered_rows() -> list:
        row_texts = self.page.locator('tbody tr').evaluate_all(
            "rows => rows.map(r => (r.innerText || '').trim()).filter(t => t)"
        )
        customers = []
        for row_text in row_texts:
            if phone_number not in row_text:
                continue
            parts = [p.strip() for p in row_text.split('\t') if p.strip()]
            name = parts[0] if len(parts) > 0 else None
            email = parts[1] if len(parts) > 1 else None
            customers.append({
                'name': name,
                'email': email,
                'phone_number': phone_number,
            })
        return customers

    _login_if_needed()
    self.page.goto('http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin/customer/index/', wait_until='domcontentloaded')
    _wait_settled()

    try:
        clear_all = self.page.get_by_role('button', name='Clear all')
        if clear_all.count() > 0:
            clear_all.click()
            _wait_settled()
    except Exception:
        pass

    try:
        filters_btn = self.page.get_by_role('button', name='Filters')
        if filters_btn.count() > 0:
            filters_btn.click()
            self.page.wait_for_timeout(800)
    except Exception:
        pass

    phone_input = self.page.locator('input[name="billing_telephone"]:visible').first
    phone_input.fill(phone_number)
    self.page.get_by_role('button', name='Apply Filters').click()
    _wait_settled()
    self.page.wait_for_timeout(1000)

    return {'customers': _parse_filtered_rows()}