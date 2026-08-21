"""Generated candidate package; not promoted."""

class GitLabCommits:

    def __init__(self, page):
        self.page = page

    async def list_repository_commits(self, base_url: str, ref_name: str, project_path: str | None=None, project_id: int | None=None, author: str | None=None, since: str | None=None, until: str | None=None, page_number: int=1, per_page: int=100, traversal_mode: str='single_page') -> dict:
        import json
        from urllib.parse import urlsplit, urljoin, quote
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError('base_url must be a non-empty string')
        parts = urlsplit(base_url)
        if not parts.scheme or not parts.netloc:
            raise ValueError('base_url must include scheme and host')
        origin = f'{parts.scheme}://{parts.netloc}'
        if not isinstance(ref_name, str) or not ref_name.strip():
            raise ValueError('ref_name must be a non-empty string')
        if project_id is None and project_path is None:
            raise ValueError('Either project_id or project_path must be provided')
        if project_id is not None and (not isinstance(project_id, int)):
            raise ValueError('project_id must be an integer when provided')
        if project_path is not None:
            if not isinstance(project_path, str) or not project_path.strip() or '/' not in project_path:
                raise ValueError("project_path must be a GitLab project path like 'group/project'")
        if not isinstance(page_number, int) or page_number < 1:
            raise ValueError('page_number must be an integer >= 1')
        if not isinstance(per_page, int) or per_page < 1:
            raise ValueError('per_page must be an integer >= 1')
        if traversal_mode not in {'single_page', 'all_pages'}:
            raise ValueError('traversal_mode must be one of: single_page, all_pages')
        project_token = str(project_id) if project_id is not None else quote(project_path, safe='')
        commits = []
        current_page = page_number
        while True:
            api_url = urljoin(origin + '/', f'api/v4/projects/{project_token}/repository/commits')
            params = {'ref_name': ref_name, 'page': current_page, 'per_page': per_page}
            if author is not None:
                params['author'] = author
            if since is not None:
                params['since'] = since
            if until is not None:
                params['until'] = until
            response = await self.page.request.get(api_url, params=params)
            if response.status >= 400:
                raise RuntimeError(f'GitLab commits API request failed with status {response.status} on page {current_page}')
            try:
                batch = await response.json()
            except Exception:
                batch = json.loads(await response.text())
            if not isinstance(batch, list):
                raise RuntimeError('Expected GitLab repository commits response to be a JSON array')
            if not batch:
                break
            for item in batch:
                if not isinstance(item, dict):
                    continue
                commit_id = item.get('id') or ''
                short_id = item.get('short_id') or ''
                if not commit_id and (not short_id):
                    raise RuntimeError('GitLab commits API item missing both id and short_id')
                commits.append({'id': commit_id, 'short_id': short_id, 'title': item.get('title') or '', 'author_name': item.get('author_name') or '', 'author_email': item.get('author_email') or '', 'committer_name': item.get('committer_name') or '', 'committer_email': item.get('committer_email') or '', 'authored_date': item.get('authored_date') or '', 'committed_at': item.get('committed_date') or '', 'web_url': item.get('web_url') or ''})
            if traversal_mode == 'single_page':
                break
            if len(batch) < per_page:
                break
            current_page += 1
        return {'commits': commits}

    async def list_visible_commit_day_buckets(self, project_path: str, branch: str) -> dict:
        import re
        from urllib.parse import urlsplit, urljoin
        if not isinstance(project_path, str) or not project_path.strip():
            raise ValueError('project_path must be a non-empty string')
        if not isinstance(branch, str) or not branch.strip():
            raise ValueError('branch must be a non-empty string')
        current_url = self.page.url
        if not current_url:
            raise RuntimeError('self.page.url is empty; navigate to the GitLab deployment before calling list_visible_commit_day_buckets')
        parts = urlsplit(current_url)
        origin = f'{parts.scheme}://{parts.netloc}'
        commits_url = urljoin(origin + '/', f'{project_path.strip('/')}/-/commits/{branch}')
        response = await self.page.goto(commits_url, wait_until='domcontentloaded')
        if response and response.status >= 400:
            raise RuntimeError(f'GitLab commits page navigation failed with status {response.status}')
        buckets = []
        items = self.page.locator('li.commits-list-item')
        count = await items.count()
        for i in range(count):
            item = items.nth(i)
            text = await item.inner_text()
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if not lines:
                continue
            header_line = None
            for line in lines:
                if re.search('\\b\\d+\\s+commit[s]?\\b', line):
                    header_line = line
                    break
            if not header_line:
                continue
            match = re.match('^(?P<day_label>.+?)\\s+(?P<commit_count>\\d+)\\s+commit[s]?$', header_line)
            if not match:
                continue
            day_label = match.group('day_label').strip()
            commit_count = int(match.group('commit_count'))
            commit_count_text = f'{commit_count} commit' if commit_count == 1 else f'{commit_count} commits'
            authors = []
            for line in lines:
                authored_match = re.match('^(?P<author>.+?)\\s+authored\\b', line)
                if authored_match:
                    authors.append(authored_match.group('author').strip())
            buckets.append({'day_label': day_label, 'commit_count': commit_count, 'commit_count_text': commit_count_text, 'authors': authors})
        return {'commit_day_buckets': buckets, 'final_url': self.page.url}

