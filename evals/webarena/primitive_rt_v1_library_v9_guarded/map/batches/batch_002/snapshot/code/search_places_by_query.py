def search_places_by_query(self, query: str):
    from urllib.parse import quote_plus, urljoin

    base_url = "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:3000"
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    query = query.strip()

    self.page.goto(f"{base_url}/search?query={quote_plus(query)}", wait_until="domcontentloaded")
    self.page.wait_for_timeout(3000)

    records = []
    anchors = self.page.locator("a.set_position")
    count = anchors.count()
    for i in range(count):
        a = anchors.nth(i)
        name = a.get_attribute("data-name")
        href = a.get_attribute("href")
        lat_raw = a.get_attribute("data-lat")
        lon_raw = a.get_attribute("data-lon")
        display_text = (a.inner_text() or "").strip()

        try:
            latitude = float(lat_raw) if lat_raw not in (None, "") else None
        except Exception:
            latitude = None
        try:
            longitude = float(lon_raw) if lon_raw not in (None, "") else None
        except Exception:
            longitude = None

        title = name.strip() if isinstance(name, str) and name.strip() else (display_text or None)
        subtitle = display_text if display_text and title and display_text != title else None

        records.append({
            "title": title,
            "subtitle": subtitle,
            "display_text": display_text,
            "name": title,
            "latitude": latitude,
            "longitude": longitude,
            "href": urljoin(base_url, href) if href else None,
        })

    return {
        "query": query,
        "records": records,
    }
