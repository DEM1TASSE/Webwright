def search_places(self, query: str, limit: int = 5) -> dict:
    """Search the site's Nominatim service for place candidates."""
    import urllib.parse
    import urllib.request
    import json

    if not query:
        raise ValueError("query is required")
    if limit <= 0:
        raise ValueError("limit must be positive")

    base_url = "http://18.208.187.221:8085/search"
    params = {
        "format": "json",
        "q": query,
        "limit": str(limit),
    }
    request_url = base_url + "?" + urllib.parse.urlencode(params)

    with urllib.request.urlopen(request_url, timeout=60) as response:
        data = json.load(response)

    candidates = []
    for item in data:
        candidates.append({
            "place_id": item.get("place_id"),
            "osm_type": item.get("osm_type"),
            "osm_id": item.get("osm_id"),
            "display_name": item.get("display_name"),
            "lat": item.get("lat"),
            "lon": item.get("lon"),
            "class_name": item.get("class"),
            "type": item.get("type"),
            "importance": item.get("importance"),
            "boundingbox": item.get("boundingbox"),
        })

    return {
        "query": query,
        "limit": limit,
        "request_url": request_url,
        "candidates": candidates,
    }
