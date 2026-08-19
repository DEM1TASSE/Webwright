def list_forum_new_posts(self, forum_name: str, max_items: int = 20):
    import re
    from urllib.parse import urljoin

    if not isinstance(forum_name, str) or not forum_name.strip():
        raise ValueError("forum_name must be a non-empty string")
    if not isinstance(max_items, int) or max_items < 1:
        raise ValueError("max_items must be a positive integer")

    forum_name = forum_name.strip()
    response = self.page.goto(f"/f/{forum_name}/new", wait_until="domcontentloaded")
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
            author_locator = card.locator("a.submission__submitter").first

            href = title_locator.get_attribute("href") if title_locator.count() else None
            title = title_locator.inner_text().strip() if title_locator.count() else None
            author_username = author_locator.inner_text().strip() if author_locator.count() else None

            if not href or not author_username:
                continue

            post_url = urljoin(self.page.url, href)
            if post_url in seen_urls:
                continue
            seen_urls.add(post_url)

            posts.append({
                "rank_on_page": len(posts) + 1,
                "post_url": post_url,
                "author_username": author_username,
                "title": title if title else None,
            })
    else:
        body_text = self.page.locator("body").inner_text()
        author_matches = re.findall(r"Submitted by ([^\s]+) ", body_text)
        hrefs = self.page.locator("a").evaluate_all("els => els.map(e => e.href)")
        matched_urls = []
        for href in hrefs:
            if href and re.search(rf"/f/{re.escape(forum_name)}/\d+/", href):
                if href not in seen_urls:
                    seen_urls.add(href)
                    matched_urls.append(href)
        for idx, post_url in enumerate(matched_urls[:max_items]):
            author_username = author_matches[idx] if idx < len(author_matches) else None
            if not author_username:
                continue
            posts.append({
                "rank_on_page": len(posts) + 1,
                "post_url": post_url,
                "author_username": author_username,
                "title": None,
            })

    return {
        "forum_name": forum_name,
        "listing_url": self.page.url,
        "ordering": "new",
        "document_status": document_status,
        "posts": posts,
    }
