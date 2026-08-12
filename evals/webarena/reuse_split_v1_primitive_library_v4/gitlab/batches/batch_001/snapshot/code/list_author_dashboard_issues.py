def list_author_dashboard_issues(self, author_username: str, search_query: str = None, sort: str = "created_date_desc", state: str = "all", page_number: int = 1) -> dict:
    import re
    from urllib.parse import urlencode

    params = {
        "author_username": author_username,
        "sort": sort,
        "state": state,
        "page": page_number,
    }
    if search_query is not None:
        params["search"] = search_query

    url = f"{self.base_url}/dashboard/issues?{urlencode(params)}"
    self.page.goto(url, wait_until="domcontentloaded")
    self.page.wait_for_load_state("networkidle")

    issue_links = self.page.locator('a[href*="/-/issues/"]')
    count = issue_links.count()
    issues = []
    seen = set()

    for i in range(count):
        link = issue_links.nth(i)
        href = link.get_attribute("href")
        title = (link.inner_text() or "").strip()
        if not href:
            continue

        issue_url = href if href.startswith("http://") or href.startswith("https://") else f"{self.base_url}{href if href.startswith('/') else '/' + href}"
        if issue_url in seen:
            continue
        seen.add(issue_url)

        match = re.search(r'/([^/]+/[^/]+)/-/issues/(\d+)', href)
        project_path_with_namespace = match.group(1) if match else None
        issue_iid = int(match.group(2)) if match else None

        issues.append({
            "title": title or None,
            "web_url": issue_url,
            "project_path_with_namespace": project_path_with_namespace,
            "issue_iid": issue_iid,
            "order_index": len(issues),
        })

    return {
        "author_username": author_username,
        "search_query": search_query,
        "sort": sort,
        "state": state,
        "page_number": page_number,
        "issues": issues,
        "is_complete_page": False,
    }
