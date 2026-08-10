def list_repository_commits(self, base_url: str, project_id: int, since: str | None = None, until: str | None = None, per_page: int | None = None, page_number: int | None = None) -> dict:
    import json
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    params = {}
    if since is not None:
        params["since"] = since
    if until is not None:
        params["until"] = until
    if per_page is not None:
        params["per_page"] = str(per_page)
    if page_number is not None:
        params["page"] = str(page_number)

    url = base_url.rstrip("/") + f"/api/v4/projects/{project_id}/repository/commits"
    if params:
        url += "?" + urlencode(params)

    request = Request(url)
    with urlopen(request) as response:
        payload = json.loads(response.read().decode("utf-8"))
        headers = {k: v for k, v in response.headers.items()}

    def _to_int(value):
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    commits = []
    for item in payload:
        commits.append({
            "id": item.get("id"),
            "short_id": item.get("short_id"),
            "title": item.get("title"),
            "message": item.get("message"),
            "author_name": item.get("author_name"),
            "author_email": item.get("author_email"),
            "authored_date": item.get("authored_date"),
            "committer_name": item.get("committer_name"),
            "committer_email": item.get("committer_email"),
            "committed_date": item.get("committed_date"),
            "created_at": item.get("created_at"),
            "parent_ids": item.get("parent_ids") or [],
            "web_url": item.get("web_url"),
        })

    return {
        "project_id": project_id,
        "commits": commits,
        "pagination": {
            "page_number": _to_int(headers.get("X-Page")),
            "per_page": _to_int(headers.get("X-Per-Page")),
            "next_page": _to_int(headers.get("X-Next-Page")),
            "prev_page": _to_int(headers.get("X-Prev-Page")),
        },
        "source_url": url,
    }
