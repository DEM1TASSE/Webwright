import json
import urllib.parse
import urllib.request


def _fetch_json(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


def _normalize_match(query, item):
    return {
        "query": query,
        "display_name": item.get("display_name"),
        "lat": float(item["lat"]),
        "lon": float(item["lon"]),
        "raw": item,
    }


def geocode_places_with_nominatim(queries, base_url="http://18.208.187.221:8085/", limit=1, timeout=60):
    if isinstance(queries, str):
        queries = [queries]
    results = []
    for query in queries:
        url = (
            base_url.rstrip("/")
            + "/search?format=json&limit="
            + str(limit)
            + "&q="
            + urllib.parse.quote(query)
        )
        data = _fetch_json(url, timeout=timeout)
        if not data:
            raise ValueError(f"No geocoding results for query: {query}")
        results.append(_normalize_match(query, data[0]))
    return results
