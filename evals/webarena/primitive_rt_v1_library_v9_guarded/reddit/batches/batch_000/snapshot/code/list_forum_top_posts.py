def list_forum_top_posts(self, forum_name: str, time_filter: str = "all", max_items: int = 10):
    import re
    from urllib.parse import urljoin

    if not isinstance(forum_name, str) or not forum_name.strip():
        raise ValueError("forum_name must be a non-empty string")
    if time_filter not in {"all"}:
        raise ValueError("time_filter must be one of: all")
    if not isinstance(max_items, int) or max_items < 1:
        raise ValueError("max_items must be a positive integer")

    forum_name = forum_name.strip()
    response = self.page.goto(f"/f/{forum_name}/top?t={time_filter}", wait_until="domcontentloaded")
    document_status = response.status if response else None

    posts = []
    seen_urls = set()

    submission_cards = self.page.locator("article.submission")
    card_count = submission_cards.count()
    if card_count > 0:
        limit = min(card_count, max_items)
        for i in range(limit):
            card = submission_cards.nth(i)
            title_locator = card.locator("a.submission__link").first
            href = title_locator.get_attribute("href") if title_locator.count() else None
            title = title_locator.inner_text().strip() if title_locator.count() else ""
            if not href or not title:
                continue
            post_url = urljoin(self.page.url, href)
            if post_url in seen_urls:
                continue
            seen_urls.add(post_url)
            posts.append({
                "rank_on_page": len(posts) + 1,
                "title": title,
                "post_url": post_url,
            })
    else:
        body_text = self.page.locator("body").inner_text()
        lines = [ln.strip() for ln in body_text.splitlines()]
        href_pairs = self.page.locator("a").evaluate_all("els => els.map(e => ({href: e.href, text: (e.innerText || '').trim()}))")
        title_to_url = {}
        for item in href_pairs:
            href = item.get("href")
            text = item.get("text")
            if href and text and re.search(rf"/f/{re.escape(forum_name)}/\d+/", href) and text not in title_to_url:
                title_to_url[text] = href

        skip = {
            "Jump to main content", "Jump to sidebar", "Postmill", "Forums", "Wiki", "Log in", "Sign up",
            f"/f/{forum_name}", "Submissions", "Comments", "Top", "All time", "More", forum_name,
            "Subscribe via RSS", "Toolbox", "Bans", "Moderation log", "Running Postmill"
        }

        for i, line in enumerate(lines):
            if len(posts) >= max_items:
                break
            if not line or line in skip:
                continue
            if i + 4 < len(lines) and lines[i + 2].startswith("Submitted by ") and re.fullmatch(r"\d+ comments", lines[i + 4]):
                title = line
                post_url = title_to_url.get(title)
                if not post_url or post_url in seen_urls:
                    continue
                seen_urls.add(post_url)
                posts.append({
                    "rank_on_page": len(posts) + 1,
                    "title": title,
                    "post_url": post_url,
                })

    return {
        "forum_name": forum_name,
        "time_filter": time_filter,
        "listing_url": self.page.url,
        "document_status": document_status,
        "posts": posts,
    }
