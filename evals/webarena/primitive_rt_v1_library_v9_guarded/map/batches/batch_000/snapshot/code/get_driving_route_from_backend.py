def get_driving_route_from_backend(self, origin: dict, destination: dict) -> dict:
    import requests

    if not isinstance(origin, dict) or not isinstance(destination, dict):
        raise ValueError("origin and destination must be objects")
    try:
        origin_lon = float(origin["lon"])
        origin_lat = float(origin["lat"])
        destination_lon = float(destination["lon"])
        destination_lat = float(destination["lat"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("origin and destination must include numeric lat and lon")

    url = (
        "http://18.208.187.221:5000/route/v1/driving/"
        f"{origin_lon},{origin_lat};{destination_lon},{destination_lat}"
        "?overview=false&steps=true&geometries=polyline"
    )
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("expected route response to be an object")

    routes = []
    for route in payload.get("routes", []):
        if not isinstance(route, dict):
            continue
        record = {}
        if route.get("duration") is not None:
            try:
                record["duration_sec"] = float(route.get("duration"))
            except (TypeError, ValueError):
                pass
        if route.get("distance") is not None:
            try:
                record["distance_m"] = float(route.get("distance"))
            except (TypeError, ValueError):
                pass
        if isinstance(route.get("legs"), list):
            record["legs"] = route.get("legs")
        routes.append(record)

    waypoints = payload.get("waypoints")
    if not isinstance(waypoints, list):
        waypoints = []

    return {
        "travel_mode": "car",
        "routes": routes,
        "waypoints": waypoints,
    }