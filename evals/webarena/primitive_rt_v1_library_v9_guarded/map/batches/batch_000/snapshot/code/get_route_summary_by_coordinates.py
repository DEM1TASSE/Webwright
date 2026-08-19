def get_route_summary_by_coordinates(self, origin: dict, destination: dict, travel_mode: str) -> dict:
    import requests

    def _parse_point(name: str, value: dict) -> tuple[float, float]:
        if not isinstance(value, dict):
            raise ValueError(f"{name} must be an object with lat and lon")
        try:
            lat = float(value["lat"])
            lon = float(value["lon"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"{name} must include numeric lat and lon")
        return lat, lon

    origin_lat, origin_lon = _parse_point("origin", origin)
    dest_lat, dest_lon = _parse_point("destination", destination)

    if travel_mode != "car":
        raise ValueError("travel_mode must be 'car'")

    response = requests.get(
        f"http://18.208.187.221:5000/route/v1/driving/{origin_lon},{origin_lat};{dest_lon},{dest_lat}",
        params={"overview": "false", "steps": "true", "geometries": "polyline"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("unexpected route response shape")

    raw_routes = payload.get("routes")
    routes = []
    if isinstance(raw_routes, list):
        for row in raw_routes:
            if not isinstance(row, dict):
                continue
            duration = row.get("duration")
            distance = row.get("distance")
            try:
                duration_sec = float(duration)
                distance_m = float(distance)
            except (TypeError, ValueError):
                continue
            routes.append({
                "duration_sec": duration_sec,
                "distance_m": distance_m,
            })

    waypoints_out = []
    raw_waypoints = payload.get("waypoints")
    if isinstance(raw_waypoints, list):
        for row in raw_waypoints:
            if not isinstance(row, dict):
                continue
            location = row.get("location")
            waypoint = {
                "name": str(row.get("name", "")),
                "lon": None,
                "lat": None,
            }
            if isinstance(location, list) and len(location) >= 2:
                try:
                    waypoint["lon"] = float(location[0])
                    waypoint["lat"] = float(location[1])
                except (TypeError, ValueError):
                    waypoint["lon"] = None
                    waypoint["lat"] = None
            waypoints_out.append(waypoint)

    return {
        "travel_mode": travel_mode,
        "origin": {"lat": origin_lat, "lon": origin_lon},
        "destination": {"lat": dest_lat, "lon": dest_lon},
        "routes": routes,
        "waypoints": waypoints_out,
    }
