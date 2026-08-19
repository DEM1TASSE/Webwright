"""Generated candidate package; not promoted."""

class GitLabAuth:

    def __init__(self, page):
        self.page = page

    def authenticate_with_sign_in_form(self, base_url: str, username: str, password: str) -> dict:
        import re
        import requests
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError('base_url must be a non-empty string')
        if not isinstance(username, str) or not username:
            raise ValueError('username must be a non-empty string')
        if not isinstance(password, str) or not password:
            raise ValueError('password must be a non-empty string')
        base_url = base_url.rstrip('/')
        session = requests.Session()
        sign_in_response = session.get(f'{base_url}/users/sign_in', timeout=30)
        sign_in_response.raise_for_status()
        match = re.search('name="authenticity_token" value="([^"]+)"', sign_in_response.text)
        if not match:
            raise RuntimeError('authenticity_token not found on sign-in page')
        response = session.post(f'{base_url}/users/sign_in', data={'authenticity_token': match.group(1), 'user[login]': username, 'user[password]': password}, headers={'Referer': f'{base_url}/users/sign_in'}, allow_redirects=True, timeout=30)
        response.raise_for_status()
        final_url = response.url
        authenticated = '/users/sign_in' not in final_url
        session_established = len(session.cookies) > 0
        return {'authenticated': bool(authenticated), 'final_url': final_url, 'session_established': bool(session_established)}

