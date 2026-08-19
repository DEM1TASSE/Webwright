def list_branch_commit_day_summaries_from_url(self, commits_page_url: str) -> dict:
    import re

    if not isinstance(commits_page_url, str) or not commits_page_url.strip():
        raise ValueError("commits_page_url must be a non-empty string")

    response = self.page.goto(commits_page_url, wait_until="domcontentloaded")
    if response is not None and response.status >= 400:
        raise RuntimeError(f"Failed to load commits page: HTTP {response.status}")

    body_text = self.page.locator('body').inner_text()
    header_pattern = re.compile(r'(?m)^(\d{2} [A-Z][a-z]{2}, \d{4})\s+(\d+) commits?$')

    days = []
    for match in header_pattern.finditer(body_text):
        days.append({
            "day_label": match.group(1),
            "displayed_commit_count": int(match.group(2)),
        })

    return {
        "commits_page_url": commits_page_url,
        "days": days,
    }
