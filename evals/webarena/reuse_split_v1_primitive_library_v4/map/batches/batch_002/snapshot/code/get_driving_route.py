def get_driving_route(self, waypoints: list, overview=False, steps: bool = True, geometries: str = "polyline", alternatives: bool = False):
    import json
    import urllib.parse
    import urllib.request

    if not isinstance(waypoints, list) or len(waypoints) < 2:
        raise ValueError("at least two waypoints are required")

    encoded_points = []
    for waypoint in waypoints:
        if "longitude" not in waypoint or "latitude" not in waypoint:
            raise ValueError("each waypoint must include latitude and longitude")
        encoded_points.append(f"{waypoint['longitude']},{waypoint['latitude']}")

    coords = ";".join(encoded_points)
    base_url = "http://18.208.187.221:5000/route/v1/driving/" + coords
    params = {
        "overview": str(overview).lower() if isinstance(overview, bool) else overview,
        "steps": str(steps).lower(),
        "geometries": geometries,
        "alternatives": str(alternatives).lower(),
    }
    url = base_url + "?" + urllib.parse.urlencode(params)

    with urllib.request.urlopen(url, timeout=30) as response:
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
        "code": payload.get("code"),
        "routes": routes,
        "waypoints": returned_waypoints,
        "route_count": len(routes),
        "request_waypoint_count": len(waypoints),
    }
