def search_dashboard_issues(self, assignee_username, state, search_query):
    import html
    import re
    from urllib.parse import urlencode, urljoin

    if state not in {"opened", "closed", "all"}:
        raise ValueError("state must be one of: opened, closed, all")

    base_url = self._get_base_url()
    self._ensure_logged_in()

    query = urlencode({
        "assignee_username": assignee_username,
        "state": state,
        "search": search_query,
    })
    url = urljoin(base_url, f"/dashboard/issues?{query}")
    response = self.page.goto(url, wait_until="domcontentloaded")
    if response is None:
        raise RuntimeError("Failed to load dashboard issues page")
    html_text = self.page.content()

    results = []
    seen_paths = set()
    for match in re.finditer(r'href="([^"]+/-/issues/\d+)"', html_text):
        issue_path = html.unescape(match.group(1))
        if issue_path in seen_paths:
            continue
        seen_paths.add(issue_path)

        start = max(0, match.start() - 800)
        end = min(len(html_text), match.end() + 1800)
        snippet_html = html_text[start:end]
        updated_match = re.search(r'datetime="([^"]+)"', snippet_html)
        result_text = " ".join(
            html.unescape(re.sub(r"<[^>]+>", " ", snippet_html)).split()
        )
        results.append({
            "issue_path": issue_path,
            "issue_url": urljoin(base_url, issue_path),
            "updated_at": updated_match.group(1) if updated_match else None,
            "result_text": result_text,
        })

    return {"results": results}

def _get_base_url(self):
    current = self.page.url or ""
    m = __import__("re").match(r"^(https?://[^/]+)", current)
    if not m:
        raise RuntimeError("Cannot determine GitLab base URL from current page")
    return m.group(1)

def _ensure_logged_in(self):
    import re
    from urllib.parse import urljoin

    base_url = self._get_base_url()
    current = self.page.url or ""
    if "/users/sign_in" not in current:
        resp = self.page.goto(urljoin(base_url, "/users/sign_in"), wait_until="domcontentloaded")
        if resp is None:
            raise RuntimeError("Failed to open sign-in page")

    content = self.page.content()
    if 'name="user[login]"' not in content and 'name="user[password]"' not in content:
        return

    username = getattr(self, "username", None)
    password = getattr(self, "password", None)
    if not username or not password:
        raise RuntimeError("GitLab credentials are required on the feature instance")

    self.page.fill('input[name="user[login]"]', username)
    self.page.fill('input[name="user[password]"]', password)
    submit = self.page.locator('button, input[type="submit"]').first
    self.page.locator('button, input[type="submit"]').first.click()
    self.page.wait_for_load_state("domcontentloaded")
    if "/users/sign_in" in (self.page.url or ""):
        raise RuntimeError("GitLab sign-in did not complete successfully")