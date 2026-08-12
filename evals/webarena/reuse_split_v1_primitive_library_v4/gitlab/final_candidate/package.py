"""Generated candidate package; not promoted."""

class GitLabCommits:

    def __init__(self, page):
        self.page = page

    def list_repository_commits(self, project_id: int, ref_name: str=None, since: str=None, until: str=None, page_number: int=1, per_page: int=100) -> dict:
        from urllib.parse import urlencode
        params = {'page': page_number, 'per_page': per_page}
        if ref_name is not None:
            params['ref_name'] = ref_name
        if since is not None:
            params['since'] = since
        if until is not None:
            params['until'] = until
        url = f'{self.base_url}/api/v4/projects/{project_id}/repository/commits?{urlencode(params)}'
        response = self.page.request.get(url, headers={'Accept': 'application/json'})
        if not response.ok:
            raise RuntimeError(f'GitLab commits API request failed: {response.status} {url}')
        payload = response.json()
        headers = response.headers
        next_page_raw = headers.get('x-next-page') or headers.get('X-Next-Page')
        next_page = int(next_page_raw) if next_page_raw and str(next_page_raw).strip() else None
        commits = []
        for item in payload:
            commits.append({'id': item.get('id'), 'short_id': item.get('short_id'), 'title': item.get('title'), 'author_name': item.get('author_name'), 'author_email': item.get('author_email'), 'authored_date': item.get('authored_date'), 'committed_date': item.get('committed_date'), 'web_url': item.get('web_url')})
        return {'project_id': project_id, 'ref_name': ref_name, 'since': since, 'until': until, 'page_number': page_number, 'per_page': per_page, 'commits': commits, 'next_page': next_page, 'is_complete_page': next_page is None}

    def list_repository_commits_history_page(self, project_path: str, ref_name: str, page_number: int=1) -> dict:
        import re
        from urllib.parse import urlencode
        if project_path.startswith('/'):
            project_path = project_path[1:]
        params = {}
        if page_number != 1:
            params['page'] = page_number
        query = f'?{urlencode(params)}' if params else ''
        url = f'{self.base_url}/{project_path}/-/commits/{ref_name}{query}'
        self.page.goto(url, wait_until='domcontentloaded')
        body_text = self.page.locator('body').inner_text()
        lines = [line.strip() for line in body_text.splitlines() if line.strip()]
        date_pattern = re.compile('^\\d{2} [A-Z][a-z]{2}, \\d{4}$')
        count_pattern = re.compile('^(\\d+) commit(?:s)?$')
        author_pattern = re.compile('^(.*?) authored$')
        date_groups = []
        current_group = None
        for line in lines:
            if date_pattern.match(line):
                current_group = {'date_label': line, 'displayed_commit_count': None, 'commits': []}
                date_groups.append(current_group)
                continue
            if current_group is None:
                continue
            count_match = count_pattern.match(line)
            if count_match and current_group['displayed_commit_count'] is None:
                current_group['displayed_commit_count'] = int(count_match.group(1))
                continue
            author_match = author_pattern.match(line)
            if author_match:
                author_name = author_match.group(1).strip()
                current_group['commits'].append({'author_display_name': author_name if author_name else None, 'authored_text': line})
        return {'project_path': project_path, 'ref_name': ref_name, 'page_number': page_number, 'commits_page_url': url, 'date_groups': date_groups, 'completeness': 'current_commits_page_only'}

