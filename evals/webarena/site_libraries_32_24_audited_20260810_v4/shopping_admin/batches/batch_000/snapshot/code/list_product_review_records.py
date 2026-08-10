async def list_product_review_records(self, scope: str, page_number: int | None = None) -> dict:
    import re

    scope_to_path = {
        "all": "/admin/review/product/index/",
        "pending": "/admin/review/product/pending/",
    }
    if scope not in scope_to_path:
        raise ValueError("scope must be one of: all, pending")
    if page_number is not None:
        raise ValueError("page_number is not supported by current evidence for this primitive")

    await self.page.goto(scope_to_path[scope], wait_until="networkidle")
    html = await self.page.content()
    review_ids = sorted(set(re.findall(r"/admin/review/product/edit/id/(\d+)/", html)))
    text = re.sub(r"<[^>]+>", " ", html)
    pager_match = re.search(r"of\s+(\d+)\s+Next page", text, re.I)
    total_pages = int(pager_match.group(1)) if pager_match else None

    return {
        "scope": scope,
        "page_number": page_number,
        "records": [{"review_id": review_id} for review_id in review_ids],
        "pagination": {
            "total_pages": total_pages,
            "is_paginated": total_pages is not None,
        },
        "completeness": {
            "page_scope": "current_listing_page",
            "is_complete_result_set": False,
        },
    }
