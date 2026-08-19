"""Generated candidate package; not promoted."""

class RedditForums:

    def __init__(self, page):
        self.page = page

    def list_forum_new_posts(self, forum_name: str, max_items: int=20):
        import re
        from urllib.parse import urljoin
        if not isinstance(forum_name, str) or not forum_name.strip():
            raise ValueError('forum_name must be a non-empty string')
        if not isinstance(max_items, int) or max_items < 1:
            raise ValueError('max_items must be a positive integer')
        forum_name = forum_name.strip()
        response = self.page.goto(f'/f/{forum_name}/new', wait_until='domcontentloaded')
        document_status = response.status if response else None
        posts = []
        seen_urls = set()
        submission_cards = self.page.locator('article.submission')
        card_count = submission_cards.count()
        if card_count > 0:
            limit = min(card_count, max_items)
            for i in range(limit):
                card = submission_cards.nth(i)
                title_locator = card.locator('a.submission__link').first
                author_locator = card.locator('a.submission__submitter').first
                href = title_locator.get_attribute('href') if title_locator.count() else None
                title = title_locator.inner_text().strip() if title_locator.count() else None
                author_username = author_locator.inner_text().strip() if author_locator.count() else None
                if not href or not author_username:
                    continue
                post_url = urljoin(self.page.url, href)
                if post_url in seen_urls:
                    continue
                seen_urls.add(post_url)
                posts.append({'rank_on_page': len(posts) + 1, 'post_url': post_url, 'author_username': author_username, 'title': title if title else None})
        else:
            body_text = self.page.locator('body').inner_text()
            author_matches = re.findall('Submitted by ([^\\s]+) ', body_text)
            hrefs = self.page.locator('a').evaluate_all('els => els.map(e => e.href)')
            matched_urls = []
            for href in hrefs:
                if href and re.search(f'/f/{re.escape(forum_name)}/\\d+/', href):
                    if href not in seen_urls:
                        seen_urls.add(href)
                        matched_urls.append(href)
            for (idx, post_url) in enumerate(matched_urls[:max_items]):
                author_username = author_matches[idx] if idx < len(author_matches) else None
                if not author_username:
                    continue
                posts.append({'rank_on_page': len(posts) + 1, 'post_url': post_url, 'author_username': author_username, 'title': None})
        return {'forum_name': forum_name, 'listing_url': self.page.url, 'ordering': 'new', 'document_status': document_status, 'posts': posts}

    def list_forum_top_posts(self, forum_name: str, time_filter: str='all', max_items: int=10):
        import re
        from urllib.parse import urljoin
        if not isinstance(forum_name, str) or not forum_name.strip():
            raise ValueError('forum_name must be a non-empty string')
        if time_filter not in {'all'}:
            raise ValueError('time_filter must be one of: all')
        if not isinstance(max_items, int) or max_items < 1:
            raise ValueError('max_items must be a positive integer')
        forum_name = forum_name.strip()
        response = self.page.goto(f'/f/{forum_name}/top?t={time_filter}', wait_until='domcontentloaded')
        document_status = response.status if response else None
        posts = []
        seen_urls = set()
        submission_cards = self.page.locator('article.submission')
        card_count = submission_cards.count()
        if card_count > 0:
            limit = min(card_count, max_items)
            for i in range(limit):
                card = submission_cards.nth(i)
                title_locator = card.locator('a.submission__link').first
                href = title_locator.get_attribute('href') if title_locator.count() else None
                title = title_locator.inner_text().strip() if title_locator.count() else ''
                if not href or not title:
                    continue
                post_url = urljoin(self.page.url, href)
                if post_url in seen_urls:
                    continue
                seen_urls.add(post_url)
                posts.append({'rank_on_page': len(posts) + 1, 'title': title, 'post_url': post_url})
        else:
            body_text = self.page.locator('body').inner_text()
            lines = [ln.strip() for ln in body_text.splitlines()]
            href_pairs = self.page.locator('a').evaluate_all("els => els.map(e => ({href: e.href, text: (e.innerText || '').trim()}))")
            title_to_url = {}
            for item in href_pairs:
                href = item.get('href')
                text = item.get('text')
                if href and text and re.search(f'/f/{re.escape(forum_name)}/\\d+/', href) and (text not in title_to_url):
                    title_to_url[text] = href
            skip = {'Jump to main content', 'Jump to sidebar', 'Postmill', 'Forums', 'Wiki', 'Log in', 'Sign up', f'/f/{forum_name}', 'Submissions', 'Comments', 'Top', 'All time', 'More', forum_name, 'Subscribe via RSS', 'Toolbox', 'Bans', 'Moderation log', 'Running Postmill'}
            for (i, line) in enumerate(lines):
                if len(posts) >= max_items:
                    break
                if not line or line in skip:
                    continue
                if i + 4 < len(lines) and lines[i + 2].startswith('Submitted by ') and re.fullmatch('\\d+ comments', lines[i + 4]):
                    title = line
                    post_url = title_to_url.get(title)
                    if not post_url or post_url in seen_urls:
                        continue
                    seen_urls.add(post_url)
                    posts.append({'rank_on_page': len(posts) + 1, 'title': title, 'post_url': post_url})
        return {'forum_name': forum_name, 'time_filter': time_filter, 'listing_url': self.page.url, 'document_status': document_status, 'posts': posts}

class RedditPosts:

    def __init__(self, page):
        self.page = page

    def load_post_page(self, post_url: str):
        if not isinstance(post_url, str) or not post_url.strip():
            raise ValueError('post_url must be a non-empty string')
        post_url = post_url.strip()
        response = self.page.goto(post_url, wait_until='domcontentloaded')
        document_status = response.status if response else None
        final_url = self.page.url
        page_title = self.page.title()
        return {'requested_post_url': post_url, 'final_url': final_url, 'document_status': document_status, 'page_title': page_title}

    def open_post_from_listing_by_title(self, link_title: str):
        if not isinstance(link_title, str) or not link_title.strip():
            raise ValueError('link_title must be a non-empty string')
        link_title = link_title.strip()
        source_url = self.page.url
        target = self.page.get_by_role('link', name=link_title).first
        if target.count() == 0:
            raise ValueError('No matching post link found on the current page')
        target.click()
        self.page.wait_for_load_state('domcontentloaded')
        return {'source_listing_url': source_url, 'selected_link_title': link_title, 'post_url': self.page.url}

class RedditUsers:

    def __init__(self, page):
        self.page = page

    def get_user_comments_page_state(self, username: str):
        if not isinstance(username, str) or not username.strip():
            raise ValueError('username must be a non-empty string')
        username = username.strip()
        response = self.page.goto(f'/user/{username}/comments', wait_until='domcontentloaded')
        document_status = response.status if response else None
        body_text = self.page.locator('body').inner_text()
        empty_state_message = 'There are no entries to display.'
        is_explicitly_empty = empty_state_message in body_text
        return {'username': username, 'comments_url': self.page.url, 'document_status': document_status, 'is_explicitly_empty': is_explicitly_empty, 'empty_state_message': empty_state_message if is_explicitly_empty else None}

class RedditSite:

    def __init__(self, page):
        self.forums = RedditForums(page)
        self.posts = RedditPosts(page)
        self.users = RedditUsers(page)
