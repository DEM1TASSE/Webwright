def search_projects(self, search_query: str) -> dict:
    import requests

    if not isinstance(search_query, str) or not search_query.strip():
        raise ValueError("search_query must be a non-empty string")

    base_url = "http://GCRSANDBOX410.redmond.corp.microsoft.com:8023"
    response = requests.get(
        f"{base_url}/api/v4/projects",
        params={"search": search_query.strip()},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError("Expected list response from GitLab projects search API")

    projects = []
    for item in data:
        if not isinstance(item, dict):
            continue
        project_id = item.get("id")
        if project_id is not None:
            try:
                project_id = int(project_id)
            except Exception:
                project_id = None
        projects.append({
            "id": project_id,
            "path_with_namespace": item.get("path_with_namespace"),
            "web_url": item.get("web_url"),
        })

    return {"projects": projects}
