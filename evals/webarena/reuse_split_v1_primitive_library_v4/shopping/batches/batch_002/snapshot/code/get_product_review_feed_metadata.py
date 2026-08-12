def get_product_review_feed_metadata(self, product_url: str) -> dict:
    import re
    import html as html_lib
    from urllib.parse import urljoin

    self.page.goto(product_url, wait_until="domcontentloaded")
    html = self.page.content()

    title_match = re.search(r'<title>(.*?)</title>', html, re.I | re.S)
    review_url_match = re.search(r'"productReviewUrl"\s*:\s*"(.*?)"', html)
    review_count_match = re.search(r'<span[^>]*itemprop=["\']reviewCount["\'][^>]*>(\d+)</span>', html, re.I)

    review_feed_url = None
    if review_url_match:
        review_feed_url = review_url_match.group(1).encode('utf-8').decode('unicode_escape').replace('\\/', '/')
        review_feed_url = urljoin(self.page.url, review_feed_url)

    product_title = None
    if title_match:
        product_title = html_lib.unescape(re.sub(r'\s+', ' ', title_match.group(1))).strip()

    review_count = int(review_count_match.group(1)) if review_count_match else None

    return {
        "product_url": self.page.url,
        "product_title": product_title,
        "review_feed_url": review_feed_url,
        "review_count": review_count,
    }
