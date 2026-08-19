def get_route_directions_summary(self, origin_query, destination_query, travel_mode):
    import re
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    if not isinstance(origin_query, str) or not origin_query.strip():
        raise ValueError("origin_query must be a non-empty string")
    if not isinstance(destination_query, str) or not destination_query.strip():
        raise ValueError("destination_query must be a non-empty string")
    if travel_mode not in {"car", "walking"}:
        raise ValueError("travel_mode must be one of: car, walking")

    mode_label_map = {
        "car": "Car (OSRM)",
        "walking": "Foot (OSRM)",
    }

    self.page.goto("http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:3000/directions", wait_until="domcontentloaded")
    try:
        self.page.wait_for_load_state("networkidle", timeout=10000)
    except PlaywrightTimeoutError:
        pass

    from_box = self.page.get_by_role("textbox", name="From").first
    to_box = self.page.get_by_role("textbox", name="To").first
    from_box.fill(origin_query.strip())
    to_box.fill(destination_query.strip())

    combobox = self.page.get_by_role("combobox").first
    combobox.select_option(label=mode_label_map[travel_mode])

    self.page.get_by_role("button", name="Go").first.click()
    try:
        self.page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeoutError:
        pass

    heading_present = False
    try:
        self.page.get_by_role("heading", name="Directions").first.wait_for(timeout=5000)
        heading_present = True
    except PlaywrightTimeoutError:
        heading_present = False

    sidebar_text = ""
    try:
        sidebar_text = (self.page.locator("#sidebar_content").inner_text(timeout=5000) or "").strip()
    except Exception:
        try:
            sidebar_text = (self.page.locator("body").inner_text(timeout=5000) or "").strip()
        except Exception:
            sidebar_text = ""

    duration_text = None
    distance_text = None
    m_time = re.search(r"Time:\s*([^\n]+)", sidebar_text)
    if m_time:
        duration_text = m_time.group(1).strip()
    m_distance = re.search(r"Distance:\s*([^\n]+)", sidebar_text)
    if m_distance:
        distance_text = m_distance.group(1).strip()

    origin_display = None
    destination_display = None
    try:
        origin_display = from_box.input_value()
    except Exception:
        origin_display = None
    try:
        destination_display = to_box.input_value()
    except Exception:
        destination_display = None

    results_panel_present = heading_present or ("Time:" in sidebar_text) or ("Distance:" in sidebar_text)
    if not results_panel_present:
        raise RuntimeError("Directions results panel not found after route submission")

    return {
        "origin_query": origin_query.strip(),
        "destination_query": destination_query.strip(),
        "travel_mode": travel_mode,
        "origin_display": origin_display,
        "destination_display": destination_display,
        "summary_text": sidebar_text,
        "travel_time_text": duration_text,
        "distance_text": distance_text,
        "results_panel_present": results_panel_present,
        "final_url": self.page.url,
    }