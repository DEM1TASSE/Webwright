def search_local_geocoder_results(self, query: str, minlon: float, minlat: float, maxlon: float, maxlat: float, zoom: int):
    import html
    import re
    from urllib.parse import urlsplit

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required")

    current_url = self.page.url or ""
    if current_url:
        parts = urlsplit(current_url)
        base_url = f"{parts.scheme}://{parts.netloc}"
    else:
        base_url = "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:3000"

    self.page.goto(base_url + "/search")
    search_html = self.page.content()

    csrf_param_match = re.search(r'<meta name="csrf-param" content="([^"]+)"', search_html)
    csrf_token_match = re.search(r'<meta name="csrf-token" content="([^"]+)"', search_html)
    if not csrf_param_match or not csrf_token_match:
        raise RuntimeError("CSRF metadata not found on search page")

    csrf_param = csrf_param_match.group(1)
    csrf_token = csrf_token_match.group(1)

    response = self.page.request.post(
        base_url + "/geocoder/search_osm_nominatim",
        form={
            "query": query,
            "zoom": str(zoom),
            "minlon": str(minlon),
            "minlat": str(minlat),
            "maxlon": str(maxlon),
            "maxlat": str(maxlat),
            csrf_param: csrf_token,
        },
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.page.url,
        },
    )
    snippet = response.text()

    records = []
    pattern = re.compile(r'<a class="set_position"[^>]*data-lat="([^"]+)"[^>]*data-lon="([^"]+)"[^>]*data-prefix="([^"]*)"[^>]*data-name="([^"]+)"')
    for match in pattern.finditer(snippet):
        records.append({
            "name": html.unescape(match.group(4)),
            "category": html.unescape(match.group(3)) or None,
            "latitude": float(match.group(1)),
            "longitude": float(match.group(2)),
        })

    return {
        "query": query,
        "viewport": {
            "minlon": minlon,
            "minlat": minlat,
            "maxlon": maxlon,
            "maxlat": maxlat,
            "zoom": zoom,
        },
        "records": records,
        "result_count": len(records),
        "is_complete": False,
    }
