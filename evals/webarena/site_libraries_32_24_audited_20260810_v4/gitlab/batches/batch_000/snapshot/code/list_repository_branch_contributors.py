def list_repository_branch_contributors(self, base_url: str, project_path: str, branch_name: str, limit: int | None = None) -> dict:
    import re

    normalized_project_path = project_path.strip("/")
    url = base_url.rstrip("/") + f"/{normalized_project_path}/-/graphs/{branch_name}"

    self.page.goto(url, wait_until="networkidle")
    text = self.page.locator("main").inner_text()

    pattern = re.compile(r"([A-Za-z][A-Za-z0-9.'\-\[\] ]*[A-Za-z0-9\]])\n\n(\d+) commits? \(")
    matches = pattern.findall(text)

    contributors = []
    seen = set()
    for name, commits in matches:
        full_name = " ".join(name.split())
        commit_count = int(commits)
        key = (full_name, commit_count)
        if key in seen:
            continue
        seen.add(key)
        contributors.append({
            "rank": len(contributors) + 1,
            "full_name": full_name,
            "commit_count": commit_count,
        })

    is_partial = False
    if limit is not None:
        contributors = contributors[:limit]
        is_partial = True

    return {
        "project_path": "/" + normalized_project_path,
        "branch_name": branch_name,
        "contributors": contributors,
        "is_partial": is_partial,
        "source_url": url,
    }
