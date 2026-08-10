def list_dashboard_projects(self, base_url: str, scope: str | None = None) -> dict:
    import re

    url = base_url.rstrip("/") + "/dashboard/projects"
    self.page.goto(url, wait_until="domcontentloaded")

    applied_scope = None
    if scope == "personal":
        self.page.get_by_role("link", name="Personal").click()
        self.page.wait_for_load_state("domcontentloaded")
        applied_scope = "personal"

    items = self.page.locator("main .projects-list > li")
    count = items.count()
    records = []

    for i in range(count):
        li = items.nth(i)
        text = (li.inner_text() or "").strip()
        links = li.locator("a").evaluate_all("els => els.map(a => ({text:(a.innerText||'').trim(), href:a.getAttribute('href')}))")
        title_link = None
        for link in links:
            link_text = (link.get("text") or "").strip()
            href = link.get("href")
            if link_text and "/" in link_text and href and "/-/" not in href:
                title_link = link
                break

        counts_match = re.search(r"\n\s*(\d+)\s*\n\s*(\d+)\s*\n\s*(\d+)\s*\n\s*(\d+)\s*\n\s*Updated", "\n" + text + "\n")
        if not title_link or not counts_match:
            continue

        stars_count, forks_count, merge_requests_count, issues_count = map(int, counts_match.groups())
        project_url = title_link.get("href")
        if project_url and project_url.startswith("/"):
            absolute_url = base_url.rstrip("/") + project_url
        else:
            absolute_url = project_url

        records.append({
            "project_path": title_link.get("text"),
            "project_url": absolute_url,
            "relative_project_url": project_url,
            "stars_count": stars_count,
            "forks_count": forks_count,
            "merge_requests_count": merge_requests_count,
            "issues_count": issues_count,
        })

    return {
        "records": records,
        "completeness": {
            "scope_applied": applied_scope,
            "pagination_complete": False,
        },
        "source_url": self.page.url,
    }
