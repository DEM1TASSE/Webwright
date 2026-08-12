def search_issues(self, query: str, scope: str = "issues", page_number: int = 1) -> dict:
    from urllib.parse import urlencode
    import re

    params = {
        "search": query,
        "scope": scope,
        "page": page_number,
    }
    url = f"{self.base_url}/search?{urlencode(params)}"
    self.page.goto(url, wait_until="networkidle")

    cards = self.page.locator('.issue, .search-result-row, .search-result, li[data-testid="search-result-row"]')
    card_count = cards.count()
    results = []

    for i in range(card_count):
        card = cards.nth(i)
        text = (card.inner_text() or "").strip()
        if not text:
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        state = None
        title = None
        if lines:
            first = lines[0].lower()
            if first in {"open", "opened", "closed"}:
                state = "closed" if first == "closed" else "opened"
        if len(lines) >= 2:
            title = lines[1]
        elif len(lines) == 1 and state is None:
            title = lines[0]

        link = card.locator('a[href*="/issues/"]').first
        href = link.get_attribute("href") if link.count() > 0 else None
        if href and not href.startswith("http://") and not href.startswith("https://"):
            href = f"{self.base_url}{href if href.startswith('/') else '/' + href}"

        issue_iid = None
        if href:
            match = re.search(r'/issues/(\d+)', href)
            if match:
                issue_iid = int(match.group(1))

        if title or href:
            results.append({
                "title": title,
                "state": state,
                "url": href,
                "issue_iid": issue_iid,
                "order_index": len(results),
            })

    return {
        "query": query,
        "scope": scope,
        "page_number": page_number,
        "results": results,
        "is_complete_page": False,
    }
