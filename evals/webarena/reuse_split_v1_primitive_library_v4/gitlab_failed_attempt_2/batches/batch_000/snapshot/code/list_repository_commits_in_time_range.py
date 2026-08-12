def list_repository_commits_in_time_range(self, base_url: str, username: str, password: str, project_id: int, ref_name: str, since: str, until: str, per_page: int = 100, page_number: int = 1) -> dict:
    import re
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

    response = session.get(
        f"{base_url}/api/v4/projects/{project_id}/repository/commits",
        params={
            "ref_name": ref_name,
            "since": since,
            "until": until,
            "per_page": per_page,
            "page": page_number,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected commits API response")

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
            "web_url": item.get("web_url"),
        })

    next_page = response.headers.get("X-Next-Page")
    total = response.headers.get("X-Total")
    total_pages = response.headers.get("X-Total-Pages")

    return {
        "commits": commits,
        "page_number": page_number,
        "per_page": per_page,
        "next_page_number": int(next_page) if next_page and next_page.isdigit() else None,
        "has_next_page": bool(next_page),
        "total": int(total) if total and total.isdigit() else None,
        "total_pages": int(total_pages) if total_pages and total_pages.isdigit() else None,
    }
