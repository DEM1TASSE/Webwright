def get_project_clone_urls(self, project_path: str) -> dict:
    import re

    if not project_path.startswith("/"):
        project_path = "/" + project_path

    url = f"{self.base_url}{project_path}"
    self.page.goto(url, wait_until="domcontentloaded")
    html = self.page.content()

    ssh_clone_url = None
    http_clone_url = None

    ssh_patterns = [
        r'name=["\']ssh_project_clone["\'][^>]*value=["\']([^"\']+)["\']',
        r'Clone with SSH.*?value=["\']([^"\']+)["\']',
        r'(ssh://git@[^"\'\s<>]+?\.git)',
        r'(git@[^"\'\s<>]+?\.git)',
    ]
    for pattern in ssh_patterns:
        match = re.search(pattern, html, re.I | re.S)
        if match:
            ssh_clone_url = match.group(1)
            break

    http_patterns = [
        r'name=["\']http_project_clone["\'][^>]*value=["\']([^"\']+)["\']',
        r'Clone with HTTPS.*?value=["\']([^"\']+)["\']',
        r'(https?://[^"\'\s<>]+?\.git)',
    ]
    for pattern in http_patterns:
        match = re.search(pattern, html, re.I | re.S)
        if match:
            http_clone_url = match.group(1)
            break

    return {
        "project_path": project_path,
        "project_url": url,
        "ssh_clone_url": ssh_clone_url,
        "http_clone_url": http_clone_url,
    }
