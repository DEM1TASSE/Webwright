"""Generated candidate package; not promoted."""

class GitLabCommits:

    def __init__(self, page):
        self.page = page

    def list_repository_commits(self, base_url: str, project_id: int, since: str | None=None, until: str | None=None, per_page: int | None=None, page_number: int | None=None) -> dict:
        import json
        from urllib.parse import urlencode
        from urllib.request import Request, urlopen
        params = {}
        if since is not None:
            params['since'] = since
        if until is not None:
            params['until'] = until
        if per_page is not None:
            params['per_page'] = str(per_page)
        if page_number is not None:
            params['page'] = str(page_number)
        url = base_url.rstrip('/') + f'/api/v4/projects/{project_id}/repository/commits'
        if params:
            url += '?' + urlencode(params)
        request = Request(url)
        with urlopen(request) as response:
            payload = json.loads(response.read().decode('utf-8'))
            headers = {k: v for (k, v) in response.headers.items()}

        def _to_int(value):
            if value in (None, ''):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        commits = []
        for item in payload:
            commits.append({'id': item.get('id'), 'short_id': item.get('short_id'), 'title': item.get('title'), 'message': item.get('message'), 'author_name': item.get('author_name'), 'author_email': item.get('author_email'), 'authored_date': item.get('authored_date'), 'committer_name': item.get('committer_name'), 'committer_email': item.get('committer_email'), 'committed_date': item.get('committed_date'), 'created_at': item.get('created_at'), 'parent_ids': item.get('parent_ids') or [], 'web_url': item.get('web_url')})
        return {'project_id': project_id, 'commits': commits, 'pagination': {'page_number': _to_int(headers.get('X-Page')), 'per_page': _to_int(headers.get('X-Per-Page')), 'next_page': _to_int(headers.get('X-Next-Page')), 'prev_page': _to_int(headers.get('X-Prev-Page'))}, 'source_url': url}

class GitLabContributors:

    def __init__(self, page):
        self.page = page

    def list_repository_branch_contributors(self, base_url: str, project_path: str, branch_name: str, limit: int | None=None) -> dict:
        import re
        normalized_project_path = project_path.strip('/')
        url = base_url.rstrip('/') + f'/{normalized_project_path}/-/graphs/{branch_name}'
        self.page.goto(url, wait_until='networkidle')
        text = self.page.locator('main').inner_text()
        pattern = re.compile("([A-Za-z][A-Za-z0-9.'\\-\\[\\] ]*[A-Za-z0-9\\]])\\n\\n(\\d+) commits? \\(")
        matches = pattern.findall(text)
        contributors = []
        seen = set()
        for (name, commits) in matches:
            full_name = ' '.join(name.split())
            commit_count = int(commits)
            key = (full_name, commit_count)
            if key in seen:
                continue
            seen.add(key)
            contributors.append({'rank': len(contributors) + 1, 'full_name': full_name, 'commit_count': commit_count})
        is_partial = False
        if limit is not None:
            contributors = contributors[:limit]
            is_partial = True
        return {'project_path': '/' + normalized_project_path, 'branch_name': branch_name, 'contributors': contributors, 'is_partial': is_partial, 'source_url': url}

class GitLabIssues:

    def __init__(self, page):
        self.page = page

    def get_issue_detail_state(self, issue_url: str) -> dict:
        import re
        self.page.goto(issue_url, wait_until='domcontentloaded')
        body = self.page.locator('body').inner_text()
        page_title = self.page.title()
        has_open_label = bool(re.search('\\bOpen\\b', body))
        has_close_issue_action = 'Close issue' in body
        has_closed_label = bool(re.search('\\bClosed\\b', body))
        has_reopen_issue_action = 'Reopen issue' in body
        if has_closed_label and has_reopen_issue_action:
            state = 'closed'
        elif has_open_label and has_close_issue_action:
            state = 'opened'
        else:
            state = 'unknown'
        return {'web_url': self.page.url, 'page_title': page_title, 'state': state, 'state_signals': {'has_open_label': has_open_label, 'has_close_issue_action': has_close_issue_action, 'has_closed_label': has_closed_label, 'has_reopen_issue_action': has_reopen_issue_action}}

    def list_dashboard_issues_by_actor_and_state(self, base_url: str, filter_type: str, username: str, state: str, page_number: int | None=None) -> dict:
        from urllib.parse import urlencode
        if filter_type not in {'author_username', 'assignee_username'}:
            raise ValueError("filter_type must be 'author_username' or 'assignee_username'")
        params = {filter_type: username, 'state': state}
        if page_number is not None:
            params['page'] = str(page_number)
        url = base_url.rstrip('/') + '/dashboard/issues?' + urlencode(params)
        self.page.goto(url, wait_until='domcontentloaded')
        issues = self.page.locator('a').evaluate_all("\n            els => els\n              .map(e => ({title:(e.innerText||'').trim(), web_url:e.href}))\n              .filter(x => x.title && /\\/issues\\/\\d+$/.test(x.web_url))\n            ")
        next_href = self.page.locator('a[rel="next"], a').evaluate_all("\n            els => {\n              const found = els.find(e => (e.getAttribute('rel') || '') === 'next' || (e.innerText || '').trim() === 'Next');\n              return found ? found.href : '';\n            }\n            ")
        current_page_number = page_number if page_number is not None else 1
        next_page_number = current_page_number + 1 if next_href else None
        return {'issues': issues, 'page_number': current_page_number, 'next_page_number': next_page_number, 'has_next_page': bool(next_href), 'is_complete': not bool(next_href), 'source_url': self.page.url}

