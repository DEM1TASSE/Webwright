def list_repository_commits(self, project_id_or_path, ref_name=None, author=None, since=None, until=None, per_page=None, page_number=None):
    from urllib.parse import quote, urlencode

    base_url = self._get_base_url()
    project_segment = quote(project_id_or_path, safe='')
    api_url = f"{base_url}/api/v4/projects/{project_segment}/repository/commits"

    params = {}
    if ref_name is not None:
        params["ref_name"] = ref_name
    if author is not None:
        params["author"] = author
    if since is not None:
        params["since"] = since
    if until is not None:
        params["until"] = until
    if per_page is not None:
        params["per_page"] = per_page
    if page_number is not None:
        params["page"] = page_number

    url = api_url if not params else f"{api_url}?{urlencode(params)}"
    response = self.page.goto(url, wait_until="domcontentloaded")
    if response is None:
        raise RuntimeError("Failed to load commits API response")

    try:
        payload = self.page.evaluate("() => JSON.parse(document.body.innerText)")
    except Exception as exc:
        raise RuntimeError("Commits API did not return parseable JSON") from exc

    commits = []
    for item in payload:
        commits.append({
            "id": item.get("id"),
            "short_id": item.get("short_id"),
            "title": item.get("title"),
            "author_name": item.get("author_name"),
            "author_email": item.get("author_email"),
            "authored_date": item.get("authored_date"),
            "web_url": item.get("web_url"),
        })

    return {
        "commits": commits,
        "page_number": page_number,
        "per_page": per_page,
        "raw_count": len(commits),
    }

def _get_base_url(self):
    current = self.page.url or ""
    m = __import__("re").match(r"^(https?://[^/]+)", current)
    if not m:
        raise RuntimeError("Cannot determine GitLab base URL from current page")
    return m.group(1)