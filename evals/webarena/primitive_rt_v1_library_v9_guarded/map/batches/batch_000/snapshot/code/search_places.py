def search_places(self, query: str, limit: int = 10) -> dict:
    import requests

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")

    response = requests.get(
        "http://18.208.187.221:8085/search",
        params={"q": query, "format": "jsonv2", "limit": limit},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("unexpected search response shape")

    results = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        try:
            lat = float(row["lat"])
            lon = float(row["lon"])
        except (KeyError, TypeError, ValueError):
            continue

        display_name = str(row.get("display_name", ""))
        results.append({
            "label": display_name,
            "display_name": display_name,
            "lat": lat,
            "lon": lon,
            "place_id": str(row["place_id"]) if row.get("place_id") is not None else None,
            "osm_type": str(row["osm_type"]) if row.get("osm_type") is not None else None,
            "osm_id": str(row["osm_id"]) if row.get("osm_id") is not None else None,
            "boundingbox": row.get("boundingbox") if isinstance(row.get("boundingbox"), list) else None,
            "class_name": str(row.get("class")) if row.get("class") is not None else None,
            "type_name": str(row.get("type")) if row.get("type") is not None else None,
            "importance": float(row["importance"]) if row.get("importance") is not None else None,
        })

    return {"results": results}
