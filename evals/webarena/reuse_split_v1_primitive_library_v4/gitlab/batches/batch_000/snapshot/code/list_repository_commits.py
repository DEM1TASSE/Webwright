def list_repository_commits(self, project_id: int, ref_name: str = None, since: str = None, until: str = None, page_number: int = 1, per_page: int = 100) -> dict:
    from urllib.parse import urlencode

    params = {
        "page": page_number,
        "per_page": per_page,
    }
    if ref_name is not None:
        params["ref_name"] = ref_name
    if since is not None:
        params["since"] = since
    if until is not None:
        params["until"] = until

    url = f"{self.base_url}/api/v4/projects/{project_id}/repository/commits?{urlencode(params)}"
    response = self.page.request.get(url, headers={"Accept": "application/json"})
    if not response.ok:
        raise RuntimeError(f"GitLab commits API request failed: {response.status} {url}")

    payload = response.json()
    headers = response.headers
    next_page_raw = headers.get("x-next-page") or headers.get("X-Next-Page")
    next_page = int(next_page_raw) if next_page_raw and str(next_page_raw).strip() else None

    commits = []
    for item in payload:
        commits.append({
            "id": item.get("id"),
            "short_id": item.get("short_id"),
            "title": item.get("title"),
            "author_name": item.get("author_name"),
            "author_email": item.get("author_email"),
            "authored_date": item.get("authored_date"),
            "committed_date": item.get("committed_date"),
            "web_url": item.get("web_url"),
        })

    return {
        "project_id": project_id,
        "ref_name": ref_name,
        "since": since,
        "until": until,
        "page_number": page_number,
        "per_page": per_page,
        "commits": commits,
        "next_page": next_page,
        "is_complete_page": next_page is None,
    }
