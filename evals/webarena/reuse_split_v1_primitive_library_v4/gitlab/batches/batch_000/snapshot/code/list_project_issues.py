def list_project_issues(self, project_id: int, scope: str = "all", order_by: str = "updated_at", sort: str = "desc", page_number: int = 1, per_page: int = 100) -> dict:
    from urllib.parse import urlencode

    params = {
        "scope": scope,
        "order_by": order_by,
        "sort": sort,
        "page": page_number,
        "per_page": per_page,
    }
    url = f"{self.base_url}/api/v4/projects/{project_id}/issues?{urlencode(params)}"
    response = self.page.request.get(url, headers={"Accept": "application/json"})
    if not response.ok:
        raise RuntimeError(f"GitLab issues API request failed: {response.status} {url}")

    payload = response.json()
    headers = response.headers
    next_page_raw = headers.get("x-next-page") or headers.get("X-Next-Page")
    next_page = int(next_page_raw) if next_page_raw and str(next_page_raw).strip() else None

    issues = []
    for item in payload:
        issues.append({
            "id": item.get("id"),
            "iid": item.get("iid"),
            "project_id": item.get("project_id", project_id),
            "title": item.get("title"),
            "state": item.get("state"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "closed_at": item.get("closed_at"),
            "web_url": item.get("web_url"),
        })

    return {
        "project_id": project_id,
        "scope": scope,
        "order_by": order_by,
        "sort": sort,
        "page_number": page_number,
        "per_page": per_page,
        "issues": issues,
        "next_page": next_page,
        "is_complete_page": next_page is None,
    }
