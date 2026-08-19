def get_route_summary_with_destination_fallbacks(self, origin: str, destination_queries, routing_mode: str):
    import re

    if not isinstance(origin, str) or not origin.strip():
        raise ValueError("origin must be a non-empty string")
    if not isinstance(destination_queries, list) or not destination_queries:
        raise ValueError("destination_queries must be a non-empty list of strings")
    cleaned_queries = []
    for q in destination_queries:
        if not isinstance(q, str) or not q.strip():
            raise ValueError("each destination query must be a non-empty string")
        cleaned_queries.append(q.strip())
    if routing_mode not in {"foot", "car"}:
        raise ValueError("routing_mode must be one of: foot, car")

    base_url = "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:3000"
    directions_url = f"{base_url}/directions"
    mode_to_label = {
        "foot": "Foot (OSRM)",
        "car": "Car (OSRM)",
    }
    attempted = []

    for candidate in cleaned_queries:
        self.page.goto(directions_url, wait_until="domcontentloaded")
        self.page.wait_for_load_state("networkidle")

        from_input = self.page.locator('input[name="route_from"]').nth(1)
        to_input = self.page.locator('input[name="route_to"]').nth(1)
        engine_select = self.page.locator('select.routing_engines').nth(1)
        go_button = self.page.locator('input.routing_go').nth(1)

        from_input.wait_for(state="visible", timeout=15000)
        to_input.wait_for(state="visible", timeout=15000)
        engine_select.wait_for(state="visible", timeout=15000)
        go_button.wait_for(state="visible", timeout=15000)

        from_input.fill("")
        from_input.fill(origin.strip())
        to_input.fill("")
        to_input.fill(candidate)
        engine_select.select_option(label=mode_to_label[routing_mode])
        attempted.append(candidate)
        go_button.click()

        try:
            self.page.wait_for_function(
                """() => {
                    const t = document.body ? document.body.innerText : '';
                    return t.includes('Distance:') && t.includes('Time:');
                }""",
                timeout=25000,
            )
            body = self.page.locator("body").inner_text()
            duration_match = re.search(r"Distance:\s*[^\n]*?Time:\s*([0-9]+:[0-9]{2})", body)
            if not duration_match:
                duration_match = re.search(r"Time:\s*([0-9]+:[0-9]{2})", body)
            distance_match = re.search(r"Distance:\s*([^\.\n]+)", body)
            if duration_match:
                return {
                    "origin_query": origin.strip(),
                    "successful_destination_query": candidate,
                    "attempted_destination_queries": attempted,
                    "routing_mode": routing_mode,
                    "duration_text": duration_match.group(1),
                    "distance_text": distance_match.group(1).strip() if distance_match else None,
                    "raw_summary_text": body,
                    "result_url": self.page.url,
                }
        except Exception:
            pass

    raise RuntimeError(f"Could not obtain route result after attempts: {attempted}")
