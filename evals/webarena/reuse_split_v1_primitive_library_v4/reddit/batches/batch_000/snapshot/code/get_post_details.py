def get_post_details(self, post_url: str) -> dict:
    """Fetch a post page and return stable post metadata and comment summary fields."""
    import html as html_lib
    import re
    from urllib.parse import urlparse

    self.page.goto(post_url)
    page_html = self.page.content()
    current_url = self.page.url

    path_match = re.search(r'/f/[^/]+/(\d+)/', urlparse(current_url).path)
    title_match = re.search(r'<h1 class="submission__title[^>]*>.*?<a [^>]*>(.*?)</a>', page_html, re.I | re.S)
    if title_match:
        post_title = re.sub(r'<[^>]+>', ' ', title_match.group(1))
        post_title = ' '.join(html_lib.unescape(post_title).split())
    else:
        meta_title_match = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', page_html, re.I)
        if meta_title_match:
            post_title = html_lib.unescape(meta_title_match.group(1)).strip()
        else:
            title_tag_match = re.search(r'<title>\s*(.*?)\s*</title>', page_html, re.I | re.S)
            post_title = html_lib.unescape(title_tag_match.group(1)).strip() if title_tag_match else ''

    author_match = re.search(r'og:article:author" content="([^"]+)"', page_html)
    if not author_match:
        author_match = re.search(r'Submitted by\s*<a href="/user/([^"]+)"', page_html, re.I | re.S)
    author_username = html_lib.unescape(author_match.group(1)).strip() if author_match else ''

    comment_count_match = re.search(r'data-comment-count="(\d+)"', page_html)
    comment_count = int(comment_count_match.group(1)) if comment_count_match else None
    comments_empty = (
        bool(re.search(r'<strong>No comments</strong>', page_html, re.I))
        or "There's nothing here" in page_html
        or "There&#039;s nothing here" in page_html
        or comment_count == 0
    )

    return {
        "post_id": path_match.group(1) if path_match else None,
        "post_url": current_url,
        "post_title": post_title,
        "author_username": author_username,
        "comment_count": comment_count,
        "comments_empty": comments_empty,
    }
