def search_local_geocoder_places(self, query: str, map_bounds: dict, zoom: int) -> dict:
    import html
    import re
    from urllib.parse import urlencode

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if not isinstance(map_bounds, dict):
        raise ValueError("map_bounds must be an object")
    for key in ("minlon", "minlat", "maxlon", "maxlat"):
        if key not in map_bounds:
            raise ValueError(f"map_bounds must include {key}")
    if not isinstance(zoom, int):
        raise ValueError("zoom must be an integer")

    base_url = "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:3000"
    search_url = base_url + "/search?" + urlencode({"query": query})
    search_response = self.page.request.get(search_url, timeout=30000)
    if not search_response.ok:
        raise RuntimeError(f"failed to load search page: {search_response.status}")
    search_html = search_response.text()

    csrf_param_match = re.search(r'<meta name="csrf-param" content="([^"]+)"', search_html)
    csrf_token_match = re.search(r'<meta name="csrf-token" content="([^"]+)"', search_html)
    if not csrf_param_match or not csrf_token_match:
        raise RuntimeError("failed to extract CSRF metadata from search page")

    csrf_param = csrf_param_match.group(1)
    csrf_token = csrf_token_match.group(1)
    form_data = {
        "query": query,
        "zoom": str(zoom),
        "minlon": str(map_bounds["minlon"]),
        "minlat": str(map_bounds["minlat"]),
        "maxlon": str(map_bounds["maxlon"]),
        "maxlat": str(map_bounds["maxlat"]),
        csrf_param: csrf_token,
    }

    response = self.page.request.post(
        base_url + "/geocoder/search_osm_nominatim",
        form=form_data,
        headers={
            "Referer": search_url,
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=30000,
    )
    if not response.ok:
        raise RuntimeError(f"local geocoder request failed: {response.status}")
    response_html = response.text()

    pattern = re.compile(
        r'<a class="set_position"[^>]*data-lat="([^"]+)"[^>]*data-lon="([^"]+)"[^>]*data-prefix="([^"]*)"[^>]*data-name="([^"]+)"'
    )

    results = []
    for match in pattern.finditer(response_html):
        results.append({
            "prefix": html.unescape(match.group(3)),
            "display_name": html.unescape(match.group(4)),
            "latitude": float(match.group(1)),
            "longitude": float(match.group(2)),
        })

    return {
        "query": query,
        "results": results,
        "result_count": len(results),
        "search_scope": {
            "map_bounds": {
                "minlon": float(map_bounds["minlon"]),
                "minlat": float(map_bounds["minlat"]),
                "maxlon": float(map_bounds["maxlon"]),
                "maxlat": float(map_bounds["maxlat"]),
            },
            "zoom": zoom,
        },
    }
