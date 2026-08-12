def search_projects_by_name(self, base_url: str, query: str) -> dict:
    from urllib.parse import quote
    import re

    search_url = f"{base_url}/search?scope=projects&search={quote(query)}"
    self.page.goto(search_url, wait_until="domcontentloaded")
    self.page.wait_for_timeout(1500)

    links = self.page.locator("a").evaluate_all(
        """
        els => els.map(e => ({
            text: (e.innerText || e.textContent || '').replace(/\s+/g, ' ').trim(),
            href: e.getAttribute('href') || ''
        }))
        """
    )

    results = []
    seen = set()
    for item in links:
        href = item.get("href", "")
        text = item.get("text", "")
        if not href or href.startswith("http"):
            continue
        if href.startswith("/") and href.count("/") >= 2 and "/-/" not in href and not href.startswith("/search") and not href.startswith("/users"):
            project_path = href
            key = (project_path, text)
            if key in seen:
                continue
            seen.add(key)
            results.append({
                "project_path": project_path,
                "project_url": f"{base_url}{project_path}",
                "label": text,
            })

    return {
        "search_url": search_url,
        "results": results,
        "page_number": None,
        "is_complete_page": True,
    }
