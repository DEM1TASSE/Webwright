def search_places_by_text_query(self, query):
    import urllib.parse
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")

    encoded_query = urllib.parse.quote(query.strip())
    url = f"http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:3000/search?query={encoded_query}"
    self.page.goto(url, wait_until="domcontentloaded")
    try:
        self.page.wait_for_load_state("networkidle", timeout=10000)
    except PlaywrightTimeoutError:
        pass

    sidebar_text = ""
    try:
        sidebar_text = (self.page.locator("#sidebar_content").inner_text(timeout=5000) or "").strip()
    except Exception:
        sidebar_text = ""

    visible_result_links = []
    try:
        links = self.page.locator("#sidebar_content a")
        count = links.count()
        for i in range(count):
            link = links.nth(i)
            text = (link.inner_text(timeout=1000) or "").strip()
            if not text:
                continue
            href = link.get_attribute("href")
            visible_result_links.append({
                "display_name": text,
                "href": href,
                "raw_result_text": text,
            })
    except Exception:
        visible_result_links = []

    return {
        "query": query.strip(),
        "search_url": self.page.url,
        "sidebar_text": sidebar_text,
        "visible_result_links": visible_result_links,
    }