class GitLabContributors:

    def __init__(self, page):
        self.page = page

    async def list_repository_contributors(self, project_id: int) -> dict:
        import json
        from urllib.parse import urlsplit, urljoin
        if not isinstance(project_id, int):
            raise ValueError('project_id must be an integer')
        current_url = self.page.url
        if not current_url:
            raise RuntimeError('self.page.url is empty; navigate to the GitLab deployment before calling list_repository_contributors')
        parts = urlsplit(current_url)
        origin = f'{parts.scheme}://{parts.netloc}'
        api_url = urljoin(origin + '/', f'api/v4/projects/{project_id}/repository/contributors')
        response = await self.page.request.get(api_url)
        if response.status >= 400:
            raise RuntimeError(f'GitLab repository contributors request failed with status {response.status}')
        try:
            payload = await response.json()
        except Exception:
            payload = json.loads(await response.text())
        if not isinstance(payload, list):
            raise RuntimeError('Expected GitLab repository contributors response to be a JSON array')
        contributors = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            commits_value = item.get('commits')
            commits = int(commits_value) if commits_value is not None else 0
            contributors.append({'name': item.get('name'), 'email': item.get('email'), 'commits': commits})
        return {'contributors': contributors}

    async def list_repository_contributors_from_graph_page(self, base_url: str | None=None, namespace: str | None=None, project: str | None=None, branch: str | None=None, graph_page_url: str | None=None, username: str | None=None, password: str | None=None) -> dict:
        import re
        from urllib.parse import urlsplit, urljoin

        def _origin_from_url(value: str) -> str:
            parts = urlsplit(value)
            if not parts.scheme or not parts.netloc:
                raise ValueError('URL must include scheme and host')
            return f'{parts.scheme}://{parts.netloc}'
        if graph_page_url is not None:
            if not isinstance(graph_page_url, str) or not graph_page_url.strip():
                raise ValueError('graph_page_url must be a non-empty string when provided')
            target_url = graph_page_url.strip()
            origin = _origin_from_url(target_url)
        else:
            if not isinstance(base_url, str) or not base_url.strip():
                raise ValueError('base_url must be a non-empty string when graph_page_url is not provided')
            if not isinstance(namespace, str) or not namespace.strip():
                raise ValueError('namespace must be a non-empty string when graph_page_url is not provided')
            if not isinstance(project, str) or not project.strip():
                raise ValueError('project must be a non-empty string when graph_page_url is not provided')
            if not isinstance(branch, str) or not branch.strip():
                raise ValueError('branch must be a non-empty string when graph_page_url is not provided')
            origin = _origin_from_url(base_url)
            target_url = urljoin(origin + '/', f'{namespace.strip('/')}/{project.strip('/')}/-/graphs/{branch}')
        if username is not None or password is not None:
            if not username or not password:
                raise ValueError('username and password must both be provided when authentication is requested')
            sign_in_url = urljoin(origin + '/', 'users/sign_in')
            response = await self.page.goto(sign_in_url, wait_until='domcontentloaded')
            if response is None:
                raise RuntimeError('Failed to load GitLab sign-in page')
            await self.page.fill('input[name="user[login]"]', username)
            await self.page.fill('input[name="user[password]"]', password)
            await self.page.locator('input[type="submit"], button[type="submit"]').first.click()
            await self.page.wait_for_load_state('domcontentloaded')
        response = await self.page.goto(target_url, wait_until='networkidle')
        document_status = response.status if response is not None else None
        final_url = self.page.url
        final_path = urlsplit(final_url).path
        if '/-/graphs/' not in final_path and (not final_path.endswith('/-/graphs')):
            raise RuntimeError(f'Loaded page does not appear to be a GitLab graphs page: {final_url}')
        inferred_branch = branch or final_path.rsplit('/-/graphs/', 1)[-1] if '/-/graphs/' in final_path else branch or ''
        repo_path = final_path.split('/-/graphs/', 1)[0].strip('/') if '/-/graphs/' in final_path else ''
        repository_url = urljoin(origin + '/', repo_path) if repo_path else ''
        contributors = []
        cards = self.page.locator('.contributors-charts .col-lg-6.col-12.gl-my-5')
        card_count = await cards.count()
        if card_count > 0:
            for i in range(card_count):
                card = cards.nth(i)
                name_locator = card.locator('h4').first
                if await name_locator.count() == 0:
                    continue
                contributor_name = (await name_locator.inner_text()).strip()
                if not contributor_name:
                    continue
                summary_locator = card.locator('p').first
                summary_text = ''
                if await summary_locator.count() > 0:
                    summary_text = (await summary_locator.inner_text()).strip()
                commit_match = re.search('(\\d+)\\s+commit', summary_text, re.IGNORECASE)
                email_match = re.search('\\(([^\\n()]+@[^\\n()]+)\\)', summary_text)
                commit_count = int(commit_match.group(1)) if commit_match else None
                contributor_email = email_match.group(1).strip() if email_match else None
                commit_count_text = None
                if commit_match:
                    n = int(commit_match.group(1))
                    commit_count_text = f'{n} commit' if n == 1 else f'{n} commits'
                contributors.append({'name': contributor_name, 'contributor_name': contributor_name, 'summary_text': summary_text, 'commit_count': commit_count, 'contributor_email': contributor_email, 'contributor_email_displayed': contributor_email, 'commit_count_text': commit_count_text})
        else:
            body_text = await self.page.locator('body').inner_text()
            regex = re.compile("([A-Za-z][A-Za-z .'-]+)\\n\\n(\\d+) commits? \\(([^\\n]+)\\)")
            for match in regex.finditer(body_text):
                contributor_name = match.group(1).strip()
                n = int(match.group(2))
                contributor_email = match.group(3).strip()
                contributors.append({'name': contributor_name, 'contributor_name': contributor_name, 'summary_text': f'{match.group(2)} commits ({contributor_email})', 'commit_count': n, 'contributor_email': contributor_email, 'contributor_email_displayed': contributor_email, 'commit_count_text': f'{n} commit' if n == 1 else f'{n} commits'})
            if not contributors:
                lines = [line.strip() for line in body_text.splitlines() if line.strip()]
                for idx in range(len(lines) - 1):
                    if re.fullmatch("[A-Za-z][A-Za-z .'-]+", lines[idx]) and re.fullmatch('\\d+ commits?', lines[idx + 1]):
                        contributor_name = lines[idx]
                        n = int(re.search('\\d+', lines[idx + 1]).group(0))
                        contributors.append({'name': contributor_name, 'contributor_name': contributor_name, 'summary_text': lines[idx + 1], 'commit_count': n, 'contributor_email': None, 'contributor_email_displayed': None, 'commit_count_text': lines[idx + 1]})
        return {'repository_url': repository_url, 'graph_page_url': final_url, 'graphs_url': final_url, 'document_status': document_status, 'branch': inferred_branch, 'contributors': contributors}

