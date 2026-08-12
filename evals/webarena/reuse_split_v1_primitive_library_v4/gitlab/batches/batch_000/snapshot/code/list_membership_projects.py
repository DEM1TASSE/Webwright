def list_membership_projects(self, page_number: int = 1, per_page: int = 100) -> dict:
    from urllib.parse import urlencode

    params = {
        "membership": "true",
        "simple": "true",
        "page": page_number,
        "per_page": per_page,
    }
    url = f"{self.base_url}/api/v4/projects?{urlencode(params)}"
    response = self.page.request.get(url, headers={"Accept": "application/json"})
    if not response.ok:
        raise RuntimeError(f"GitLab membership projects API request failed: {response.status} {url}")

    payload = response.json()
    headers = response.headers
    next_page_raw = headers.get("x-next-page") or headers.get("X-Next-Page")
    next_page = int(next_page_raw) if next_page_raw and str(next_page_raw).strip() else None

    projects = []
    for item in payload:
        projects.append({
            "id": item.get("id"),
            "name": item.get("name"),
            "path": item.get("path"),
            "path_with_namespace": item.get("path_with_namespace"),
            "web_url": item.get("web_url"),
        })

    return {
        "page_number": page_number,
        "per_page": per_page,
        "projects": projects,
        "next_page": next_page,
        "is_complete_page": next_page is None,
    }
