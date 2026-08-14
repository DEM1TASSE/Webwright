def get_site_configured_route(self, waypoints: list) -> dict:
    import json
    import urllib.parse
    import urllib.request

    if not isinstance(waypoints, list) or len(waypoints) < 2:
        raise ValueError("waypoints must be a list of at least two coordinate objects")

    encoded_points = []
    for waypoint in waypoints:
        if not isinstance(waypoint, dict):
            raise ValueError("each waypoint must be an object with latitude and longitude")
        if "latitude" not in waypoint or "longitude" not in waypoint:
            raise ValueError("each waypoint must include latitude and longitude")
        latitude = float(waypoint["latitude"])
        longitude = float(waypoint["longitude"])
        encoded_points.append(f"{longitude},{latitude}")

    base_url = "http://18.208.187.221:5002/route/v1/driving/"
    query = urllib.parse.urlencode({
        "overview": "false",
        "steps": "true",
        "alternatives": "false",
        "annotations": "false",
    })
    url = base_url + ";".join(encoded_points) + "?" + query

    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    routes = []
    for route in payload.get("routes", []):
        routes.append({
            "duration_seconds": route.get("duration"),
            "distance_meters": route.get("distance"),
        })

    snapped_waypoints = []
    for waypoint in payload.get("waypoints", []):
        location = waypoint.get("location") or []
        snapped_waypoints.append({
            "latitude": float(location[1]) if len(location) > 1 and location[1] is not None else None,
            "longitude": float(location[0]) if len(location) > 0 and location[0] is not None else None,
        })

    return {
        "code": payload.get("code"),
        "waypoints": snapped_waypoints,
        "routes": routes,
        "route_count": len(routes),
    }
