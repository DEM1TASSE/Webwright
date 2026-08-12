def get_project_by_path(self, project_path_with_namespace: str) -> dict:
    from urllib.parse import quote

    encoded_project = quote(project_path_with_namespace, safe="")
    url = f"{self.base_url}/api/v4/projects/{encoded_project}"
    response = self.page.request.get(url, headers={"Accept": "application/json"})
    if not response.ok:
        raise RuntimeError(f"GitLab project API request failed: {response.status} {url}")

    item = response.json()
    return {
        "project": {
            "id": item.get("id"),
            "name": item.get("name"),
            "path": item.get("path"),
            "path_with_namespace": item.get("path_with_namespace"),
            "default_branch": item.get("default_branch"),
            "web_url": item.get("web_url"),
            "ssh_url_to_repo": item.get("ssh_url_to_repo"),
            "http_url_to_repo": item.get("http_url_to_repo"),
        }
    }
