def get_issue_details(self, base_url: str, username: str, password: str, project: str | int, issue_iid: int) -> dict:
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
        f"{base_url}/api/v4/projects/{project_identifier}/issues/{issue_iid}",
        timeout=30,
    )
    response.raise_for_status()
    item = response.json()

    return {
        "id": item.get("id"),
        "project_id": item.get("project_id"),
        "iid": item.get("iid"),
        "title": item.get("title"),
        "state": item.get("state"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "closed_at": item.get("closed_at"),
        "web_url": item.get("web_url"),
    }
