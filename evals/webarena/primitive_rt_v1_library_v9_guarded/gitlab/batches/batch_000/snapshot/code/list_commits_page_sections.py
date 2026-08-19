def list_commits_page_sections(self, commits_page_url):
    import re

    if not commits_page_url:
        raise ValueError("commits_page_url is required")

    response = self.page.goto(commits_page_url, wait_until="domcontentloaded")
    if response is None:
        raise RuntimeError("Failed to load repository commits page")
    status = response.status if hasattr(response, "status") else None
    if status is not None and status >= 400:
        raise RuntimeError(f"Repository commits page request failed with status {status}")

    body_text = self.page.locator("body").inner_text()
    lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    header_pattern = re.compile(r"^(\d{2} [A-Za-z]{3}, \d{4})\s+(\d+) commits?$")

    sections = []
    current = None
    for line in lines:
        header_match = header_pattern.match(line)
        if header_match:
            if current is not None:
                sections.append(current)
            current = {
                "date_label": header_match.group(1),
                "displayed_commit_count": int(header_match.group(2)),
                "visible_lines": [],
            }
            continue
        if current is not None:
            current["visible_lines"].append(line)

    if current is not None:
        sections.append(current)

    return {"date_sections": sections}
