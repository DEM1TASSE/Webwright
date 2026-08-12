def search_products(self, query: str, page_number: int = 1, fetch_all_pages: bool = False) -> dict:
    import re
    import html as html_lib
    from urllib.parse import quote, urljoin

    def _clean(text: str) -> str:
        text = re.sub(r'<[^>]+>', ' ', text)
        return html_lib.unescape(re.sub(r'\s+', ' ', text)).strip()

    def _parse_products(page_html: str, current_url: str) -> list:
        products = []
        for block in re.findall(r'<li[^>]*class=["\'][^"\']*product-item[^"\']*["\'][^>]*>(.*?)</li>', page_html, re.I | re.S):
            name_match = re.search(r'class=["\']product-item-link["\'][^>]*>(.*?)</a>', block, re.I | re.S)
            href_match = re.search(r'class=["\']product-item-link["\'][^>]*href=["\']([^"\']+)["\']', block, re.I | re.S)
            price_matches = re.findall(r'\$\s*([0-9]+(?:\.[0-9]{2})?)', block)
            if not name_match or not price_matches:
                continue
            products.append({
                "name": _clean(name_match.group(1)),
                "product_url": urljoin(current_url, href_match.group(1)) if href_match else None,
                "price": float(price_matches[0]),
            })
        return products

    base_url = "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:7770"
    first_url = f"{base_url}/catalogsearch/result/?q={quote(query)}"
    self.page.goto(first_url, wait_until="domcontentloaded")
    first_html = self.page.content()

    discovered = {1}
    for p in re.findall(r'catalogsearch/result/(?:index/)?\?p=(\d+)&amp;q=', first_html, re.I):
        discovered.add(int(p))

    fetched = sorted(discovered) if fetch_all_pages else [page_number]

    results = []
    seen = set()
    for current_page_number in fetched:
        current_url = first_url if current_page_number == 1 else f"{base_url}/catalogsearch/result/index/?p={current_page_number}&q={quote(query)}"
        if current_page_number != 1:
            self.page.goto(current_url, wait_until="domcontentloaded")
            page_html = self.page.content()
        else:
            page_html = first_html
        for product in _parse_products(page_html, self.page.url):
            key = (product["name"], product["product_url"], product["price"])
            if key in seen:
                continue
            seen.add(key)
            results.append(product)

    return {
        "query": query,
        "results": results,
        "page_numbers_discovered": sorted(discovered),
        "fetched_page_numbers": fetched,
        "is_complete": fetch_all_pages and set(fetched) == set(discovered),
    }
