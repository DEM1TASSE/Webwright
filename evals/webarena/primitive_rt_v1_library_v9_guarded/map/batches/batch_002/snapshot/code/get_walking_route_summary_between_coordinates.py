def get_walking_route_summary_between_coordinates(self, origin, destination):
    import re
    from urllib.parse import quote

    def _validate_point(name, value):
        if not isinstance(value, dict):
            raise ValueError(f"{name} must be an object with latitude and longitude")
        if "latitude" not in value or "longitude" not in value:
            raise ValueError(f"{name} must include latitude and longitude")
        latitude = float(value["latitude"])
        longitude = float(value["longitude"])
        if latitude < -90 or latitude > 90:
            raise ValueError(f"{name}.latitude must be between -90 and 90")
        if longitude < -180 or longitude > 180:
            raise ValueError(f"{name}.longitude must be between -180 and 180")
        return latitude, longitude

    def _parse_distance_meters(distance_text):
        if not distance_text:
            return None
        s = distance_text.strip().lower().replace(" ", "")
        if s.endswith("km"):
            return float(s[:-2]) * 1000
        if s.endswith("m"):
            return float(s[:-1])
        return None

    origin_lat, origin_lon = _validate_point("origin", origin)
    destination_lat, destination_lon = _validate_point("destination", destination)

    engine_by_mode = {
        "walking": "fossgis_osrm_foot",
    }
    route_value = f"{origin_lat},{origin_lon};{destination_lat},{destination_lon}"
    route_url = (
        "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:3000/"
        f"directions?engine={engine_by_mode['walking']}&route={quote(route_value, safe='')}"
    )

    self.page.goto(route_url, wait_until="domcontentloaded")
    self.page.wait_for_timeout(3000)

    body = self.page.locator("body").inner_text()
    match = re.search(r"Distance:\s*([^\.]+)\.\s*Time:\s*([^\.]+)\.", body)
    if not match:
        raise RuntimeError("The directions page did not contain a parseable walking route summary")

    distance_text = match.group(1).strip()
    duration_text = match.group(2).strip()
    return {
        "route": {
            "distance_text": distance_text,
            "duration_text": duration_text,
            "distance_meters": _parse_distance_meters(distance_text),
            "route_url": self.page.url,
        }
    }
