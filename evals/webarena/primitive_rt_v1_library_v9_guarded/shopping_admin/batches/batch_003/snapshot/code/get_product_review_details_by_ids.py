async def get_product_review_details_by_ids(self, review_ids: list[int]) -> dict:
    base = "http://gcrsandbox410.redmond.corp.microsoft.com:7780"
    page = self.page

    async def _ensure_logged_in() -> None:
        await page.goto(f"{base}/admin", wait_until="domcontentloaded")
        body_text = (await page.locator("body").inner_text()).lower()
        if "welcome, please sign in" in body_text or "username" in body_text or "sign in" in body_text:
            await page.locator('input[name="login[username]"], input[type="text"]').first.fill("admin")
            await page.locator('input[name="login[password]"], input[type="password"]').first.fill("admin1234")
            await page.locator('button.action-login, button[type="submit"]').first.click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2000)

    async def _read_required_value(selector: str, review_id: int, field_name: str) -> str:
        locator = page.locator(selector).first
        if await locator.count() == 0:
            raise RuntimeError(f"Missing {field_name} field for review id {review_id}")
        return await locator.input_value()

    await _ensure_logged_in()

    records = []
    for review_id in review_ids:
        target = f"{base}/admin/review/product/edit/id/{review_id}/"
        await page.goto(target, wait_until="domcontentloaded")
        await page.wait_for_timeout(1200)

        nickname = await _read_required_value('#nickname, input[name="nickname"]', review_id, 'nickname')
        title = await _read_required_value('#title, input[name="title"]', review_id, 'title')
        detail = await _read_required_value('#detail, textarea[name="detail"]', review_id, 'detail')
        status_value = await _read_required_value('#status_id', review_id, 'status')

        records.append({
            "id": review_id,
            "status_value": status_value,
            "nickname": nickname,
            "title": title,
            "detail": detail,
            "review_url": page.url,
        })

    return {"records": records}