class GitLabIssues:

    def __init__(self, page):
        self.page = page

    async def get_issue_detail(self, base_url: str, username: str, password: str, issue_url: str) -> dict:
        import re
        import html as html_lib
        from urllib.parse import urlsplit, urljoin
        base_parts = urlsplit(base_url)
        if not base_parts.scheme or not base_parts.netloc:
            raise ValueError('base_url must include scheme and host')
        origin = f'{base_parts.scheme}://{base_parts.netloc}'
        sign_in_url = urljoin(origin + '/', 'users/sign_in')
        response = await self.page.goto(sign_in_url, wait_until='domcontentloaded')
        if response is None:
            raise RuntimeError('Failed to load GitLab sign-in page')
        sign_in_html = await self.page.content()
        token_match = re.search('name="authenticity_token" value="([^"]+)"', sign_in_html)
        if not token_match:
            raise RuntimeError('GitLab authenticity_token not found on sign-in page')
        login_response = await self.page.request.post(sign_in_url, form={'authenticity_token': token_match.group(1), 'user[login]': username, 'user[password]': password, 'user[remember_me]': '0'}, headers={'Referer': sign_in_url})
        if not login_response.ok:
            raise RuntimeError(f'GitLab login failed with status {login_response.status}')
        resolved_issue_url = issue_url if urlsplit(issue_url).scheme else urljoin(origin + '/', issue_url.lstrip('/'))
        issue_response = await self.page.goto(resolved_issue_url, wait_until='domcontentloaded')
        if issue_response is None:
            raise RuntimeError('Failed to load GitLab issue detail page')
        issue_html = await self.page.content()
        page_title_match = re.search('<title>(.*?)</title>', issue_html, re.S)
        page_title = html_lib.unescape(page_title_match.group(1)).strip() if page_title_match else ''
        page_text = ' '.join(html_lib.unescape(re.sub('<[^>]+>', ' ', issue_html)).split())
        is_closed = ' closed ' in f' {page_text.lower()} '
        issue_title = page_title.split('(#')[0].strip() if page_title else ''
        return {'issue_url': self.page.url, 'issue_title': issue_title, 'page_title': page_title, 'is_closed': is_closed}

    async def list_dashboard_issues(self, base_url: str, username: str, password: str, assignee_username: str, state: str, search: str) -> dict:
        import re
        import html as html_lib
        from urllib.parse import urlsplit, urljoin, urlencode
        if state not in {'opened', 'closed', 'all'}:
            raise ValueError('state must be one of: opened, closed, all')
        base_parts = urlsplit(base_url)
        if not base_parts.scheme or not base_parts.netloc:
            raise ValueError('base_url must include scheme and host')
        origin = f'{base_parts.scheme}://{base_parts.netloc}'
        sign_in_url = urljoin(origin + '/', 'users/sign_in')
        response = await self.page.goto(sign_in_url, wait_until='domcontentloaded')
        if response is None:
            raise RuntimeError('Failed to load GitLab sign-in page')
        sign_in_html = await self.page.content()
        token_match = re.search('name="authenticity_token" value="([^"]+)"', sign_in_html)
        if not token_match:
            raise RuntimeError('GitLab authenticity_token not found on sign-in page')
        login_response = await self.page.request.post(sign_in_url, form={'authenticity_token': token_match.group(1), 'user[login]': username, 'user[password]': password, 'user[remember_me]': '0'}, headers={'Referer': sign_in_url})
        if not login_response.ok:
            raise RuntimeError(f'GitLab login failed with status {login_response.status}')
        query = urlencode({'assignee_username': assignee_username, 'state': state, 'search': search})
        issues_url = urljoin(origin + '/', f'dashboard/issues?{query}')
        issues_response = await self.page.goto(issues_url, wait_until='domcontentloaded')
        if issues_response is None:
            raise RuntimeError('Failed to load dashboard issues page')
        body = await self.page.content()
        issues = []
        for match in re.finditer('href="([^"]+/-/issues/\\d+)"', body):
            issue_path = html_lib.unescape(match.group(1))
            snippet_start = max(0, match.start() - 800)
            snippet_end = min(len(body), match.end() + 1800)
            snippet = body[snippet_start:snippet_end]
            dt_match = re.search('datetime="([^"]+)"', snippet)
            issues.append({'issue_path': issue_path, 'issue_url': urljoin(origin + '/', issue_path.lstrip('/')), 'updated_at_iso': dt_match.group(1) if dt_match else ''})
        return {'issues': issues}

