def search_places_with_address_details(self, query):
    from urllib.parse import quote

    if not query or not str(query).strip():
        raise ValueError("query must be a non-empty string")

    encoded_query = quote(str(query).strip())
    api_url = (
        "https://nominatim.openstreetmap.org/search"
        f"?q={encoded_query}&format=jsonv2&addressdetails=1"
    )
    response = self.page.request.get(
        api_url,
        headers={"User-Agent": "Mozilla/5.0 WebArena Agent"},
    )
    if not response.ok:
        raise RuntimeError(f"Nominatim search failed with status {response.status}")

    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Expected list payload from Nominatim search")

    results = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        results.append({
            "place_id": item.get("place_id"),
            "osm_type": item.get("osm_type"),
            "osm_id": item.get("osm_id"),
            "name": item.get("name"),
            "display_name": item.get("display_name"),
            "lat": item.get("lat"),
            "lon": item.get("lon"),
            "category": item.get("category"),
            "type": item.get("type"),
            "address": item.get("address") if isinstance(item.get("address"), dict) else None,
            "boundingbox": item.get("boundingbox") if isinstance(item.get("boundingbox"), list) else None,
        })

    return {"results": results}
