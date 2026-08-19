def list_repository_contributors(self, project_id: int) -> dict:
    import requests

    if not isinstance(project_id, int):
        raise ValueError("project_id must be an integer")

    base_url = "http://GCRSANDBOX410.redmond.corp.microsoft.com:8023"
    response = requests.get(
        f"{base_url}/api/v4/projects/{project_id}/repository/contributors",
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise RuntimeError("Expected list response from GitLab contributors API")

    contributors = []
    for item in data:
        if not isinstance(item, dict):
            continue
        commits = item.get("commits")
        if commits is not None:
            try:
                commits = int(commits)
            except Exception:
                commits = None
        contributors.append({
            "name": item.get("name"),
            "email": item.get("email"),
            "commits": commits,
        })

    return {"contributors": contributors}