class GitLabIssues:

    def __init__(self, page):
        self.page = page

    def get_issue_details(self, project_path_with_namespace: str, issue_iid: int) -> dict:
        from urllib.parse import quote
        encoded_project = quote(project_path_with_namespace, safe='')
        url = f'{self.base_url}/api/v4/projects/{encoded_project}/issues/{issue_iid}'
        response = self.page.request.get(url, headers={'Accept': 'application/json'})
        if not response.ok:
            raise RuntimeError(f'GitLab issue detail API request failed: {response.status} {url}')
        item = response.json()
        return {'issue': {'id': item.get('id'), 'iid': item.get('iid'), 'project_id': item.get('project_id'), 'project_path_with_namespace': project_path_with_namespace, 'title': item.get('title'), 'description': item.get('description'), 'state': item.get('state'), 'created_at': item.get('created_at'), 'updated_at': item.get('updated_at'), 'closed_at': item.get('closed_at'), 'web_url': item.get('web_url')}}

    def get_issue_state_from_page(self, issue_url: str) -> dict:
        import re
        self.page.goto(issue_url, wait_until='domcontentloaded')
        self.page.wait_for_load_state('networkidle')
        body_text = self.page.locator('body').inner_text()
        state = None
        if re.search('(^|\\n)\\s*Closed\\s*(\\n|$)', body_text, re.I):
            state = 'closed'
        elif re.search('(^|\\n)\\s*Open\\s*(\\n|$)', body_text, re.I):
            state = 'open'
        if state is None:
            raise RuntimeError(f'Could not determine issue state from page: {issue_url}')
        return {'issue_url': issue_url, 'state': state}

    def list_dashboard_issues_page(self, assignee_username: str=None, author_username: str=None, state: str='all', search_query: str=None, sort: str='created_date_desc', page_number: int=1) -> dict:
        import re
        from urllib.parse import urlencode
        params = {'state': state, 'sort': sort, 'page': page_number}
        if assignee_username is not None:
            params['assignee_username'] = assignee_username
        if author_username is not None:
            params['author_username'] = author_username
        if search_query is not None:
            params['search'] = search_query
        url = f'{self.base_url}/dashboard/issues?{urlencode(params)}'
        self.page.goto(url, wait_until='domcontentloaded')
        self.page.wait_for_load_state('networkidle')
        issue_links = self.page.locator('a[href*="/-/issues/"]')
        count = issue_links.count()
        issues = []
        seen = set()
        for i in range(count):
            link = issue_links.nth(i)
            href = link.get_attribute('href')
            title = (link.inner_text() or '').strip()
            if not href:
                continue
            issue_url = href if href.startswith('http://') or href.startswith('https://') else f"{self.base_url}{(href if href.startswith('/') else '/' + href)}"
            if issue_url in seen:
                continue
            seen.add(issue_url)
            match = re.search('/([^/]+/[^/]+)/-/issues/(\\d+)', href)
            project_path_with_namespace = match.group(1) if match else None
            issue_iid = int(match.group(2)) if match else None
            issues.append({'title': title or None, 'issue_url': issue_url, 'web_url': issue_url, 'project_path_with_namespace': project_path_with_namespace, 'issue_iid': issue_iid, 'order_index': len(issues)})
        return {'assignee_username': assignee_username, 'author_username': author_username, 'search_query': search_query, 'sort': sort, 'state': state, 'page_number': page_number, 'issues': issues, 'is_complete_page': False}

    def list_project_issues(self, project_id: int, scope: str='all', order_by: str='updated_at', sort: str='desc', page_number: int=1, per_page: int=100) -> dict:
        from urllib.parse import urlencode
        params = {'scope': scope, 'order_by': order_by, 'sort': sort, 'page': page_number, 'per_page': per_page}
        url = f'{self.base_url}/api/v4/projects/{project_id}/issues?{urlencode(params)}'
        response = self.page.request.get(url, headers={'Accept': 'application/json'})
        if not response.ok:
            raise RuntimeError(f'GitLab issues API request failed: {response.status} {url}')
        payload = response.json()
        headers = response.headers
        next_page_raw = headers.get('x-next-page') or headers.get('X-Next-Page')
        next_page = int(next_page_raw) if next_page_raw and str(next_page_raw).strip() else None
        issues = []
        for item in payload:
            issues.append({'id': item.get('id'), 'iid': item.get('iid'), 'project_id': item.get('project_id', project_id), 'title': item.get('title'), 'state': item.get('state'), 'created_at': item.get('created_at'), 'updated_at': item.get('updated_at'), 'closed_at': item.get('closed_at'), 'web_url': item.get('web_url')})
        return {'project_id': project_id, 'scope': scope, 'order_by': order_by, 'sort': sort, 'page_number': page_number, 'per_page': per_page, 'issues': issues, 'next_page': next_page, 'is_complete_page': next_page is None}

    def search_issues(self, query: str, scope: str='issues', page_number: int=1) -> dict:
        from urllib.parse import urlencode
        import re
        params = {'search': query, 'scope': scope, 'page': page_number}
        url = f'{self.base_url}/search?{urlencode(params)}'
        self.page.goto(url, wait_until='networkidle')
        cards = self.page.locator('.issue, .search-result-row, .search-result, li[data-testid="search-result-row"]')
        card_count = cards.count()
        results = []
        for i in range(card_count):
            card = cards.nth(i)
            text = (card.inner_text() or '').strip()
            if not text:
                continue
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            state = None
            title = None
            if lines:
                first = lines[0].lower()
                if first in {'open', 'opened', 'closed'}:
                    state = 'closed' if first == 'closed' else 'opened'
            if len(lines) >= 2:
                title = lines[1]
            elif len(lines) == 1 and state is None:
                title = lines[0]
            link = card.locator('a[href*="/issues/"]').first
            href = link.get_attribute('href') if link.count() > 0 else None
            if href and (not href.startswith('http://')) and (not href.startswith('https://')):
                href = f"{self.base_url}{(href if href.startswith('/') else '/' + href)}"
            issue_iid = None
            if href:
                match = re.search('/issues/(\\d+)', href)
                if match:
                    issue_iid = int(match.group(1))
            if title or href:
                results.append({'title': title, 'state': state, 'url': href, 'issue_iid': issue_iid, 'order_index': len(results)})
        return {'query': query, 'scope': scope, 'page_number': page_number, 'results': results, 'is_complete_page': False}

