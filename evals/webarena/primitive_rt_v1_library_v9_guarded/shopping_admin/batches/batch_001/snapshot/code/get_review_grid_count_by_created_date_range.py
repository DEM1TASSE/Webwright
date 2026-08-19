def get_review_grid_count_by_created_date_range(self, start_date: str, end_date: str) -> dict:
    import re
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    def _login_if_needed() -> None:
        self.page.goto('http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin', wait_until='domcontentloaded')
        if self.page.locator('input[name="username"]').count() > 0:
            self.page.fill('input[name="username"]', 'admin')
        if self.page.locator('input[name="password"]').count() > 0:
            self.page.fill('input[name="password"]', 'admin1234')
        if self.page.locator('input[name="login[username]"]').count() > 0:
            self.page.fill('input[name="login[username]"]', 'admin')
        if self.page.locator('input[name="login[password]"]').count() > 0:
            self.page.fill('input[name="login[password]"]', 'admin1234')
        sign_in = self.page.get_by_role('button', name=re.compile(r'sign in|login', re.I))
        if sign_in.count() > 0:
            sign_in.first.click()
        elif self.page.locator('button[type="submit"]').count() > 0:
            self.page.locator('button[type="submit"]').first.click()
        try:
            self.page.wait_for_load_state('domcontentloaded', timeout=10000)
        except PlaywrightTimeoutError:
            pass
        self.page.wait_for_timeout(1500)

    _login_if_needed()
    self.page.goto('http://gcrsandbox410.redmond.corp.microsoft.com:7780/admin/review/product/index/', wait_until='domcontentloaded')
    self.page.wait_for_timeout(1500)
    self.page.fill('input[name="created_at[from]"]', start_date)
    self.page.fill('input[name="created_at[to]"]', end_date)
    self.page.get_by_role('button', name='Search').click()
    try:
        self.page.wait_for_load_state('networkidle', timeout=10000)
    except PlaywrightTimeoutError:
        self.page.wait_for_timeout(1000)
    self.page.wait_for_timeout(1000)
    body_text = self.page.locator('body').inner_text()
    match = re.search(r'(\d+) records found', body_text)
    if match is None:
        raise ValueError('Could not parse review count from reviews grid summary')
    return {
        'record_count': int(match.group(1)),
        'applied_filters': {
            'start_date': start_date,
            'end_date': end_date,
        },
        'source_page': self.page.url,
    }