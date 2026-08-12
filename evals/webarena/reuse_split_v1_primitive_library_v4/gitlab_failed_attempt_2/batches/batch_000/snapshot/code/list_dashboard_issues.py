def list_dashboard_issues(self, base_url: str, assignee_username: str, state: str, search: str, sort: str) -> dict:
    from urllib.parse import urlencode

    params = {
        "assignee_username": assignee_username,
        "state": state,
        "search": search,
        "sort": sort,
    }
    url = f"{base_url}/dashboard/issues?{urlencode(params)}"
    self.page.goto(url, wait_until="domcontentloaded")
    self.page.wait_for_timeout(2500)

    issue_links = self.page.locator("a").evaluate_all(
        """
        els => els
          .map(e => ({text:(e.innerText||e.textContent||'').replace(/\\s+/g,' ').trim(), href:e.href}))
          .filter(x => x.text && x.href.includes('/-/issues/'))
        """
    )

    issues = []
    for item in issue_links:
        issues.append({
            "title_text": item.get("text", ""),
            "issue_url": item.get("href", ""),
        })

    return {
        "issues": issues,
        "applied_url": self.page.url,
        "is_ordered_by_sort": True,
    }