class GitLabCommits:

    def __init__(self, page):
        self.page = page

    def collect_all_repository_commits(self, project_id: int, ref_name: str, per_page: int) -> dict:
        import requests
        if not isinstance(project_id, int):
            raise ValueError('project_id must be an integer')
        if not isinstance(ref_name, str) or not ref_name.strip():
            raise ValueError('ref_name must be a non-empty string')
        if not isinstance(per_page, int) or per_page < 1:
            raise ValueError('per_page must be an integer >= 1')
        base_url = 'http://GCRSANDBOX410.redmond.corp.microsoft.com:8023'
        all_commits = []
        page_number = 1
        pages_fetched = 0
        termination_condition = None
        while True:
            response = requests.get(f'{base_url}/api/v4/projects/{project_id}/repository/commits', params={'ref_name': ref_name, 'page': page_number, 'per_page': per_page}, timeout=30)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise RuntimeError('Expected list response from GitLab commits API')
            pages_fetched += 1
            batch = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                batch.append({'id': item.get('id'), 'short_id': item.get('short_id'), 'title': item.get('title'), 'author_name': item.get('author_name'), 'author_email': item.get('author_email'), 'committer_name': item.get('committer_name'), 'committer_email': item.get('committer_email'), 'committed_date': item.get('committed_date'), 'web_url': item.get('web_url')})
            if not batch:
                termination_condition = 'empty_page'
                break
            all_commits.extend(batch)
            if len(batch) < per_page:
                termination_condition = 'short_page'
                break
            page_number += 1
        return {'commits': all_commits, 'pagination_summary': {'pages_fetched': pages_fetched, 'per_page': per_page, 'termination_condition': termination_condition}}

    def get_commit_groups_from_project_commits_page(self, project_url: str, ref_name: str) -> dict:
        import re
        if not isinstance(project_url, str) or not project_url.strip():
            raise ValueError('project_url must be a non-empty string')
        if not isinstance(ref_name, str) or not ref_name.strip():
            raise ValueError('ref_name must be a non-empty string')
        project_url = project_url.rstrip('/')
        commits_url = f'{project_url}/-/commits/{ref_name}'
        self.page.goto(commits_url, wait_until='domcontentloaded')
        body_text = self.page.locator('body').inner_text()
        lines = [line.strip() for line in body_text.splitlines() if line.strip()]
        header_pattern = re.compile('^(?P<date_label>\\d{2}\\s+[A-Za-z]{3},\\s+\\d{4})\\s+(?P<count>\\d+)\\s+commit(?:s)?$')
        commit_groups = []
        current_group = None
        for line in lines:
            match = header_pattern.match(line)
            if match:
                if current_group is not None:
                    commit_groups.append(current_group)
                current_group = {'date_label': match.group('date_label'), 'displayed_commit_count': int(match.group('count')), 'entries': []}
                continue
            if current_group is None:
                continue
            if ' authored' in line:
                author_display = line.split(' authored', 1)[0].strip() or None
                current_group['entries'].append({'author_display': author_display, 'attribution_line': line})
        if current_group is not None:
            commit_groups.append(current_group)
        return {'commit_groups': commit_groups, 'page_url': self.page.url}

    def list_branch_commit_day_summaries_from_url(self, commits_page_url: str) -> dict:
        import re
        if not isinstance(commits_page_url, str) or not commits_page_url.strip():
            raise ValueError('commits_page_url must be a non-empty string')
        response = self.page.goto(commits_page_url, wait_until='domcontentloaded')
        if response is not None and response.status >= 400:
            raise RuntimeError(f'Failed to load commits page: HTTP {response.status}')
        body_text = self.page.locator('body').inner_text()
        header_pattern = re.compile('(?m)^(\\d{2} [A-Z][a-z]{2}, \\d{4})\\s+(\\d+) commits?$')
        days = []
        for match in header_pattern.finditer(body_text):
            days.append({'day_label': match.group(1), 'displayed_commit_count': int(match.group(2))})
        return {'commits_page_url': commits_page_url, 'days': days}

    def list_repository_commits(self, project_id_or_path, ref_name=None, author=None, since=None, until=None, per_page=None, page_number=None):
        from urllib.parse import quote, urlencode
        if isinstance(project_id_or_path, bool) or project_id_or_path is None:
            raise ValueError('project_id_or_path must be a non-empty string or integer')
        if not isinstance(project_id_or_path, (str, int)):
            raise ValueError('project_id_or_path must be a non-empty string or integer')
        if isinstance(project_id_or_path, str) and (not project_id_or_path.strip()):
            raise ValueError('project_id_or_path must be a non-empty string or integer')
        if ref_name is not None and (not isinstance(ref_name, str) or not ref_name.strip()):
            raise ValueError('ref_name must be a non-empty string when provided')
        if author is not None and (not isinstance(author, str) or not author.strip()):
            raise ValueError('author must be a non-empty string when provided')
        if since is not None and (not isinstance(since, str) or not since.strip()):
            raise ValueError('since must be a non-empty ISO-8601 string when provided')
        if until is not None and (not isinstance(until, str) or not until.strip()):
            raise ValueError('until must be a non-empty ISO-8601 string when provided')
        if per_page is not None and (not isinstance(per_page, int) or per_page < 1):
            raise ValueError('per_page must be an integer >= 1 when provided')
        if page_number is not None and (not isinstance(page_number, int) or page_number < 1):
            raise ValueError('page_number must be an integer >= 1 when provided')
        base_url = self._list_repository_commits__get_base_url().rstrip('/')
        project_segment = quote(str(project_id_or_path).strip(), safe='')
        api_url = f'{base_url}/api/v4/projects/{project_segment}/repository/commits'
        params = {}
        if ref_name is not None:
            params['ref_name'] = ref_name.strip()
        if author is not None:
            params['author'] = author.strip()
        if since is not None:
            params['since'] = since.strip()
        if until is not None:
            params['until'] = until.strip()
        if per_page is not None:
            params['per_page'] = per_page
        if page_number is not None:
            params['page'] = page_number
        url = api_url if not params else f'{api_url}?{urlencode(params)}'
        response = self.page.goto(url, wait_until='domcontentloaded')
        if response is None:
            raise RuntimeError('Failed to load commits API response')
        if response.status >= 400:
            raise RuntimeError(f'Failed to load commits API response: HTTP {response.status}')
        try:
            payload = self.page.evaluate('() => JSON.parse(document.body.innerText)')
        except Exception as exc:
            raise RuntimeError('Commits API did not return parseable JSON') from exc
        if not isinstance(payload, list):
            raise RuntimeError('Expected list response from GitLab commits API')
        commits = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            commits.append({'id': item.get('id'), 'short_id': item.get('short_id'), 'title': item.get('title'), 'author_name': item.get('author_name'), 'author_email': item.get('author_email'), 'committer_name': item.get('committer_name'), 'committer_email': item.get('committer_email'), 'authored_date': item.get('authored_date'), 'committed_date': item.get('committed_date'), 'web_url': item.get('web_url')})
        return {'commits': commits, 'page_number': page_number, 'per_page': per_page, 'raw_count': len(commits), 'pagination': {'page_number': page_number, 'per_page': per_page, 'returned_count': len(commits)}}

    def _list_repository_commits__get_base_url(self):
        current = self.page.url or ''
        m = __import__('re').match('^(https?://[^/]+)', current)
        if not m:
            raise RuntimeError('Cannot determine GitLab base URL from current page')
        return m.group(1)

