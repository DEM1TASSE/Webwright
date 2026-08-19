def search_places_in_sidebar(self, query):
    import urllib.parse
    import re
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")

    query = query.strip()
    encoded = urllib.parse.quote(query)
    self.page.goto(f"/search?query={encoded}", wait_until="domcontentloaded")
    try:
        self.page.wait_for_load_state("networkidle", timeout=10000)
    except PlaywrightTimeoutError:
        pass

    sidebar = self.page.locator("#sidebar_content")
    try:
        sidebar_text = sidebar.inner_text(timeout=5000)
    except Exception as e:
        raise RuntimeError("search results sidebar was not available") from e

    lines = [line.strip() for line in sidebar_text.splitlines() if line.strip()]
    records = []
    current = None

    def flush_current():
        nonlocal current
        if current and current.get("name"):
            current["result_rank"] = len(records) + 1
            records.append(current)
        current = None

    for line in lines:
        if line.lower() in {"search", "directions", "export", "share", "edit"}:
            continue
        if line.startswith("http://") or line.startswith("https://"):
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?\s*(?:km|m|mi|ft)", line, flags=re.IGNORECASE):
            if current is not None and not current.get("detail_text"):
                current["detail_text"] = line
            continue
        if current is None:
            current = {
                "name": line,
                "address_or_location": None,
                "detail_text": None,
            }
        elif current.get("address_or_location") is None:
            current["address_or_location"] = line
        else:
            if current.get("detail_text"):
                current["detail_text"] += " | " + line
            else:
                current["detail_text"] = line

    flush_current()

    return {
        "query": query,
        "records": records,
        "sidebar_text": sidebar_text,
    }
