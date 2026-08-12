def list_repository_commits_history_page(self, project_path: str, ref_name: str, page_number: int = 1) -> dict:
    import re
    from urllib.parse import urlencode

    if project_path.startswith("/"):
        project_path = project_path[1:]

    params = {}
    if page_number != 1:
        params["page"] = page_number
    query = f"?{urlencode(params)}" if params else ""
    url = f"{self.base_url}/{project_path}/-/commits/{ref_name}{query}"
    self.page.goto(url, wait_until="domcontentloaded")
    body_text = self.page.locator("body").inner_text()

    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    date_pattern = re.compile(r"^\d{2} [A-Z][a-z]{2}, \d{4}$")
    count_pattern = re.compile(r"^(\d+) commit(?:s)?$")
    author_pattern = re.compile(r"^(.*?) authored$")

    date_groups = []
    current_group = None

    for line in lines:
        if date_pattern.match(line):
            current_group = {
                "date_label": line,
                "displayed_commit_count": None,
                "commits": [],
            }
            date_groups.append(current_group)
            continue

        if current_group is None:
            continue

        count_match = count_pattern.match(line)
        if count_match and current_group["displayed_commit_count"] is None:
            current_group["displayed_commit_count"] = int(count_match.group(1))
            continue

        author_match = author_pattern.match(line)
        if author_match:
            author_name = author_match.group(1).strip()
            current_group["commits"].append({
                "author_display_name": author_name if author_name else None,
                "authored_text": line,
            })

    return {
        "project_path": project_path,
        "ref_name": ref_name,
        "page_number": page_number,
        "commits_page_url": url,
        "date_groups": date_groups,
        "completeness": "current_commits_page_only",
    }
