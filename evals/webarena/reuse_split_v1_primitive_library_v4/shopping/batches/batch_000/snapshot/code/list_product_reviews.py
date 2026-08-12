def list_product_reviews(self, product_id: str, page_number: int = 1, limit: int = 50) -> dict:
    import re
    import html as html_lib
    from urllib.parse import urlencode

    def _clean(text: str) -> str:
        text = re.sub(r'<[^>]+>', ' ', text)
        return html_lib.unescape(re.sub(r'\s+', ' ', text)).strip()

    base_url = "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:7770"
    query = {"limit": str(limit)}
    if page_number != 1:
        query["p"] = str(page_number)
    review_url = f"{base_url}/review/product/listAjax/id/{product_id}/?{urlencode(query)}"

    self.page.goto(review_url, wait_until="domcontentloaded")
    html = self.page.content()

    reviews = []
    blocks = re.findall(r'<li class=["\']item review-item["\'].*?</li>', html, re.I | re.S)
    for block in blocks:
        title_match = re.search(r'<div class=["\']review-title["\'][^>]*>(.*?)</div>', block, re.I | re.S)
        content_match = re.search(r'<div class=["\']review-content["\'][^>]*>(.*?)</div>', block, re.I | re.S)
        author_match = re.search(r'itemprop=["\']author["\']>\s*(.*?)</strong>', block, re.I | re.S)
        rating_match = re.search(r'<div class=["\']rating-result["\'][^>]*title=["\'](\d+)%["\']', block, re.I | re.S)
        rating_percent = int(rating_match.group(1)) if rating_match else None
        reviews.append({
            "author_name": _clean(author_match.group(1)) if author_match else None,
            "review_title": _clean(title_match.group(1)) if title_match else None,
            "review_content": _clean(content_match.group(1)) if content_match else None,
            "rating_percent": rating_percent,
            "stars": int(round(rating_percent / 20.0)) if rating_percent is not None else None,
        })

    return {
        "product_id": product_id,
        "reviews": reviews,
        "page_number": page_number,
        "limit": limit,
        "is_complete_for_page": True,
    }
