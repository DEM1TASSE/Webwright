async def get_product_review_detail_from_admin(self, review_id: str) -> dict:
    detail_url = f"/admin/review/product/edit/id/{review_id}/"
    await self.page.goto(detail_url, wait_until="networkidle")

    product_name = (await self.page.locator('a[href*="catalog/product/edit"], .admin__field:has-text("Product") .admin__field-value').first.inner_text()).strip()
    checked_id = await self.page.locator('input[type="radio"]:checked').first.get_attribute('id')
    rating = int(checked_id.split('_')[-1]) if checked_id else None

    return {
        "review": {
            "review_id": review_id,
            "product_name": product_name,
            "rating": rating,
        }
    }
