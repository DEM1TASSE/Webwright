def inspect_project_page_availability(self, base_url: str, namespace: str, project_name: str) -> dict:
    requested_path = f"/{namespace.strip('/')}/{project_name.strip('/')}"
    url = base_url.rstrip("/") + requested_path

    self.page.goto(url, wait_until="domcontentloaded")
    page_title = self.page.title()
    body_text = self.page.locator("body").inner_text()

    lowered = body_text.lower()
    if "page not found" in lowered or "the page could not be found" in lowered or "not found" in lowered:
        availability = "NOT_FOUND_OR_INACCESSIBLE"
    elif self.page.url.rstrip("/") == url.rstrip("/"):
        availability = "ACCESSIBLE"
    else:
        availability = "UNKNOWN"

    return {
        "requested_path": requested_path,
        "project_url": self.page.url,
        "page_title": page_title,
        "availability": availability,
    }
