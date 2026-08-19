def collect_all_repository_commits(self, project_id: int, ref_name: str, per_page: int) -> dict:
    import requests

    if not isinstance(project_id, int):
        raise ValueError("project_id must be an integer")
    if not isinstance(ref_name, str) or not ref_name.strip():
        raise ValueError("ref_name must be a non-empty string")
    if not isinstance(per_page, int) or per_page < 1:
        raise ValueError("per_page must be an integer >= 1")

    base_url = "http://GCRSANDBOX410.redmond.corp.microsoft.com:8023"
    all_commits = []
    page_number = 1
    pages_fetched = 0
    termination_condition = None

    while True:
        response = requests.get(
            f"{base_url}/api/v4/projects/{project_id}/repository/commits",
            params={"ref_name": ref_name, "page": page_number, "per_page": per_page},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise RuntimeError("Expected list response from GitLab commits API")

        pages_fetched += 1
        batch = []
        for item in data:
            if not isinstance(item, dict):
                continue
            batch.append({
                "id": item.get("id"),
                "short_id": item.get("short_id"),
                "title": item.get("title"),
                "author_name": item.get("author_name"),
                "author_email": item.get("author_email"),
                "committer_name": item.get("committer_name"),
                "committer_email": item.get("committer_email"),
                "committed_date": item.get("committed_date"),
                "web_url": item.get("web_url"),
            })

        if not batch:
            termination_condition = "empty_page"
            break

        all_commits.extend(batch)

        if len(batch) < per_page:
            termination_condition = "short_page"
            break

        page_number += 1

    return {
        "commits": all_commits,
        "pagination_summary": {
            "pages_fetched": pages_fetched,
            "per_page": per_page,
            "termination_condition": termination_condition,
        },
    }
