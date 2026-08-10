def list_project_members(self, base_url: str, project_path: str) -> dict:
    import html
    import json
    import re

    normalized_project_path = project_path if project_path.startswith("/") else f"/{project_path}"
    url = base_url.rstrip("/") + normalized_project_path + "/-/project_members"

    self.page.goto(url, wait_until="domcontentloaded")
    content = self.page.content()

    match = re.search(r'data-members-data="([^"]+)"', content)
    if not match:
        raise ValueError("Could not find structured members data on project members page")

    decoded = html.unescape(match.group(1))
    data = json.loads(decoded)
    raw_members = (((data.get("user") or {}).get("members")) or [])

    members = []
    for member in raw_members:
        user = member.get("user") or {}
        access_level = member.get("access_level") or {}
        members.append({
            "username": user.get("username"),
            "name": user.get("name"),
            "id": user.get("id"),
            "state": user.get("state"),
            "avatar_url": user.get("avatar_url"),
            "web_url": user.get("web_url"),
            "access_level": access_level.get("string_value"),
            "access_level_integer": access_level.get("integer_value"),
            "member_type": member.get("type"),
            "expires_at": member.get("expires_at"),
        })

    return {
        "project_path": normalized_project_path,
        "members": members,
        "source_url": url,
    }