class GitLabContributors:

    def __init__(self, page):
        self.page = page

    def list_repository_contributors(self, project_id: int) -> dict:
        import requests
        if not isinstance(project_id, int):
            raise ValueError('project_id must be an integer')
        base_url = 'http://GCRSANDBOX410.redmond.corp.microsoft.com:8023'
        response = requests.get(f'{base_url}/api/v4/projects/{project_id}/repository/contributors', timeout=30)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise RuntimeError('Expected list response from GitLab contributors API')
        contributors = []
        for item in data:
            if not isinstance(item, dict):
                continue
            commits = item.get('commits')
            if commits is not None:
                try:
                    commits = int(commits)
                except Exception:
                    commits = None
            contributors.append({'name': item.get('name'), 'email': item.get('email'), 'commits': commits})
        return {'contributors': contributors}

    def list_repository_contributors_from_graph_page(self, graph_page_url):
        import re
        if not isinstance(graph_page_url, str) or not graph_page_url.strip():
            raise ValueError('graph_page_url must be a non-empty string')
        response = self.page.goto(graph_page_url, wait_until='networkidle')
        if response is None:
            raise RuntimeError('Failed to load graph page')
        if response.status >= 400:
            raise RuntimeError(f'Failed to load graph page: HTTP {response.status}')
        contributors = []
        cards = self.page.locator('.contributors-charts .col-lg-6.col-12.gl-my-5')
        card_count = cards.count()
        for i in range(card_count):
            card = cards.nth(i)
            name_locator = card.locator('h4').first
            name = name_locator.inner_text().strip() if name_locator.count() > 0 else ''
            if not name:
                continue
            summary_locator = card.locator('p').first
            summary = summary_locator.inner_text().strip() if summary_locator.count() > 0 else ''
            email = ''
            email_match = re.search('\\(([^\\n()]+@[^\\n()]+)\\)', summary)
            if email_match:
                email = email_match.group(1).strip()
            commit_match = re.search('(\\d+)\\s+commit', summary)
            commit_count = int(commit_match.group(1)) if commit_match else -1
            contributors.append({'name': name, 'commit_count': commit_count, 'commits': commit_count, 'email': email, 'summary': summary})
        if not contributors:
            body_text = self.page.locator('body').inner_text()
            pattern = re.compile("([A-Za-z][A-Za-z .'-]+)\\n\\n(\\d+) commits? \\(([^\\n]+)\\)")
            seen = set()
            for m in pattern.finditer(body_text):
                key = (m.group(1).strip(), int(m.group(2)), m.group(3).strip())
                if key in seen:
                    continue
                seen.add(key)
                contributors.append({'name': m.group(1).strip(), 'commit_count': int(m.group(2)), 'commits': int(m.group(2)), 'email': m.group(3).strip(), 'summary': f'{m.group(2)} commits ({m.group(3).strip()})'})
        return {'contributors': contributors}

