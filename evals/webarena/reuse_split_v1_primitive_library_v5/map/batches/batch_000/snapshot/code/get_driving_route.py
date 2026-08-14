def get_driving_route(self, waypoints: list) -> dict:
    import json
    import urllib.parse
    import urllib.request

    if not isinstance(waypoints, list) or len(waypoints) < 2:
        raise ValueError("waypoints must be a list of at least two coordinate objects")

    encoded_points = []
    normalized_waypoints = []
    for waypoint in waypoints:
        if not isinstance(waypoint, dict):
            raise ValueError("each waypoint must be an object with latitude and longitude")
        latitude = waypoint.get("latitude")
        longitude = waypoint.get("longitude")
        if latitude is None or longitude is None:
            raise ValueError("each waypoint must include latitude and longitude")
        latitude = float(latitude)
        longitude = float(longitude)
        normalized_waypoints.append({
            "latitude": latitude,
            "longitude": longitude,
        })
        encoded_points.append(f"{longitude},{latitude}")

    base_url = "http://18.208.187.221:5000/route/v1/driving/"
    query = urllib.parse.urlencode({
        "overview": "false",
        "steps": "true",
        "geometries": "polyline",
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

    return {
        "code": payload.get("code"),
        "waypoints": normalized_waypoints,
        "routes": routes,
        "route_count": len(routes),
    }