class GitLabProfiles:

    def __init__(self, page):
        self.page = page

    async def get_user_follower_count_from_profile(self, profile_url: str) -> dict:
        import re
        if not isinstance(profile_url, str) or not profile_url.strip():
            raise ValueError('profile_url must be a non-empty string')
        response = await self.page.goto(profile_url, wait_until='networkidle')
        document_status = response.status if response is not None else None
        follower_link = self.page.locator('a[href$="/followers"]').first
        if await follower_link.count() == 0:
            raise RuntimeError(f'Followers link not found on profile page: {self.page.url}')
        follower_text = (await follower_link.inner_text()).strip()
        match = re.search('(\\d+)\\s+followers?', follower_text, re.IGNORECASE)
        if not match:
            raise RuntimeError(f'Could not parse follower count from text: {follower_text!r}')
        follower_count = int(match.group(1))
        return {'profile_url': self.page.url, 'document_status': document_status, 'follower_count': follower_count, 'follower_text': follower_text}

class GitLabProjects:

    def __init__(self, page):
        self.page = page

    async def search_projects(self, search_query: str) -> dict:
        import json
        from urllib.parse import urlsplit, urljoin, urlencode
        if not isinstance(search_query, str) or not search_query.strip():
            raise ValueError('search_query must be a non-empty string')
        current_url = self.page.url
        if not current_url:
            raise RuntimeError('self.page.url is empty; navigate to the GitLab deployment before calling search_projects')
        parts = urlsplit(current_url)
        origin = f'{parts.scheme}://{parts.netloc}'
        api_url = urljoin(origin + '/', 'api/v4/projects') + '?' + urlencode({'search': search_query})
        response = await self.page.request.get(api_url)
        if response.status >= 400:
            raise RuntimeError(f'GitLab project search failed with status {response.status}')
        try:
            payload = await response.json()
        except Exception:
            payload = json.loads(await response.text())
        if not isinstance(payload, list):
            raise RuntimeError('Expected GitLab projects search response to be a JSON array')
        projects = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            project_id = item.get('id')
            path_with_namespace = item.get('path_with_namespace')
            web_url = item.get('web_url')
            if project_id is None or path_with_namespace is None or web_url is None:
                continue
            projects.append({'id': int(project_id), 'path_with_namespace': str(path_with_namespace), 'web_url': str(web_url)})
        return {'projects': projects}

class GitLabSite:

    def __init__(self, page):
        self.commits = GitLabCommits(page)
        self.contributors = GitLabContributors(page)
        self.issues = GitLabIssues(page)
        self.profiles = GitLabProfiles(page)
        self.projects = GitLabProjects(page)