class GitLabMembers:

    def __init__(self, page):
        self.page = page

    def list_project_members(self, base_url: str, project_path: str) -> dict:
        import html
        import json
        import re
        normalized_project_path = project_path if project_path.startswith('/') else f'/{project_path}'
        url = base_url.rstrip('/') + normalized_project_path + '/-/project_members'
        self.page.goto(url, wait_until='domcontentloaded')
        content = self.page.content()
        match = re.search('data-members-data="([^"]+)"', content)
        if not match:
            raise ValueError('Could not find structured members data on project members page')
        decoded = html.unescape(match.group(1))
        data = json.loads(decoded)
        raw_members = (data.get('user') or {}).get('members') or []
        members = []
        for member in raw_members:
            user = member.get('user') or {}
            access_level = member.get('access_level') or {}
            members.append({'username': user.get('username'), 'name': user.get('name'), 'id': user.get('id'), 'state': user.get('state'), 'avatar_url': user.get('avatar_url'), 'web_url': user.get('web_url'), 'access_level': access_level.get('string_value'), 'access_level_integer': access_level.get('integer_value'), 'member_type': member.get('type'), 'expires_at': member.get('expires_at')})
        return {'project_path': normalized_project_path, 'members': members, 'source_url': url}

class GitLabProjects:

    def __init__(self, page):
        self.page = page

    def get_project_overview_metrics(self, project_url: str) -> dict:
        import re
        self.page.goto(project_url, wait_until='domcontentloaded')
        body = self.page.locator('body').inner_text()
        id_match = re.search('Project ID:\\s*(\\d+)', body)
        star_match = re.search('\\bStar\\s*(\\d+)\\b', body)
        return {'project_url': self.page.url, 'project_id': int(id_match.group(1)) if id_match else None, 'stars_count': int(star_match.group(1)) if star_match else None}

    def inspect_project_page_availability(self, base_url: str, namespace: str, project_name: str) -> dict:
        requested_path = f"/{namespace.strip('/')}/{project_name.strip('/')}"
        url = base_url.rstrip('/') + requested_path
        self.page.goto(url, wait_until='domcontentloaded')
        page_title = self.page.title()
        body_text = self.page.locator('body').inner_text()
        lowered = body_text.lower()
        if 'page not found' in lowered or 'the page could not be found' in lowered or 'not found' in lowered:
            availability = 'NOT_FOUND_OR_INACCESSIBLE'
        elif self.page.url.rstrip('/') == url.rstrip('/'):
            availability = 'ACCESSIBLE'
        else:
            availability = 'UNKNOWN'
        return {'requested_path': requested_path, 'project_url': self.page.url, 'page_title': page_title, 'availability': availability}

    def list_dashboard_projects(self, base_url: str, scope: str | None=None) -> dict:
        import re
        url = base_url.rstrip('/') + '/dashboard/projects'
        self.page.goto(url, wait_until='domcontentloaded')
        applied_scope = None
        if scope == 'personal':
            self.page.get_by_role('link', name='Personal').click()
            self.page.wait_for_load_state('domcontentloaded')
            applied_scope = 'personal'
        items = self.page.locator('main .projects-list > li')
        count = items.count()
        records = []
        for i in range(count):
            li = items.nth(i)
            text = (li.inner_text() or '').strip()
            links = li.locator('a').evaluate_all("els => els.map(a => ({text:(a.innerText||'').trim(), href:a.getAttribute('href')}))")
            title_link = None
            for link in links:
                link_text = (link.get('text') or '').strip()
                href = link.get('href')
                if link_text and '/' in link_text and href and ('/-/' not in href):
                    title_link = link
                    break
            counts_match = re.search('\\n\\s*(\\d+)\\s*\\n\\s*(\\d+)\\s*\\n\\s*(\\d+)\\s*\\n\\s*(\\d+)\\s*\\n\\s*Updated', '\n' + text + '\n')
            if not title_link or not counts_match:
                continue
            (stars_count, forks_count, merge_requests_count, issues_count) = map(int, counts_match.groups())
            project_url = title_link.get('href')
            if project_url and project_url.startswith('/'):
                absolute_url = base_url.rstrip('/') + project_url
            else:
                absolute_url = project_url
            records.append({'project_path': title_link.get('text'), 'project_url': absolute_url, 'relative_project_url': project_url, 'stars_count': stars_count, 'forks_count': forks_count, 'merge_requests_count': merge_requests_count, 'issues_count': issues_count})
        return {'records': records, 'completeness': {'scope_applied': applied_scope, 'pagination_complete': False}, 'source_url': self.page.url}

class GitLabSite:

    def __init__(self, page):
        self.commits = GitLabCommits(page)
        self.contributors = GitLabContributors(page)
        self.issues = GitLabIssues(page)
        self.members = GitLabMembers(page)
        self.projects = GitLabProjects(page)
