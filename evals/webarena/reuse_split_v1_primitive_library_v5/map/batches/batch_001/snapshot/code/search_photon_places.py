def search_photon_places(self, query: str, result_limit: int = 5) -> dict:
    import urllib.parse
    import urllib.request
    import json

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if not isinstance(result_limit, int) or result_limit <= 0:
        raise ValueError("result_limit must be a positive integer")

    url = "https://photon.komoot.io/api/?" + urllib.parse.urlencode({
        "q": query,
        "limit": result_limit,
    })
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    results = []
    for feature in payload.get("features", []):
        geometry = feature.get("geometry") or {}
        coordinates = geometry.get("coordinates") or []
        properties = feature.get("properties") or {}
        results.append({
            "longitude": float(coordinates[0]) if len(coordinates) > 0 and coordinates[0] is not None else None,
            "latitude": float(coordinates[1]) if len(coordinates) > 1 and coordinates[1] is not None else None,
            "name": properties.get("name"),
            "osm_key": properties.get("osm_key"),
            "osm_value": properties.get("osm_value"),
            "country": properties.get("country"),
            "state": properties.get("state"),
            "city": properties.get("city"),
            "postcode": properties.get("postcode"),
            "street": properties.get("street"),
            "house_number": properties.get("house_number"),
        })

    return {
        "query": query,
        "result_limit": result_limit,
        "results": results,
        "result_count": len(results),
    }