class GitLabProjects:

    def __init__(self, page):
        self.page = page

    def get_project_by_path(self, project_path_with_namespace: str) -> dict:
        from urllib.parse import quote
        encoded_project = quote(project_path_with_namespace, safe='')
        url = f'{self.base_url}/api/v4/projects/{encoded_project}'
        response = self.page.request.get(url, headers={'Accept': 'application/json'})
        if not response.ok:
            raise RuntimeError(f'GitLab project API request failed: {response.status} {url}')
        item = response.json()
        return {'project': {'id': item.get('id'), 'name': item.get('name'), 'path': item.get('path'), 'path_with_namespace': item.get('path_with_namespace'), 'default_branch': item.get('default_branch'), 'web_url': item.get('web_url'), 'ssh_url_to_repo': item.get('ssh_url_to_repo'), 'http_url_to_repo': item.get('http_url_to_repo')}}

    def get_project_clone_urls(self, project_path: str) -> dict:
        import re
        if not project_path.startswith('/'):
            project_path = '/' + project_path
        url = f'{self.base_url}{project_path}'
        self.page.goto(url, wait_until='domcontentloaded')
        html = self.page.content()
        ssh_clone_url = None
        http_clone_url = None
        ssh_patterns = ['name=["\\\']ssh_project_clone["\\\'][^>]*value=["\\\']([^"\\\']+)["\\\']', 'Clone with SSH.*?value=["\\\']([^"\\\']+)["\\\']', '(ssh://git@[^"\\\'\\s<>]+?\\.git)', '(git@[^"\\\'\\s<>]+?\\.git)']
        for pattern in ssh_patterns:
            match = re.search(pattern, html, re.I | re.S)
            if match:
                ssh_clone_url = match.group(1)
                break
        http_patterns = ['name=["\\\']http_project_clone["\\\'][^>]*value=["\\\']([^"\\\']+)["\\\']', 'Clone with HTTPS.*?value=["\\\']([^"\\\']+)["\\\']', '(https?://[^"\\\'\\s<>]+?\\.git)']
        for pattern in http_patterns:
            match = re.search(pattern, html, re.I | re.S)
            if match:
                http_clone_url = match.group(1)
                break
        return {'project_path': project_path, 'project_url': url, 'ssh_clone_url': ssh_clone_url, 'http_clone_url': http_clone_url}

    def list_membership_projects(self, page_number: int=1, per_page: int=100) -> dict:
        from urllib.parse import urlencode
        params = {'membership': 'true', 'simple': 'true', 'page': page_number, 'per_page': per_page}
        url = f'{self.base_url}/api/v4/projects?{urlencode(params)}'
        response = self.page.request.get(url, headers={'Accept': 'application/json'})
        if not response.ok:
            raise RuntimeError(f'GitLab membership projects API request failed: {response.status} {url}')
        payload = response.json()
        headers = response.headers
        next_page_raw = headers.get('x-next-page') or headers.get('X-Next-Page')
        next_page = int(next_page_raw) if next_page_raw and str(next_page_raw).strip() else None
        projects = []
        for item in payload:
            projects.append({'id': item.get('id'), 'name': item.get('name'), 'path': item.get('path'), 'path_with_namespace': item.get('path_with_namespace'), 'web_url': item.get('web_url')})
        return {'page_number': page_number, 'per_page': per_page, 'projects': projects, 'next_page': next_page, 'is_complete_page': next_page is None}

    def list_personal_projects_page(self, sort_by: str='most_stars', page_number: int=1) -> dict:
        import re
        from urllib.parse import urlencode
        sort_map = {'most_stars': 'stars_desc'}
        params = {'personal': 'true', 'page': page_number}
        if sort_by in sort_map:
            params['sort'] = sort_map[sort_by]
        url = f'{self.base_url}/dashboard/projects?{urlencode(params)}'
        self.page.goto(url, wait_until='domcontentloaded')
        items = self.page.locator('main ul > li')
        count = items.count()
        projects = []
        for i in range(count):
            item = items.nth(i)
            name_link = item.locator('h2 a').first
            if name_link.count() == 0:
                continue
            href = name_link.get_attribute('href')
            name = (name_link.inner_text() or '').strip()
            if not href or not name:
                continue
            full_url = href if href.startswith('http://') or href.startswith('https://') else f"{self.base_url}{(href if href.startswith('/') else '/' + href)}"
            path_with_namespace = href.split('?', 1)[0].split('#', 1)[0].strip('/')
            role_text = item.inner_text() or ''
            viewer_role_is_owner = bool(re.search('\\bOwner\\b', role_text))
            star_count = None
            star_link = item.locator('a[href$="/-/starrers"]').first
            if star_link.count() > 0:
                star_text = (star_link.inner_text() or '').strip()
                star_match = re.search('\\d+', star_text)
                if star_match:
                    star_count = int(star_match.group(0))
            projects.append({'name': name, 'web_url': full_url, 'path_with_namespace': path_with_namespace, 'star_count': star_count, 'viewer_role_is_owner': viewer_role_is_owner})
        return {'page_number': page_number, 'applied_scope': 'personal', 'sort_by': sort_by, 'projects': projects, 'completeness': 'visible_page_only'}

    def search_project_links(self, query: str, page_number: int=1) -> dict:
        import re
        from urllib.parse import urlencode
        params = {'scope': 'projects', 'search': query, 'page': page_number}
        url = f'{self.base_url}/search?{urlencode(params)}'
        self.page.goto(url, wait_until='domcontentloaded')
        anchors = self.page.locator('a[href]')
        count = anchors.count()
        results = []
        seen = set()
        for i in range(count):
            anchor = anchors.nth(i)
            href = anchor.get_attribute('href')
            text = (anchor.inner_text() or '').strip()
            if not href:
                continue
            if '/-/' in href or href.startswith('#'):
                continue
            normalized_href = href if href.startswith('http://') or href.startswith('https://') else f"{self.base_url}{(href if href.startswith('/') else '/' + href)}"
            path = href
            if href.startswith('http://') or href.startswith('https://'):
                path_match = re.match('^https?://[^/]+(/[^?#]*)', href)
                path = path_match.group(1) if path_match else href
            path = path.split('?')[0].split('#')[0]
            if not re.match('^/[^/]+/[^/]+/?$', path):
                continue
            if normalized_href in seen:
                continue
            seen.add(normalized_href)
            results.append({'project_path': path.rstrip('/'), 'project_url': normalized_href, 'display_text': text, 'order_index': len(results)})
        return {'query': query, 'page_number': page_number, 'results': results, 'is_complete_page': False}

class GitLabSite:

    def __init__(self, page):
        self.commits = GitLabCommits(page)
        self.issues = GitLabIssues(page)
        self.projects = GitLabProjects(page)
