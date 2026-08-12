def list_post_comments_with_net_scores(self, post_url: str) -> dict:
    """Fetch a post page and return visible comments with displayed net scores."""
    import html as html_lib
    import re

    self.page.goto(post_url)
    page_html = self.page.content()
    current_url = self.page.url

    starts = [m.start() for m in re.finditer(r'<article class="comment', page_html)]
    comments = []

    def _strip_tags(value: str) -> str:
        text = re.sub(r'<[^>]+>', ' ', value)
        return ' '.join(html_lib.unescape(text).split())

    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else page_html.find('</section>', start)
        if end == -1:
            end = len(page_html)
        segment = page_html[start:end]

        author_match = re.search(r'<a href="/user/[^"]+" class="fg-inherit"><strong>(.*?)</strong></a>', segment)
        score_match = re.search(r'<span class="vote__net-score"[^>]*>([−\-]?\d+)</span>', segment)
        time_match = re.search(r'<time class="[^"]*"[\s\S]*?title="([^"]+)"', segment)
        is_op_marked = ('comment__author--op' in segment) or (re.search(r'>\s*OP\s*<', segment) is not None)

        comments.append({
            "comment_position": len(comments) + 1,
            "author_username": html_lib.unescape(author_match.group(1)).strip() if author_match else None,
            "net_score": int(score_match.group(1).replace('−', '-')) if score_match else None,
            "displayed_timestamp": time_match.group(1) if time_match else None,
            "is_op_marked": is_op_marked,
            "comment_text_excerpt": _strip_tags(segment)[:300],
        })

    return {
        "post_url": current_url,
        "comments": comments,
        "completeness": "page_visible_comments",
    }
