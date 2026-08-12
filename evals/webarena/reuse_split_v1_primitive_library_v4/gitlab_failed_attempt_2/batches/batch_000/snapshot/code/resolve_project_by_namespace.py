def resolve_project_by_namespace(self, base_url: str, username: str, password: str, project_path_with_namespace: str) -> dict:
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

    response = session.get(
        f"{base_url}/api/v4/projects/{quote(project_path_with_namespace, safe='')}",
        timeout=30,
    )
    response.raise_for_status()
    project = response.json()

    return {
        "id": project.get("id"),
        "name": project.get("name"),
        "path": project.get("path"),
        "path_with_namespace": project.get("path_with_namespace"),
        "web_url": project.get("web_url"),
        "default_branch": project.get("default_branch"),
    }
