import json
import urllib.request


def _fetch_json(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


def _coord_string(coordinates):
    parts = []
    for lon, lat in coordinates:
        parts.append(f"{float(lon)},{float(lat)}")
    return ";".join(parts)


def _normalize_route(route):
    return {
        "duration": route.get("duration"),
        "distance": route.get("distance"),
        "legs": [
            {
                "duration": leg.get("duration"),
                "distance": leg.get("distance"),
                "summary": leg.get("summary"),
            }
            for leg in route.get("legs", [])
        ],
        "raw": route,
    }


def query_osrm_route(coordinates, base_url="http://18.208.187.221:5000/route/v1/driving/", overview=False, steps=True, timeout=60):
    if len(coordinates) < 2:
        raise ValueError("At least two coordinates are required")
    coord_str = _coord_string(coordinates)
    query = f"overview={'true' if overview else 'false'}&steps={'true' if steps else 'false'}"
    url = base_url.rstrip("/") + "/" + coord_str + "?" + query
    data = _fetch_json(url, timeout=timeout)
    if data.get("code") not in (None, "Ok"):
        raise ValueError(f"OSRM route request failed: {data}")
    routes = data.get("routes") or []
    if not routes:
        raise ValueError("OSRM returned no routes")
    return _normalize_route(routes[0])
