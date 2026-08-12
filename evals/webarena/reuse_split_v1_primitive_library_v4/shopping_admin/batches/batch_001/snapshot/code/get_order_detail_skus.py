async def get_order_detail_skus(self, order_id: str) -> dict:
    import re

    if not order_id:
        raise ValueError('order_id is required')

    await self.page.goto(f'/admin/sales/order/view/order_id/{order_id}/', wait_until='domcontentloaded')
    await self.page.wait_for_load_state('networkidle')

    body_text = await self.page.locator('body').inner_text()
    sku_matches = re.findall(r'SKU:\s*([^\n\r]+)', body_text)
    skus = [{'sku': sku.strip()} for sku in sku_matches if sku.strip()]

    return {
        'order_id': str(order_id),
        'order_url': self.page.url,
        'skus': skus,
        'is_complete': True,
    }
