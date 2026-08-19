def get_route_summary(self, origin_query, destination_query, transport_mode=None):
    import re
    from urllib.parse import urlparse

    host = urlparse(self.page.url).netloc
    directions_url = f"{self.page.url.split('/search')[0].split('/directions')[0].rstrip('/')}/directions" if host else "/directions"
    self.page.goto(directions_url, wait_until="domcontentloaded")

    from_box = self.page.get_by_role("textbox", name="From")
    to_box = self.page.get_by_role("textbox", name="To")
    from_box.fill(origin_query)
    to_box.fill(destination_query)

    mode_control = self.page.get_by_role("combobox")
    selected_transport_mode = None
    if transport_mode is not None:
        mode_map = {
            "car_osrm": "Car (OSRM)",
        }
        if transport_mode not in mode_map:
            raise ValueError(f"Unsupported transport_mode: {transport_mode}")
        mode_control.select_option(label=mode_map[transport_mode])
        selected_transport_mode = transport_mode

    self.page.get_by_role("button", name="Go").click()
    self.page.get_by_role("heading", name="Directions").wait_for(timeout=20000)
    summary_locator = self.page.locator("p").filter(has_text="Distance:").first
    summary_locator.wait_for(timeout=20000)

    summary_text = summary_locator.inner_text().strip()
    resolved_origin = from_box.input_value().strip()
    resolved_destination = to_box.input_value().strip()
    displayed_mode_value = mode_control.input_value().strip()

    distance_text = None
    duration_text = None
    m = re.search(r"Distance:\s*(.*?)\.\s*Time:\s*(.*?)\.", summary_text)
    if m:
        distance_text = m.group(1).strip()
        duration_text = m.group(2).strip()
    else:
        distance_match = re.search(r"Distance:\s*([^\.]+)", summary_text)
        time_match = re.search(r"Time:\s*([^\.]+)", summary_text)
        if distance_match:
            distance_text = distance_match.group(1).strip()
        if time_match:
            duration_text = time_match.group(1).strip()

    if not resolved_origin or not resolved_destination:
        raise RuntimeError("Directions results did not expose resolved endpoints")
    if not summary_text:
        raise RuntimeError("Directions summary text was empty")

    return {
        "resolved_origin": resolved_origin,
        "resolved_destination": resolved_destination,
        "travel_mode": selected_transport_mode or displayed_mode_value,
        "displayed_travel_mode": displayed_mode_value,
        "summary_text": summary_text,
        "distance_text": distance_text,
        "duration_text": duration_text,
    }
