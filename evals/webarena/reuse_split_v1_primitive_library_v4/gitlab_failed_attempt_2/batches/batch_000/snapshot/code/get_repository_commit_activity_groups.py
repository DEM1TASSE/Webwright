def get_repository_commit_activity_groups(self, project_path: str, ref: str, page_number: int = 1) -> dict:
    import re
    from urllib.parse import urlencode

    params = {"page": page_number} if page_number != 1 else None
    url = f"{project_path.rstrip('/')}/-/commits/{ref}"
    if params:
        url = f"{url}?{urlencode(params)}"

    self.page.goto(url, wait_until="domcontentloaded")
    self.page.wait_for_timeout(1500)
    body_text = self.page.locator("body").inner_text()

    date_matches = list(re.finditer(r'(\b\d{2}\s+[A-Z][a-z]{2},\s+\d{4}\b)\s+(\d+)\s+commit(?:s)?', body_text))
    entries = []
    for idx, match in enumerate(date_matches):
        start = match.start()
        end = date_matches[idx + 1].start() if idx + 1 < len(date_matches) else len(body_text)
        section = body_text[start:end]
        authors = []
        for author_match in re.finditer(r'\b([^\n]+?)\s+authored\b', section):
            author_name = author_match.group(1).strip()
            if author_name and author_name not in authors:
                authors.append(author_name)
        entries.append({
            "date_label": match.group(1),
            "commit_count": int(match.group(2)),
            "visible_authors": [{"author_name": name} for name in authors],
        })

    pager_text = self.page.locator("body").inner_text()
    has_next_page = bool(re.search(r'\bNext\b', pager_text))

    return {
        "project_path": project_path,
        "ref": ref,
        "page_number": page_number,
        "entries": entries,
        "is_paginated": has_next_page,
        "next_page_number": page_number + 1 if has_next_page else None,
    }
