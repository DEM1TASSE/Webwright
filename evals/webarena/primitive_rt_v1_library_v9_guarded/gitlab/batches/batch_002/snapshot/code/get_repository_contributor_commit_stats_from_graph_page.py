def get_repository_contributor_commit_stats_from_graph_page(self, graph_page_url: str) -> dict:
    import re

    if not isinstance(graph_page_url, str) or not graph_page_url.strip():
        raise ValueError("graph_page_url must be a non-empty string")

    response = self.page.goto(graph_page_url, wait_until="networkidle")
    if response is not None and response.status >= 400:
        raise RuntimeError(f"Failed to load graph page: HTTP {response.status}")

    cards = self.page.locator('.contributors-charts .col-lg-6.col-12.gl-my-5')
    card_count = cards.count()
    contributors = []

    for i in range(card_count):
        card = cards.nth(i)
        name = card.locator('h4').first.inner_text().strip()
        if not name:
            continue
        summary_locator = card.locator('p').first
        summary = summary_locator.inner_text().strip() if summary_locator.count() > 0 else ''
        match = re.search(r'(\d+)\s+commit', summary)
        commits = int(match.group(1)) if match else -1
        contributors.append({
            "name": name,
            "summary": summary,
            "commits": commits,
        })

    return {"contributors": contributors}
