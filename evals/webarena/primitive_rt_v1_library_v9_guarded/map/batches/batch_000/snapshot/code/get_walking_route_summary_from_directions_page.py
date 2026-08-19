def get_walking_route_summary_from_directions_page(self, origin: dict, destination: dict) -> dict:
    import re

    if not isinstance(origin, dict) or not isinstance(destination, dict):
        raise ValueError("origin and destination must be objects")
    try:
        origin_lat = float(origin["lat"])
        origin_lon = float(origin["lon"])
        destination_lat = float(destination["lat"])
        destination_lon = float(destination["lon"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("origin and destination must include numeric lat and lon")

    route_url = (
        "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:3000/directions"
        f"?engine=fossgis_osrm_foot&route={origin_lat},{origin_lon};{destination_lat},{destination_lon}"
    )

    self.page.goto(route_url, wait_until="domcontentloaded")
    self.page.wait_for_timeout(2500)

    body_text = self.page.locator("body").inner_text()
    distance_text = None
    duration_text = None
    duration_minutes = None

    match = re.search(r"Distance:\s*([^\.]+?)\.\s*Time:\s*(0:\d{2})", body_text)
    if match:
        distance_text = match.group(1).strip()
        duration_text = match.group(2).strip()
        duration_minutes = int(duration_text.split(":", 1)[1])
    else:
        match2 = re.search(r"Distance:\s*(.*?)\s*Time:\s*(.*?)\n", body_text, re.S)
        if match2:
            distance_text = match2.group(1).strip() or None
            duration_text = match2.group(2).strip() or None
            if duration_text:
                hhmm = re.fullmatch(r"0:(\d{2})", duration_text)
                if hhmm:
                    duration_minutes = int(hhmm.group(1))

    return {
        "route_url": self.page.url,
        "travel_mode": "foot",
        "origin": {"lat": origin_lat, "lon": origin_lon},
        "destination": {"lat": destination_lat, "lon": destination_lon},
        "distance_text": distance_text,
        "duration_text": duration_text,
        "duration_minutes": duration_minutes,
    }