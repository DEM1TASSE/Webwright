"""Generated candidate package; not promoted."""

class GitLabIssues:

    def __init__(self, page):
        self.page = page

    def get_issue_closed_state_from_issue_page(self, issue_url):
        import re
        self.page.goto(issue_url, wait_until='domcontentloaded')
        body = self.page.locator('body').inner_text()
        title = self.page.title()
        is_open = bool(re.search('\\bOpen\\b', body) and 'Close issue' in body)
        is_closed = bool(re.search('\\bClosed\\b', body) and 'Reopen issue' in body)
        return {'issue_state': {'title': title, 'is_open': is_open, 'is_closed': is_closed}}

    def search_dashboard_issues_by_role_and_title_substring(self, base_url, role_filters, title_substring):
        visited = set()
        matches = []
        needle = title_substring.lower()
        for role_filter in role_filters:
            role_name = role_filter['role_name']
            username = role_filter['username']
            state = role_filter.get('state', 'all')
            url = f"{base_url.rstrip('/')}/dashboard/issues?{role_name}={username}&state={state}"
            while url and url not in visited:
                visited.add(url)
                self.page.goto(url, wait_until='domcontentloaded')
                issue_links = self.page.locator('a').evaluate_all("els => els.map(e => ({ text:(e.innerText||'').trim(), href:e.href })).filter(x => x.text && /\\/issues\\/\\d+$/.test(x.href))")
                for item in issue_links:
                    if needle in item['text'].lower():
                        matches.append({'title': item['text'], 'href': item['href'], 'source_list_url': url})
                next_href = self.page.locator('a[rel="next"], a').evaluate_all("els => { const found = els.find(e => (e.getAttribute('rel')||'') === 'next' || (e.innerText||'').trim() === 'Next'); return found ? found.href : ''; }")
                url = next_href if next_href and next_href != self.page.url else ''
        unique = []
        seen = set()
        for item in matches:
            if item['href'] not in seen:
                seen.add(item['href'])
                unique.append(item)
        return {'matches': unique}

class GitLabMembers:

    def __init__(self, page):
        self.page = page

    def list_project_members_from_members_page(self, base_url, project_path):
        import html
        import json
        import re
        from urllib.parse import urljoin
        from urllib.request import Request, urlopen
        members_url = urljoin(base_url.rstrip('/') + '/', project_path.lstrip('/') + '/-/project_members')
        cookies = self.page.context.cookies()
        cookie_header = '; '.join((f"{cookie['name']}={cookie['value']}" for cookie in cookies))
        headers = {'Cookie': cookie_header} if cookie_header else {}
        request = Request(members_url, headers=headers)
        with urlopen(request) as response:
            page_html = response.read().decode('utf-8')
        match = re.search('data-members-data="([^"]+)"', page_html)
        if not match:
            raise RuntimeError('Could not find data-members-data blob on members page')
        decoded = html.unescape(match.group(1))
        data = json.loads(decoded)
        members = []
        for member in data.get('user', {}).get('members', []):
            user = member.get('user') or {}
            members.append({'username': user.get('username'), 'name': user.get('name'), 'access_level': (member.get('access_level') or {}).get('string_value'), 'type': member.get('type')})
        return {'members': members}

