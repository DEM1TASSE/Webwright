"""Generated candidate package; not promoted."""

class RedditForums:

    def __init__(self, page):
        self.page = page

    def list_forum_posts(self, forum_name: str, listing_mode: str) -> dict:
        """Fetch a forum listing page and return visible posts in displayed order."""
        import html as html_lib
        import re
        from urllib.parse import urljoin
        page_path = f'/f/{forum_name}/{listing_mode}'
        self.page.goto(page_path)
        page_html = self.page.content()
        current_url = self.page.url
        article_pattern = re.compile('<article class="\\s*submission[\\s\\S]*?</article>', re.I)
        href_pattern = re.compile(f'href="(/f/{re.escape(forum_name)}/(\\d+)/[^"#]+)"', re.I)
        title_pattern = re.compile('<h1 class="submission__title[^>]*>.*?<a [^>]*>(.*?)</a>', re.I | re.S)
        author_pattern = re.compile('Submitted by\\s*<a href="/user/[^"]+"[^>]*><strong>(.*?)</strong></a>', re.I | re.S)
        time_pattern = re.compile('<time[^>]*?(?:title|datetime)="([^"]+)"', re.I | re.S)

        def _clean_text(value: str) -> str:
            text = re.sub('<[^>]+>', ' ', value)
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
            posts.append({'post_id': post_id, 'post_path': post_path, 'post_url': urljoin(current_url, post_path), 'listing_position': len(posts) + 1, 'post_title': _clean_text(title_match.group(1)) if title_match else None, 'author_username': html_lib.unescape(author_match.group(1)).strip() if author_match else None, 'listed_timestamp': time_match.group(1) if time_match else None})
        if not posts:
            fallback_seen = set()
            for href_match in href_pattern.finditer(page_html):
                post_path = href_match.group(1)
                post_id = href_match.group(2)
                if post_path in fallback_seen:
                    continue
                fallback_seen.add(post_path)
                posts.append({'post_id': post_id, 'post_path': post_path, 'post_url': urljoin(current_url, post_path), 'listing_position': len(posts) + 1, 'post_title': None, 'author_username': None, 'listed_timestamp': None})
        return {'forum_name': forum_name, 'listing_mode': listing_mode, 'page_url': current_url, 'posts': posts, 'completeness': 'page_visible_results'}

class RedditPosts:

    def __init__(self, page):
        self.page = page

    def read_post_page(self, post_url: str) -> dict:
        """Fetch a post page and return stable post metadata plus visible comments."""
        import html as html_lib
        import re
        from urllib.parse import urlparse
        self.page.goto(post_url)
        page_html = self.page.content()
        current_url = self.page.url
        path_match = re.search('/f/[^/]+/(\\d+)/', urlparse(current_url).path)
        title_match = re.search('<h1 class="submission__title[^>]*>.*?<a [^>]*>(.*?)</a>', page_html, re.I | re.S)
        if title_match:
            post_title = re.sub('<[^>]+>', ' ', title_match.group(1))
            post_title = ' '.join(html_lib.unescape(post_title).split())
        else:
            meta_title_match = re.search('<meta[^>]+property="og:title"[^>]+content="([^"]*)"', page_html, re.I)
            if meta_title_match:
                post_title = html_lib.unescape(meta_title_match.group(1)).strip()
            else:
                title_tag_match = re.search('<title>\\s*(.*?)\\s*</title>', page_html, re.I | re.S)
                post_title = html_lib.unescape(title_tag_match.group(1)).strip() if title_tag_match else ''
        author_match = re.search('og:article:author" content="([^"]+)"', page_html)
        if not author_match:
            author_match = re.search('Submitted by\\s*<a href="/user/([^"]+)"', page_html, re.I | re.S)
        author_username = html_lib.unescape(author_match.group(1)).strip() if author_match else ''
        comment_count_match = re.search('data-comment-count="(\\d+)"', page_html)
        comment_count = int(comment_count_match.group(1)) if comment_count_match else None
        comments_empty = bool(re.search('<strong>No comments</strong>', page_html, re.I)) or "There's nothing here" in page_html or 'There&#039;s nothing here' in page_html or (comment_count == 0)
        starts = [m.start() for m in re.finditer('<article class="comment', page_html)]
        comments = []

        def _strip_tags(value: str) -> str:
            text = re.sub('<[^>]+>', ' ', value)
            return ' '.join(html_lib.unescape(text).split())
        for (i, start) in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else page_html.find('</section>', start)
            if end == -1:
                end = len(page_html)
            segment = page_html[start:end]
            comment_author_match = re.search('<a href="/user/[^"]+" class="fg-inherit"><strong>(.*?)</strong></a>', segment)
            score_match = re.search('<span class="vote__net-score"[^>]*>([−\\-]?\\d+)</span>', segment)
            time_match = re.search('<time class="[^"]*"[\\s\\S]*?title="([^"]+)"', segment)
            is_op_marked = 'comment__author--op' in segment or re.search('>\\s*OP\\s*<', segment) is not None
            comments.append({'comment_position': len(comments) + 1, 'author_username': html_lib.unescape(comment_author_match.group(1)).strip() if comment_author_match else None, 'net_score': int(score_match.group(1).replace('−', '-')) if score_match else None, 'displayed_timestamp': time_match.group(1) if time_match else None, 'is_op_marked': is_op_marked, 'comment_text_excerpt': _strip_tags(segment)[:300]})
        return {'post_id': path_match.group(1) if path_match else None, 'post_url': current_url, 'post_title': post_title, 'author_username': author_username, 'comment_count': comment_count, 'comments_empty': comments_empty, 'comments': comments, 'completeness': 'page_visible_comments'}

class RedditSite:

    def __init__(self, page):
        self.forums = RedditForums(page)
        self.posts = RedditPosts(page)
