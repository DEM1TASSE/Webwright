def get_route(self, profile: str, waypoints: list, base_url: str, overview=False, steps: bool = True, annotations: bool = False, geometries: str = "polyline", alternatives: bool = False):
    import json
    import urllib.parse
    import urllib.request

    if not isinstance(profile, str) or not profile.strip():
        raise ValueError("profile is required")
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("base_url is required")
    if not isinstance(waypoints, list) or len(waypoints) < 2:
        raise ValueError("at least two waypoints are required")

    encoded_points = []
    for waypoint in waypoints:
        if "longitude" not in waypoint or "latitude" not in waypoint:
            raise ValueError("each waypoint must include latitude and longitude")
        encoded_points.append(f"{waypoint['longitude']},{waypoint['latitude']}")

    coords = ";".join(encoded_points)
    normalized_base = base_url.rstrip("/")
    request_base = f"{normalized_base}/route/v1/{profile}/{coords}"
    params = {
        "overview": str(overview).lower() if isinstance(overview, bool) else overview,
        "steps": str(steps).lower(),
        "annotations": str(annotations).lower(),
        "geometries": geometries,
        "alternatives": str(alternatives).lower(),
    }
    request_url = request_base + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(request_url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    routes = []
    for route in payload.get("routes", []):
        routes.append({
            "duration_seconds": route.get("duration"),
            "distance_meters": route.get("distance"),
            "weight": route.get("weight"),
            "weight_name": route.get("weight_name"),
            "geometry": route.get("geometry"),
            "legs": route.get("legs"),
        })

    returned_waypoints = []
    for waypoint in payload.get("waypoints", []):
        location = waypoint.get("location") or [None, None]
        returned_waypoints.append({
            "name": waypoint.get("name"),
            "longitude": location[0],
            "latitude": location[1],
            "distance_meters": waypoint.get("distance"),
        })

    return {
        "profile": profile,
        "base_url": normalized_base,
        "code": payload.get("code"),
        "routes": routes,
        "waypoints": returned_waypoints,
        "route_count": len(routes),
        "request_waypoint_count": len(waypoints),
        "request_url": request_url,
    }
