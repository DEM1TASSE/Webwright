"""Generated candidate package; not promoted."""

class GitLabCommits:

    def __init__(self, page):
        self.page = page

    def list_repository_commits_via_api(self, base_url, project_id, since=None, until=None, page_number=None, per_page=None):
        import json
        from urllib.parse import urlencode
        from urllib.request import Request, urlopen
        api_url = f"{base_url.rstrip('/')}/api/v4/projects/{project_id}/repository/commits"
        params = {}
        if since:
            params['since'] = since
        if until:
            params['until'] = until
        if page_number is not None:
            params['page'] = str(page_number)
        if per_page is not None:
            params['per_page'] = str(per_page)
        url = api_url + ('?' + urlencode(params) if params else '')
        request = Request(url)
        cookie_header_parts = []
        for cookie in self.page.context.cookies():
            name = cookie.get('name')
            value = cookie.get('value')
            if name and value is not None:
                cookie_header_parts.append(f'{name}={value}')
        if cookie_header_parts:
            request.add_header('Cookie', '; '.join(cookie_header_parts))
        with urlopen(request) as response:
            commits = json.loads(response.read().decode('utf-8'))
            headers = dict(response.headers.items())
        pagination = {'x_page': headers.get('X-Page'), 'x_per_page': headers.get('X-Per-Page'), 'x_next_page': headers.get('X-Next-Page'), 'x_prev_page': headers.get('X-Prev-Page'), 'x_total': headers.get('X-Total'), 'x_total_pages': headers.get('X-Total-Pages')}
        return {'commits': commits, 'pagination': pagination}

    def list_visible_repository_contributors_from_graphs_page(self, repository_path, branch):
        import re
        from urllib.parse import urlparse
        current = urlparse(self.page.url)
        base_url = f'{current.scheme}://{current.netloc}'
        target_url = f"{base_url}/{repository_path.strip('/')}/-/graphs/{branch}"
        self.page.goto(target_url, wait_until='networkidle')
        main_text = self.page.locator('main').inner_text()
        pattern = re.compile("([A-Za-z][A-Za-z0-9.'\\-\\[\\] ]*[A-Za-z0-9\\]])\\n\\n(\\d+) commits? \\(")
        contributors = []
        seen = set()
        for name, commits in pattern.findall(main_text):
            clean_name = ' '.join(name.split())
            record = (clean_name, int(commits))
            if record in seen:
                continue
            seen.add(record)
            contributors.append({'display_name': clean_name, 'commit_count': int(commits)})
        return {'contributors': contributors, 'source_url': target_url, 'is_complete': False}

class GitLabProjects:

    def __init__(self, page):
        self.page = page

    def get_project_metadata_from_project_page(self, base_url, project_href):
        import re
        target_url = f"{base_url.rstrip('/')}/{project_href.lstrip('/')}"
        self.page.goto(target_url, wait_until='domcontentloaded')
        body = self.page.locator('body').inner_text()
        project_id_match = re.search('Project ID:\\s*(\\d+)', body)
        star_match = re.search('\\bStar\\s*(\\d+)\\b', body)
        return {'project': {'project_id': int(project_id_match.group(1)) if project_id_match else None, 'star_count': int(star_match.group(1)) if star_match else None, 'source_url': target_url}}

    def list_personal_projects_from_dashboard(self, base_url):
        import re
        self.page.goto(f"{base_url.rstrip('/')}/dashboard/projects", wait_until='domcontentloaded')
        self.page.get_by_role('link', name='Personal').click()
        self.page.wait_for_load_state('domcontentloaded')
        items = self.page.locator('main .projects-list > li')
        projects = []
        pattern = re.compile('\\n\\s*(\\d+)\\s*\\n\\s*(\\d+)\\s*\\n\\s*(\\d+)\\s*\\n\\s*(\\d+)\\s*\\n\\s*Updated')
        for index in range(items.count()):
            item = items.nth(index)
            text = item.inner_text().strip()
            links = item.locator('a').evaluate_all("els => els.map(a => ({text:(a.innerText||'').trim(), href:a.getAttribute('href')}))")
            title_link = next((x for x in links if x.get('text') and '/' in x.get('text') and (not x.get('text').isdigit())), None)
            match = pattern.search('\n' + text + '\n')
            if title_link and match:
                stars, forks, merge_requests, issues = map(int, match.groups())
                projects.append({'display_path': title_link['text'], 'href': title_link['href'], 'stars_count': stars, 'forks_count': forks, 'merge_requests_count': merge_requests, 'issues_count': issues})
        return {'projects': projects}

    def list_project_members_from_members_page_blob(self, base_url, project_path):
        import html
        import json
        import re
        from urllib.parse import urljoin
        import requests
        members_url = urljoin(base_url.rstrip('/') + '/', project_path.strip('/') + '/-/project_members')
        session = requests.Session()
        cookies = self.page.context.cookies()
        for cookie in cookies:
            session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain'), path=cookie.get('path', '/'))
        response = session.get(members_url)
        response.raise_for_status()
        match = re.search('data-members-data="([^"]+)"', response.text)
        if not match:
            raise RuntimeError('Could not find data-members-data blob on members page')
        decoded = html.unescape(match.group(1))
        data = json.loads(decoded)
        members = []
        usernames = []
        for member in data['user']['members']:
            user = member.get('user') or {}
            record = {'username': user.get('username'), 'name': user.get('name'), 'access_level': (member.get('access_level') or {}).get('string_value'), 'type': member.get('type'), 'expires_at': member.get('expires_at'), 'state': user.get('state'), 'avatar_url': user.get('avatar_url'), 'web_url': user.get('web_url')}
            members.append(record)
            if record['username']:
                usernames.append(record['username'])
        return {'members': members, 'usernames': usernames}

class GitLabReviews:

    def __init__(self, page):
        self.page = page

    def get_issue_state_from_detail_page(self, issue_url):
        import re
        self.page.goto(issue_url, wait_until='domcontentloaded')
        body = self.page.locator('body').inner_text()
        state = None
        if re.search('\\bClosed\\b', body) and re.search('Reopen issue', body):
            state = 'closed'
        elif re.search('\\bOpen\\b', body) and re.search('Close issue', body):
            state = 'open'
        return {'issue': {'issue_url': issue_url, 'state': state}}

    def list_dashboard_issues(self, dashboard_url):
        issues = []
        visited_pages = []
        seen_issue_urls = set()
        current_url = dashboard_url
        while current_url and current_url not in visited_pages:
            visited_pages.append(current_url)
            self.page.goto(current_url, wait_until='domcontentloaded')
            issue_links = self.page.locator('a').evaluate_all("els => els.map(e => ({ text:(e.innerText||'').trim(), href:e.href })).filter(x => x.text && /\\/issues\\/\\d+$/.test(x.href))")
            for item in issue_links:
                href = item.get('href')
                if href not in seen_issue_urls:
                    seen_issue_urls.add(href)
                    issues.append({'title': item.get('text'), 'href': href})
            next_href = self.page.locator("a[rel='next'], a").evaluate_all("els => { const found = els.find(e => (e.getAttribute('rel')||'') === 'next' || (e.innerText||'').trim() === 'Next'); return found ? found.href : ''; }")
            current_url = next_href if next_href and next_href != self.page.url else ''
        return {'issues': issues, 'visited_pages': visited_pages}

class GitLabSite:

    def __init__(self, page):
        self.commits = GitLabCommits(page)
        self.projects = GitLabProjects(page)
        self.reviews = GitLabReviews(page)
