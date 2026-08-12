def list_forum_posts(self, forum_name: str, listing_mode: str) -> dict:
    """Fetch a forum listing page and return visible posts in displayed order."""
    import html as html_lib
    import re
    from urllib.parse import urljoin

    page_path = f"/f/{forum_name}/{listing_mode}"
    self.page.goto(page_path)
    page_html = self.page.content()
    current_url = self.page.url

    article_pattern = re.compile(
        r'<article class="\s*submission[\s\S]*?</article>',
        re.I,
    )
    href_pattern = re.compile(
        rf'href="(/f/{re.escape(forum_name)}/(\d+)/[^"#]+)"',
        re.I,
    )
    title_pattern = re.compile(
        r'<h1 class="submission__title[^>]*>.*?<a [^>]*>(.*?)</a>',
        re.I | re.S,
    )
    author_pattern = re.compile(
        r'Submitted by\s*<a href="/user/[^"]+"[^>]*><strong>(.*?)</strong></a>',
        re.I | re.S,
    )
    time_pattern = re.compile(
        r'<time[^>]*?(?:title|datetime)="([^"]+)"',
        re.I | re.S,
    )

    def _clean_text(value: str) -> str:
        text = re.sub(r'<[^>]+>', ' ', value)
        return ' '.join(html_lib.unescape(text).split())

    posts = []
    seen_paths = set()

    for article_html in article_pattern.findall(page_html):
        href_match = href_pattern.search(article_html)
        if not href_match:
            continue
        post_path = href_match.group(1)
        post_id = href_match.group(2)
        if post_path in seen_paths:
            continue
        seen_paths.add(post_path)

        title_match = title_pattern.search(article_html)
        author_match = author_pattern.search(article_html)
        time_match = time_pattern.search(article_html)

        posts.append({
            "post_id": post_id,
            "post_path": post_path,
            "post_url": urljoin(current_url, post_path),
            "listing_position": len(posts) + 1,
            "post_title": _clean_text(title_match.group(1)) if title_match else None,
            "author_username": html_lib.unescape(author_match.group(1)).strip() if author_match else None,
            "listed_timestamp": time_match.group(1) if time_match else None,
        })

    if not posts:
        fallback_seen = set()
        for href_match in href_pattern.finditer(page_html):
            post_path = href_match.group(1)
            post_id = href_match.group(2)
            if post_path in fallback_seen:
                continue
            fallback_seen.add(post_path)
            posts.append({
                "post_id": post_id,
                "post_path": post_path,
                "post_url": urljoin(current_url, post_path),
                "listing_position": len(posts) + 1,
                "post_title": None,
                "author_username": None,
                "listed_timestamp": None,
            })

    return {
        "forum_name": forum_name,
        "listing_mode": listing_mode,
        "page_url": current_url,
        "posts": posts,
        "completeness": "page_visible_results",
    }
