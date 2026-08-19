def get_repository_contributors_from_graphs_page(self, namespace, repository, ref):
    import re
    from urllib.parse import quote, urljoin

    base_url = self._get_base_url()
    self._ensure_logged_in()
    path = f"/{quote(namespace, safe='')}/{quote(repository, safe='')}/-/graphs/{quote(ref, safe='')}"
    url = urljoin(base_url, path)
    response = self.page.goto(url, wait_until="networkidle")
    if response is None:
        raise RuntimeError("Failed to load repository graphs page")

    body_text = self.page.locator("body").inner_text()
    contributors = []
    pattern = re.compile(r"([A-Za-z][A-Za-z .'-]+)\n\n(\d+) commits? \(([^\n]+)\)")
    for m in pattern.finditer(body_text):
        contributors.append({
            "name": m.group(1).strip(),
            "commit_count": int(m.group(2)),
            "email": m.group(3).strip(),
        })

    if not contributors:
        lines = [line.strip() for line in body_text.splitlines() if line.strip()]
        for i in range(len(lines) - 1):
            if re.fullmatch(r"[A-Za-z][A-Za-z .'-]+", lines[i]) and re.fullmatch(r"\d+ commits?", lines[i + 1]):
                contributors.append({
                    "name": lines[i],
                    "commit_count": int(re.search(r"\d+", lines[i + 1]).group(0)),
                    "email": "",
                })

    return {"contributors": contributors}

def _get_base_url(self):
    current = self.page.url or ""
    m = __import__("re").match(r"^(https?://[^/]+)", current)
    if not m:
        raise RuntimeError("Cannot determine GitLab base URL from current page")
    return m.group(1)

def _ensure_logged_in(self):
    from urllib.parse import urljoin

    base_url = self._get_base_url()
    self.page.goto(urljoin(base_url, "/users/sign_in"), wait_until="domcontentloaded")
    content = self.page.content()
    if 'name="user[login]"' not in content and 'name="user[password]"' not in content:
        return
    username = getattr(self, "username", None)
    password = getattr(self, "password", None)
    if not username or not password:
        raise RuntimeError("GitLab credentials are required on the feature instance")
    self.page.fill('input[name="user[login]"]', username)
    self.page.fill('input[name="user[password]"]', password)
    self.page.locator('button, input[type="submit"]').first.click()
    self.page.wait_for_load_state("domcontentloaded")
    if "/users/sign_in" in (self.page.url or ""):
        raise RuntimeError("GitLab sign-in did not complete successfully")