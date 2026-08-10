def get_osrm_route(self, coordinates: list, profile: str = "car", overview: bool = False, steps: bool = True) -> dict:
    """Request an OSRM route for ordered waypoint coordinates."""
    import urllib.parse
    import urllib.request
    import json

    if len(coordinates) < 2:
        raise ValueError("at least two coordinates are required")

    profile_endpoints = {
        "car": "http://18.208.187.221:5000/route/v1/driving/",
        "foot": "http://18.208.187.221:5002/route/v1/driving/",
    }
    if profile not in profile_endpoints:
        raise ValueError("profile must be one of: car, foot")

    encoded_coordinates = []
    normalized_coordinates = []
    for coord in coordinates:
        lon = coord["lon"]
        lat = coord["lat"]
        encoded_coordinates.append(f"{lon},{lat}")
        normalized_coordinates.append({"lon": lon, "lat": lat})

    params = {
        "overview": "true" if overview else "false",
        "steps": "true" if steps else "false",
    }
    request_url = profile_endpoints[profile] + ";".join(encoded_coordinates) + "?" + urllib.parse.urlencode(params)

    with urllib.request.urlopen(request_url, timeout=60) as response:
        data = json.load(response)

    routes = []
    for route in data.get("routes", []):
        legs = []
        for index, leg in enumerate(route.get("legs", []), start=1):
            legs.append({
                "leg_index": index,
                "duration_seconds": leg.get("duration"),
                "distance_meters": leg.get("distance"),
            })
        routes.append({
            "duration_seconds": route.get("duration"),
            "distance_meters": route.get("distance"),
            "legs": legs,
        })

    return {
        "code": data.get("code"),
        "profile": profile,
        "request_url": request_url,
        "coordinates": normalized_coordinates,
        "routes": routes,
    }
