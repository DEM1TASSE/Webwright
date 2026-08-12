def get_issue_details(self, project_path_with_namespace: str, issue_iid: int) -> dict:
    from urllib.parse import quote

    encoded_project = quote(project_path_with_namespace, safe="")
    url = f"{self.base_url}/api/v4/projects/{encoded_project}/issues/{issue_iid}"
    response = self.page.request.get(url, headers={"Accept": "application/json"})
    if not response.ok:
        raise RuntimeError(f"GitLab issue detail API request failed: {response.status} {url}")

    item = response.json()
    return {
        "issue": {
            "id": item.get("id"),
            "iid": item.get("iid"),
            "project_id": item.get("project_id"),
            "project_path_with_namespace": project_path_with_namespace,
            "title": item.get("title"),
            "description": item.get("description"),
            "state": item.get("state"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "closed_at": item.get("closed_at"),
            "web_url": item.get("web_url"),
        }
    }