class GitLabProjects:

    def __init__(self, page):
        self.page = page

    def get_project_id_and_star_count_from_project_page(self, base_url, project_path):
        import re
        self.page.goto(f"{base_url.rstrip('/')}/{project_path.strip('/')}", wait_until='domcontentloaded')
        body = self.page.locator('body').inner_text()
        id_match = re.search('Project ID:\\s*(\\d+)', body)
        star_match = re.search('\\bStar\\s*(\\d+)\\b', body)
        return {'project': {'project_id': int(id_match.group(1)) if id_match else None, 'star_count': int(star_match.group(1)) if star_match else None}}

    def list_personal_projects_from_dashboard_with_stats(self, base_url):
        import re
        self.page.goto(f"{base_url.rstrip('/')}/dashboard/projects", wait_until='domcontentloaded')
        self.page.get_by_role('link', name='Personal').click()
        self.page.wait_for_load_state('domcontentloaded')
        items = self.page.locator('main .projects-list > li')
        projects = []
        for index in range(items.count()):
            item = items.nth(index)
            text = item.inner_text().strip()
            links = item.locator('a').evaluate_all("els => els.map(a => ({text:(a.innerText||'').trim(), href:a.getAttribute('href')}))")
            title_link = next((entry for entry in links if entry['text'] and '/' in entry['text'] and (not entry['text'].isdigit())), None)
            match = re.search('\\n\\s*(\\d+)\\s*\\n\\s*(\\d+)\\s*\\n\\s*(\\d+)\\s*\\n\\s*(\\d+)\\s*\\n\\s*Updated', '\n' + text + '\n')
            if title_link and match:
                stars, forks, merge_requests, issues = map(int, match.groups())
                projects.append({'project_name': title_link['text'], 'project_path': title_link['href'], 'stars_count': stars, 'forks_count': forks, 'merge_requests_count': merge_requests, 'issues_count': issues})
        return {'projects': projects}

    def search_personal_projects_by_name(self, base_url, owner_username, name_query, sort='name_asc'):
        import html
        import re
        from urllib.parse import urlencode, urljoin
        from urllib.request import Request, urlopen
        query = urlencode({'name': name_query, 'personal': 'true', 'sort': sort})
        url = f"{base_url.rstrip('/')}/dashboard/projects?{query}"
        cookies = self.page.context.cookies()
        cookie_header = '; '.join((f"{cookie['name']}={cookie['value']}" for cookie in cookies))
        headers = {'Cookie': cookie_header} if cookie_header else {}
        request = Request(url, headers=headers)
        with urlopen(request) as response:
            page_html = response.read().decode('utf-8')
        projects = []
        seen = set()
        for href, text in re.findall('<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page_html, re.S | re.I):
            clean = re.sub('<[^>]+>', ' ', text)
            clean = re.sub('\\s+', ' ', html.unescape(clean)).strip()
            if href.startswith(f'/{owner_username}/') and '/-/' not in href and (href not in seen):
                seen.add(href)
                projects.append({'project_path': href, 'label': clean, 'url': urljoin(base_url.rstrip('/') + '/', href.lstrip('/'))})
        return {'projects': projects}

class GitLabRepository:

    def __init__(self, page):
        self.page = page

    def list_branch_contributors_from_graphs_page(self, base_url, project_path, branch):
        import re
        url = f"{base_url.rstrip('/')}/{project_path.strip('/')}/-/graphs/{branch}"
        self.page.goto(url, wait_until='networkidle')
        body_text = self.page.locator('main').inner_text()
        pattern = re.compile("([A-Za-z][A-Za-z0-9.'\\-\\[\\] ]*[A-Za-z0-9\\]])\\n\\n(\\d+) commits? \\(")
        contributors = []
        seen = set()
        for name, commits in pattern.findall(body_text):
            clean = ' '.join(name.split())
            key = (clean, int(commits))
            if key in seen:
                continue
            seen.add(key)
            contributors.append({'full_name': clean, 'commit_count': int(commits)})
        return {'contributors': contributors}

    def list_repository_commits_in_date_range(self, base_url, project_id, since, until, page_number=1, per_page=100):
        import json
        from urllib.parse import urlencode
        from urllib.request import Request, urlopen
        params = {'since': since, 'until': until, 'page': page_number, 'per_page': per_page}
        url = f"{base_url.rstrip('/')}/api/v4/projects/{project_id}/repository/commits?{urlencode(params)}"
        request = Request(url)
        with urlopen(request) as response:
            payload = json.loads(response.read().decode('utf-8'))
            headers = response.headers
        commits = []
        for item in payload:
            commits.append({'id': item.get('id'), 'short_id': item.get('short_id'), 'title': item.get('title'), 'author_name': item.get('author_name'), 'authored_date': item.get('authored_date'), 'committed_date': item.get('committed_date'), 'created_at': item.get('created_at'), 'web_url': item.get('web_url')})
        return {'commits': commits, 'pagination': {'x_page': headers.get('X-Page'), 'x_per_page': headers.get('X-Per-Page'), 'x_next_page': headers.get('X-Next-Page')}}

class GitLabSite:

    def __init__(self, page):
        self.issues = GitLabIssues(page)
        self.members = GitLabMembers(page)
        self.projects = GitLabProjects(page)
        self.repository = GitLabRepository(page)
