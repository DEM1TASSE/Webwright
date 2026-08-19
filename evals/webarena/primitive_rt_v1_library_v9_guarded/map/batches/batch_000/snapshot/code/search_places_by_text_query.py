def search_places_by_text_query(self, query: str, limit: int = 10) -> dict:
    import requests

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError("limit must be a positive integer")

    response = requests.get(
        "http://18.208.187.221:8085/search",
        params={"q": query, "format": "json", "limit": limit},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("expected search response to be a list")

    results = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        display_name = row.get("display_name")
        lat = row.get("lat")
        lon = row.get("lon")
        if display_name is None or lat is None or lon is None:
            continue
        try:
            lat_num = float(lat)
            lon_num = float(lon)
        except (TypeError, ValueError):
            continue

        record = {
            "display_name": str(display_name),
            "lat": lat_num,
            "lon": lon_num,
        }
        if row.get("place_id") is not None:
            record["place_id"] = str(row.get("place_id"))
        if row.get("osm_type") is not None:
            record["osm_type"] = str(row.get("osm_type"))
        if row.get("osm_id") is not None:
            record["osm_id"] = str(row.get("osm_id"))
        if row.get("class") is not None:
            record["class_name"] = str(row.get("class"))
        if row.get("type") is not None:
            record["type_name"] = str(row.get("type"))
        if row.get("importance") is not None:
            try:
                record["importance"] = float(row.get("importance"))
            except (TypeError, ValueError):
                pass
        if isinstance(row.get("boundingbox"), list):
            record["boundingbox"] = [str(v) for v in row.get("boundingbox")]
        results.append(record)

    return {"results": results}