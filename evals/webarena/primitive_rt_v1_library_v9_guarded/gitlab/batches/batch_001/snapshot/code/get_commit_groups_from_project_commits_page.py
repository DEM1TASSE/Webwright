def get_commit_groups_from_project_commits_page(self, project_url: str, ref_name: str) -> dict:
    import re

    if not isinstance(project_url, str) or not project_url.strip():
        raise ValueError("project_url must be a non-empty string")
    if not isinstance(ref_name, str) or not ref_name.strip():
        raise ValueError("ref_name must be a non-empty string")

    project_url = project_url.rstrip("/")
    commits_url = f"{project_url}/-/commits/{ref_name}"
    self.page.goto(commits_url, wait_until="domcontentloaded")

    body_text = self.page.locator("body").inner_text()
    lines = [line.strip() for line in body_text.splitlines() if line.strip()]

    header_pattern = re.compile(r"^(?P<date_label>\d{2}\s+[A-Za-z]{3},\s+\d{4})\s+(?P<count>\d+)\s+commit(?:s)?$")
    commit_groups = []
    current_group = None

    for line in lines:
        match = header_pattern.match(line)
        if match:
            if current_group is not None:
                commit_groups.append(current_group)
            current_group = {
                "date_label": match.group("date_label"),
                "displayed_commit_count": int(match.group("count")),
                "entries": [],
            }
            continue

        if current_group is None:
            continue

        if " authored" in line:
            author_display = line.split(" authored", 1)[0].strip() or None
            current_group["entries"].append({
                "author_display": author_display,
                "attribution_line": line,
            })

    if current_group is not None:
        commit_groups.append(current_group)

    return {
        "commit_groups": commit_groups,
        "page_url": self.page.url,
    }
