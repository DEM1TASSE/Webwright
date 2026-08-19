async def get_product_review_detail_by_url(self, review_url: str) -> dict:
    base = "http://gcrsandbox410.redmond.corp.microsoft.com:7780"
    page = self.page

    async def _ensure_logged_in() -> None:
        await page.goto(f"{base}/admin", wait_until="domcontentloaded")
        body = (await page.locator("body").inner_text()).lower()
        if "sign in" in body or "welcome, please sign in" in body or "username" in body:
            await page.locator('input[name="login[username]"], input[type="text"]').first.fill("admin")
            await page.locator('input[name="login[password]"], input[type="password"]').first.fill("admin1234")
            await page.locator('button.action-login, button[type="submit"]').first.click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2000)

    async def _read_optional_value(selector: str):
        locator = page.locator(selector).first
        if await locator.count() == 0:
            return None
        return await locator.input_value()

    await _ensure_logged_in()
    target = review_url if review_url.startswith("http") else base + review_url
    await page.goto(target, wait_until="domcontentloaded")
    await page.wait_for_timeout(1200)

    nickname = await _read_optional_value('input[name="nickname"], #nickname')
    title = await _read_optional_value('input[name="title"], #title')
    review_text = await _read_optional_value('textarea[name="detail"], #detail')
    status_value = await _read_optional_value('#status_id')

    if nickname is None or title is None or review_text is None:
        raise RuntimeError("Review detail form fields not available on loaded page")

    return {
        "nickname": nickname,
        "title": title,
        "review_text": review_text,
        "status_value": status_value,
        "review_url": page.url,
    }
