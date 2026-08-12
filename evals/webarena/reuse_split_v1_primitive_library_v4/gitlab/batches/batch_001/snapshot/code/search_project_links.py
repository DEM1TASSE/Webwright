def search_project_links(self, query: str, page_number: int = 1) -> dict:
    import re
    from urllib.parse import urlencode

    params = {
        "scope": "projects",
        "search": query,
        "page": page_number,
    }
    url = f"{self.base_url}/search?{urlencode(params)}"
    self.page.goto(url, wait_until="domcontentloaded")

    anchors = self.page.locator('a[href]')
    count = anchors.count()
    results = []
    seen = set()

    for i in range(count):
        anchor = anchors.nth(i)
        href = anchor.get_attribute("href")
        text = (anchor.inner_text() or "").strip()
        if not href:
            continue
        if "/-/" in href or href.startswith("#"):
            continue

        normalized_href = href if href.startswith("http://") or href.startswith("https://") else f"{self.base_url}{href if href.startswith('/') else '/' + href}"
        path = href
        if href.startswith("http://") or href.startswith("https://"):
            path_match = re.match(r'^https?://[^/]+(/[^?#]*)', href)
            path = path_match.group(1) if path_match else href
        path = path.split("?")[0].split("#")[0]

        if not re.match(r'^/[^/]+/[^/]+/?$', path):
            continue
        if normalized_href in seen:
            continue
        seen.add(normalized_href)

        results.append({
            "project_path": path.rstrip("/"),
            "project_url": normalized_href,
            "display_text": text,
            "order_index": len(results),
        })

    return {
        "query": query,
        "page_number": page_number,
        "results": results,
        "is_complete_page": False,
    }
