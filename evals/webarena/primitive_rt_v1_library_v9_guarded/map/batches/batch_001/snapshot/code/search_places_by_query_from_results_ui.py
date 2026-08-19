def search_places_by_query_from_results_ui(self, query):
    import re
    from urllib.parse import quote

    if not query or not str(query).strip():
        raise ValueError("query must be a non-empty string")

    base = self.page.url.split("/search")[0].split("/directions")[0].rstrip("/")
    search_url = f"{base}/search?query={quote(str(query).strip())}"
    self.page.goto(search_url, wait_until="domcontentloaded")
    self.page.wait_for_timeout(1500)

    link_locator = self.page.get_by_role("link")
    count = link_locator.count()
    results = []
    seen = set()
    for i in range(count):
        link = link_locator.nth(i)
        label = link.inner_text().strip()
        href = link.get_attribute("href")
        if not label:
            continue
        key = (label, href)
        if key in seen:
            continue
        seen.add(key)

        parts = [p.strip() for p in label.split(",")]
        result_name = parts[0] if parts else label
        address_components = [p for p in parts[1:] if p]
        results.append({
            "result_name": result_name,
            "result_label": label,
            "address_components": address_components,
            "detail_href": href,
        })

    return {"results": results}
