def list_repository_commits(self, repository_url: str, ref: str, author: str | None = None) -> dict:
    import re
    from urllib.parse import quote
    import httpx

    list_url = f"{repository_url.rstrip('/')}/-/commits/{ref}"
    if author:
        list_url = f"{list_url}?author={quote(author)}"

    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        response = client.get(list_url)
        response.raise_for_status()
        html = response.text

    matches = re.findall(
        r'<a class=\"commit-author-link\"[^>]*>(.*?)</a> authored <time class=\"js-timeago\"[^>]*datetime=\"([^\"]+)\"',
        html,
        re.S,
    )

    commits = []
    for raw_author, authored_at in matches:
        author_name = re.sub(r'<.*?>', '', raw_author).strip()
        commits.append({
            "author_name": author_name,
            "authored_at": authored_at,
            "authored_date": authored_at[:10] if authored_at else "",
        })

    return {
        "list_url": list_url,
        "commits": commits,
    }
