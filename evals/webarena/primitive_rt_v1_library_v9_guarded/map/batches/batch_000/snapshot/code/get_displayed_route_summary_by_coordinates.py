def get_displayed_route_summary_by_coordinates(self, origin: dict, destination: dict, travel_mode: str) -> dict:
    import re

    def _validate_point(name: str, value: dict):
        if not isinstance(value, dict):
            raise ValueError(f"{name} must be an object with lat and lon")
        try:
            lat = float(value["lat"])
            lon = float(value["lon"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"{name} must include numeric lat and lon")
        return lat, lon

    origin_lat, origin_lon = _validate_point("origin", origin)
    dest_lat, dest_lon = _validate_point("destination", destination)

    if travel_mode == "car":
        route_url = (
            "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:3000"
            f"/directions?from={origin_lat},{origin_lon}&to={dest_lat},{dest_lon}&engine=fossgis_osrm_car"
        )
    elif travel_mode == "foot":
        route_url = (
            "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:3000"
            f"/directions?engine=fossgis_osrm_foot&route={origin_lat},{origin_lon};{dest_lat},{dest_lon}"
        )
    else:
        raise ValueError("travel_mode must be one of: car, foot")

    self.page.goto(route_url, wait_until="domcontentloaded")
    self.page.wait_for_timeout(2500)
    body_text = self.page.locator("body").inner_text()

    distance_text = None
    duration_text = None
    duration_minutes = None

    summary_match = re.search(r"Distance:\s*([^\.\n]+(?:m|km))\.\s*Time:\s*([^\n]+)", body_text)
    if summary_match:
        distance_text = summary_match.group(1).strip()
        duration_text = summary_match.group(2).strip().rstrip(".")
    else:
        for line in body_text.splitlines():
            line = line.strip()
            if line.startswith("Distance:"):
                distance_part = line.split("Time:", 1)[0]
                distance_text = distance_part.split("Distance:", 1)[1].strip().rstrip(".")
                if "Time:" in line:
                    duration_text = line.split("Time:", 1)[1].strip().rstrip(".")
                break

    if duration_text:
        minute_match = re.fullmatch(r"0:(\d{2})", duration_text)
        if minute_match:
            duration_minutes = int(minute_match.group(1))

    return {
        "route_url": self.page.url,
        "travel_mode": travel_mode,
        "origin": {"lat": origin_lat, "lon": origin_lon},
        "destination": {"lat": dest_lat, "lon": dest_lon},
        "distance_text": distance_text,
        "duration_text": duration_text,
        "duration_minutes": duration_minutes,
        "page_summary_text": body_text,
        "has_route": (distance_text is not None or duration_text is not None),
    }
