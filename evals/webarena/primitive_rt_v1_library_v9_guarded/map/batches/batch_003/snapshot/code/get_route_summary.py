def get_route_summary(self, origin_query, destination_query, travel_mode):
    import re
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    if not isinstance(origin_query, str) or not origin_query.strip():
        raise ValueError("origin_query must be a non-empty string")
    if not isinstance(destination_query, str) or not destination_query.strip():
        raise ValueError("destination_query must be a non-empty string")
    if travel_mode not in {"car", "walking"}:
        raise ValueError("travel_mode must be one of: car, walking")

    origin_query = origin_query.strip()
    destination_query = destination_query.strip()

    self.page.goto("/directions", wait_until="domcontentloaded")

    from_box = self.page.get_by_role("textbox", name="From")
    to_box = self.page.get_by_role("textbox", name="To")
    if from_box.count() == 0 or to_box.count() == 0:
        route_from = self.page.locator("#route_from")
        route_to = self.page.locator("#route_to")
        if route_from.count() == 0 or route_to.count() == 0:
            raise RuntimeError("Directions input boxes were not found")
        from_target = route_from.nth(1 if route_from.count() > 1 else 0)
        to_target = route_to.nth(1 if route_to.count() > 1 else 0)
    else:
        from_target = from_box.first
        to_target = to_box.first

    from_target.fill(origin_query)
    to_target.fill(destination_query)

    mode_map = {"car": "Car (OSRM)", "walking": "Foot (OSRM)"}
    desired_label = mode_map[travel_mode]

    selected = False
    combobox = self.page.get_by_role("combobox")
    if combobox.count() > 0:
        try:
            combobox.first.select_option(label=desired_label)
            selected = True
        except Exception:
            selected = False

    if not selected:
        selects = self.page.locator("select.routing_engines")
        if selects.count() > 0:
            target = selects.nth(1 if selects.count() > 1 else 0)
            try:
                if travel_mode == "walking":
                    target.select_option("2")
                else:
                    target.select_option(label=desired_label)
                selected = True
            except Exception:
                try:
                    target.select_option(label=desired_label)
                    selected = True
                except Exception:
                    selected = False

    if not selected:
        raise RuntimeError("Directions travel mode control could not be set")

    go_button = self.page.get_by_role("button", name="Go")
    if go_button.count() > 0:
        go_button.first.click()
    else:
        routing_go = self.page.locator(".routing_go")
        if routing_go.count() == 0:
            raise RuntimeError("Directions submit control was not found")
        routing_go.nth(1 if routing_go.count() > 1 else 0).click()

    try:
        self.page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeoutError:
        pass

    try:
        self.page.get_by_role("heading", name="Directions").wait_for(timeout=5000)
    except Exception:
        pass

    sidebar_text = None
    try:
        sidebar_text = self.page.locator("#sidebar_content").inner_text(timeout=5000)
    except Exception:
        try:
            sidebar_text = self.page.locator("body").inner_text(timeout=5000)
        except Exception as e:
            raise RuntimeError("Directions results text was not available") from e

    time_match = re.search(r"Time:\s*([^\n]+)", sidebar_text)
    distance_match = re.search(r"Distance:\s*([^\n]+)", sidebar_text)
    travel_time_text = time_match.group(1).strip() if time_match else None
    distance_text = distance_match.group(1).strip() if distance_match else None
    results_panel_present = bool(travel_time_text or distance_text or "Directions" in sidebar_text)
    if not results_panel_present:
        raise RuntimeError("Directions results were not found")

    try:
        origin_display = from_target.input_value(timeout=1000)
    except Exception:
        origin_display = origin_query
    try:
        destination_display = to_target.input_value(timeout=1000)
    except Exception:
        destination_display = destination_query

    return {
        "origin_query": origin_query,
        "destination_query": destination_query,
        "travel_mode": travel_mode,
        "origin_display": origin_display,
        "destination_display": destination_display,
        "sidebar_text": sidebar_text,
        "travel_time_text": travel_time_text,
        "distance_text": distance_text,
        "results_panel_present": results_panel_present,
        "final_url": self.page.url,
    }
