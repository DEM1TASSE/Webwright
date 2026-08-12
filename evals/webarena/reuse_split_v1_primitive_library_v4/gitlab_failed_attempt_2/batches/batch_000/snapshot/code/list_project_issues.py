def list_project_issues(self, base_url: str, username: str, password: str, project: str | int, scope: str = "all", order_by: str = "updated_at", sort: str = "desc", per_page: int = 100, page_number: int = 1) -> dict:
    import re
    from urllib.parse import quote
    import requests

    session = requests.Session()
    sign_in = session.get(f"{base_url}/users/sign_in", timeout=30)
    sign_in.raise_for_status()
    match = re.search(r'name="authenticity_token" value="([^"]+)"', sign_in.text)
    if not match:
        raise RuntimeError("Could not find authenticity token on sign-in page")

    login_resp = session.post(
        f"{base_url}/users/sign_in",
        data={
            "authenticity_token": match.group(1),
            "user[login]": username,
            "user[password]": password,
            "user[remember_me]": "0",
        },
        timeout=30,
        allow_redirects=True,
    )
    login_resp.raise_for_status()

    project_identifier = str(project)
    if isinstance(project, str) and "/" in project:
        project_identifier = quote(project, safe="")

    response = session.get(
        f"{base_url}/api/v4/projects/{project_identifier}/issues",
        params={
            "scope": scope,
            "order_by": order_by,
            "sort": sort,
            "per_page": per_page,
            "page": page_number,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected issues API response")

    issues = []
    for item in payload:
        issues.append({
            "id": item.get("id"),
            "project_id": item.get("project_id"),
            "iid": item.get("iid"),
            "title": item.get("title"),
            "state": item.get("state"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "closed_at": item.get("closed_at"),
            "web_url": item.get("web_url"),
        })

    next_page = response.headers.get("X-Next-Page")
    total = response.headers.get("X-Total")
    total_pages = response.headers.get("X-Total-Pages")

    return {
        "issues": issues,
        "page_number": page_number,
        "per_page": per_page,
        "order_by": order_by,
        "sort": sort,
        "next_page_number": int(next_page) if next_page and next_page.isdigit() else None,
        "has_next_page": bool(next_page),
        "total": int(total) if total and total.isdigit() else None,
        "total_pages": int(total_pages) if total_pages and total_pages.isdigit() else None,
    }
