def get_route(self, waypoints: list, transportation_method: str) -> dict:
    import json
    import urllib.parse
    import urllib.request

    if not isinstance(waypoints, list) or len(waypoints) < 2:
        raise ValueError("waypoints must be a list of at least two coordinate objects")
    if transportation_method not in {"driving", "walking", "biking"}:
        raise ValueError("transportation_method must be one of: driving, walking, biking")

    mode_config = {
        "driving": {"port": 5000, "profile": "driving"},
        "biking": {"port": 5001, "profile": "driving"},
        "walking": {"port": 5002, "profile": "driving"},
    }
    config = mode_config[transportation_method]

    normalized_waypoints = []
    encoded_points = []
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

    url = (
        f"http://18.208.187.221:{config['port']}/route/v1/{config['profile']}/"
        + ";".join(encoded_points)
        + "?"
        + urllib.parse.urlencode({
            "overview": "false",
            "steps": "true",
            "annotations": "false",
            "geometries": "polyline",
        })
    )

    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    output_waypoints = []
    for waypoint in payload.get("waypoints", []):
        location = waypoint.get("location") or [None, None]
        longitude = location[0] if len(location) > 0 else None
        latitude = location[1] if len(location) > 1 else None
        output_waypoints.append({
            "name": waypoint.get("name"),
            "latitude": float(latitude) if latitude is not None else None,
            "longitude": float(longitude) if longitude is not None else None,
        })

    routes = []
    for route in payload.get("routes", []):
        legs_out = []
        for leg in route.get("legs", []):
            steps_out = []
            for step in leg.get("steps", []):
                steps_out.append({
                    "mode": step.get("mode"),
                    "distance_meters": step.get("distance"),
                    "duration_seconds": step.get("duration"),
                    "name": step.get("name"),
                    "maneuver": step.get("maneuver"),
                })
            legs_out.append({"steps": steps_out})
        routes.append({
            "duration_seconds": route.get("duration"),
            "distance_meters": route.get("distance"),
            "legs": legs_out,
        })

    return {
        "transportation_method": transportation_method,
        "code": payload.get("code"),
        "input_waypoints": normalized_waypoints,
        "waypoints": output_waypoints,
        "routes": routes,
        "route_count": len(routes),
    }