class GitLabIssues:

    def __init__(self, page):
        self.page = page

    def get_issue_detail_state(self, issue_url):
        import html
        import re
        response = self.page.goto(issue_url, wait_until='domcontentloaded')
        if response is None:
            raise RuntimeError('Failed to load issue detail page')
        final_url = self.page.url
        html_text = self.page.content()
        title_match = re.search('<title>(.*?)</title>', html_text, re.S | re.I)
        raw_title = html.unescape(title_match.group(1)).strip() if title_match else final_url
        issue_title = raw_title.split('(#')[0].strip() if '(#' in raw_title else raw_title
        visible_text = ' '.join(html.unescape(re.sub('<[^>]+>', ' ', html_text)).split())
        lowered = f' {visible_text.lower()} '
        is_closed = ' closed ' in lowered
        return {'issue_title': issue_title, 'issue_url': final_url, 'is_closed': is_closed}

    def search_dashboard_issues(self, assignee_username, state, search_query):
        import html
        import re
        from urllib.parse import urlencode, urljoin
        if state not in {'opened', 'closed', 'all'}:
            raise ValueError('state must be one of: opened, closed, all')
        base_url = self._search_dashboard_issues__get_base_url()
        self._search_dashboard_issues__ensure_logged_in()
        query = urlencode({'assignee_username': assignee_username, 'state': state, 'search': search_query})
        url = urljoin(base_url, f'/dashboard/issues?{query}')
        response = self.page.goto(url, wait_until='domcontentloaded')
        if response is None:
            raise RuntimeError('Failed to load dashboard issues page')
        html_text = self.page.content()
        results = []
        seen_paths = set()
        for match in re.finditer('href="([^"]+/-/issues/\\d+)"', html_text):
            issue_path = html.unescape(match.group(1))
            if issue_path in seen_paths:
                continue
            seen_paths.add(issue_path)
            start = max(0, match.start() - 800)
            end = min(len(html_text), match.end() + 1800)
            snippet_html = html_text[start:end]
            updated_match = re.search('datetime="([^"]+)"', snippet_html)
            result_text = ' '.join(html.unescape(re.sub('<[^>]+>', ' ', snippet_html)).split())
            results.append({'issue_path': issue_path, 'issue_url': urljoin(base_url, issue_path), 'updated_at': updated_match.group(1) if updated_match else None, 'result_text': result_text})
        return {'results': results}

    def _search_dashboard_issues__get_base_url(self):
        current = self.page.url or ''
        m = __import__('re').match('^(https?://[^/]+)', current)
        if not m:
            raise RuntimeError('Cannot determine GitLab base URL from current page')
        return m.group(1)

    def _search_dashboard_issues__ensure_logged_in(self):
        import re
        from urllib.parse import urljoin
        base_url = self._search_dashboard_issues__get_base_url()
        current = self.page.url or ''
        if '/users/sign_in' not in current:
            resp = self.page.goto(urljoin(base_url, '/users/sign_in'), wait_until='domcontentloaded')
            if resp is None:
                raise RuntimeError('Failed to open sign-in page')
        content = self.page.content()
        if 'name="user[login]"' not in content and 'name="user[password]"' not in content:
            return
        username = getattr(self, 'username', None)
        password = getattr(self, 'password', None)
        if not username or not password:
            raise RuntimeError('GitLab credentials are required on the feature instance')
        self.page.fill('input[name="user[login]"]', username)
        self.page.fill('input[name="user[password]"]', password)
        submit = self.page.locator('button, input[type="submit"]').first
        self.page.locator('button, input[type="submit"]').first.click()
        self.page.wait_for_load_state('domcontentloaded')
        if '/users/sign_in' in (self.page.url or ''):
            raise RuntimeError('GitLab sign-in did not complete successfully')

class GitLabProfiles:

    def __init__(self, page):
        self.page = page

    def get_user_follower_count_from_profile_page(self, profile_url: str) -> dict:
        import re
        if not isinstance(profile_url, str) or not profile_url.strip():
            raise ValueError('profile_url must be a non-empty string')
        response = self.page.goto(profile_url, wait_until='networkidle')
        if response is not None and response.status >= 400:
            raise RuntimeError(f'Failed to load profile page: HTTP {response.status}')
        follower_link = self.page.locator('a[href$="/followers"]').first
        follower_text = follower_link.inner_text().strip()
        match = re.search('(\\d+)\\s+followers?', follower_text)
        if not match:
            raise RuntimeError(f'Could not parse follower count from text: {follower_text!r}')
        follower_count = int(match.group(1))
        return {'follower_count': follower_count, 'followers_link_text': follower_text}

class GitLabProjects:

    def __init__(self, page):
        self.page = page

    def search_projects(self, search_query: str) -> dict:
        import requests
        if not isinstance(search_query, str) or not search_query.strip():
            raise ValueError('search_query must be a non-empty string')
        base_url = 'http://GCRSANDBOX410.redmond.corp.microsoft.com:8023'
        response = requests.get(f'{base_url}/api/v4/projects', params={'search': search_query.strip()}, timeout=30)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            raise RuntimeError('Expected list response from GitLab projects search API')
        projects = []
        for item in data:
            if not isinstance(item, dict):
                continue
            project_id = item.get('id')
            if project_id is not None:
                try:
                    project_id = int(project_id)
                except Exception:
                    project_id = None
            projects.append({'id': project_id, 'path_with_namespace': item.get('path_with_namespace'), 'web_url': item.get('web_url')})
        return {'projects': projects}

class GitLabSite:

    def __init__(self, page):
        self.auth = GitLabAuth(page)
        self.commits = GitLabCommits(page)
        self.contributors = GitLabContributors(page)
        self.issues = GitLabIssues(page)
        self.profiles = GitLabProfiles(page)
        self.projects = GitLabProjects(page)
