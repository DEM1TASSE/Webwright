def search_places(self, query: str, limit: int = 10, response_format: str = "jsonv2"):
    import json
    import urllib.parse
    import urllib.request

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required")
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")
    if not isinstance(response_format, str) or not response_format.strip():
        raise ValueError("response_format is required")

    base_url = "http://18.208.187.221:8085/search"
    params = {
        "q": query,
        "format": response_format,
        "limit": limit,
    }
    url = base_url + "?" + urllib.parse.urlencode(params)

    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    candidates = []
    for item in payload:
        lat_value = item.get("lat")
        lon_value = item.get("lon")
        candidates.append({
            "place_id": item.get("place_id"),
            "osm_type": item.get("osm_type"),
            "osm_id": item.get("osm_id"),
            "display_name": item.get("display_name"),
            "latitude": float(lat_value) if lat_value is not None else None,
            "longitude": float(lon_value) if lon_value is not None else None,
            "category": item.get("category") or item.get("class"),
            "type": item.get("type"),
            "importance": item.get("importance"),
            "boundingbox": item.get("boundingbox"),
        })

    return {
        "query": query,
        "limit_requested": limit,
        "response_format": response_format,
        "candidates": candidates,
        "result_count": len(candidates),
        "is_complete": False,
    }
