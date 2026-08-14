def search_places(self, query: str, result_limit: int = 5) -> dict:
    import json
    import urllib.parse
    import urllib.request

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if not isinstance(result_limit, int) or result_limit <= 0:
        raise ValueError("result_limit must be a positive integer")

    base_url = "http://18.208.187.221:8085/search"
    params = {
        "q": query,
        "format": "jsonv2",
        "limit": str(result_limit),
    }
    url = base_url + "?" + urllib.parse.urlencode(params)

    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    results = []
    for item in payload:
        lat_raw = item.get("lat")
        lon_raw = item.get("lon")
        results.append({
            "place_id": item.get("place_id"),
            "osm_type": item.get("osm_type"),
            "osm_id": item.get("osm_id"),
            "display_name": item.get("display_name"),
            "latitude": float(lat_raw) if lat_raw is not None else None,
            "longitude": float(lon_raw) if lon_raw is not None else None,
            "category": item.get("category"),
            "place_type": item.get("type"),
            "importance": item.get("importance"),
        })

    return {
        "query": query,
        "result_limit": result_limit,
        "results": results,
        "result_count": len(results),
    }
