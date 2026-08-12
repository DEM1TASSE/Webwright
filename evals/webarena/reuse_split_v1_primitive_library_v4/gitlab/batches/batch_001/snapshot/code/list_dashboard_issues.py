def list_dashboard_issues(self, assignee_username: str, state: str, search_query: str, sort: str, page_number: int = 1) -> dict:
    import re
    from urllib.parse import urlencode

    params = {
        "assignee_username": assignee_username,
        "state": state,
        "search": search_query,
        "sort": sort,
        "page": page_number,
    }
    url = f"{self.base_url}/dashboard/issues?{urlencode(params)}"
    self.page.goto(url, wait_until="domcontentloaded")

    links = self.page.locator('a[href*="/-/issues/"]')
    count = links.count()
    issues = []
    seen = set()

    for i in range(count):
        link = links.nth(i)
        title_text = (link.inner_text() or "").strip()
        href = link.get_attribute("href")
        if not href:
            continue
        issue_url = href if href.startswith("http://") or href.startswith("https://") else f"{self.base_url}{href if href.startswith('/') else '/' + href}"
        if issue_url in seen:
            continue
        seen.add(issue_url)

        iid_match = re.search(r'/-/issues/(\d+)', href)
        issue_iid = iid_match.group(1) if iid_match else None

        issues.append({
            "title_text": title_text,
            "issue_url": issue_url,
            "issue_iid": issue_iid,
            "order_index": len(issues),
        })

    return {
        "issues": issues,
        "sort": sort,
        "page_number": page_number,
        "applied_filters": {
            "assignee_username": assignee_username,
            "state": state,
            "search_query": search_query,
        },
        "is_complete_page": False,
    }
