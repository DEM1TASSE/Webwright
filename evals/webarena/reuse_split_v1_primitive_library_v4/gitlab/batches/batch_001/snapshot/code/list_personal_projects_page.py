def list_personal_projects_page(self, sort_by: str = "most_stars", page_number: int = 1) -> dict:
    import re
    from urllib.parse import urlencode

    sort_map = {
        "most_stars": "stars_desc",
    }

    params = {
        "personal": "true",
        "page": page_number,
    }
    if sort_by in sort_map:
        params["sort"] = sort_map[sort_by]

    url = f"{self.base_url}/dashboard/projects?{urlencode(params)}"
    self.page.goto(url, wait_until="domcontentloaded")

    items = self.page.locator('main ul > li')
    count = items.count()
    projects = []

    for i in range(count):
        item = items.nth(i)
        name_link = item.locator('h2 a').first
        if name_link.count() == 0:
            continue

        href = name_link.get_attribute("href")
        name = (name_link.inner_text() or "").strip()
        if not href or not name:
            continue

        full_url = href if href.startswith("http://") or href.startswith("https://") else f"{self.base_url}{href if href.startswith('/') else '/' + href}"
        path_with_namespace = href.split("?", 1)[0].split("#", 1)[0].strip("/")
        role_text = item.inner_text() or ""
        viewer_role_is_owner = bool(re.search(r'\bOwner\b', role_text))

        star_count = None
        star_link = item.locator('a[href$="/-/starrers"]').first
        if star_link.count() > 0:
            star_text = (star_link.inner_text() or "").strip()
            star_match = re.search(r'\d+', star_text)
            if star_match:
                star_count = int(star_match.group(0))

        projects.append({
            "name": name,
            "web_url": full_url,
            "path_with_namespace": path_with_namespace,
            "star_count": star_count,
            "viewer_role_is_owner": viewer_role_is_owner,
        })

    return {
        "page_number": page_number,
        "applied_scope": "personal",
        "sort_by": sort_by,
        "projects": projects,
        "completeness": "visible_page_only",
    }
