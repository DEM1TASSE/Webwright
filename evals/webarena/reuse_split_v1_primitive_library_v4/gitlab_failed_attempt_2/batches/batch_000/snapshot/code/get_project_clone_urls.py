def get_project_clone_urls(self, base_url: str, username: str, password: str, project_path: str) -> dict:
    import re
    import html as html_lib
    import requests

    session = requests.Session()
    sign_in = session.get(f"{base_url}/users/sign_in", timeout=30)
    sign_in.raise_for_status()

    match = re.search(r'name=["\']authenticity_token["\'][^>]*value=["\']([^"\']+)', sign_in.text, re.I | re.S)
    if not match:
        match = re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']authenticity_token["\']', sign_in.text, re.I | re.S)
    if not match:
        raise RuntimeError("Could not find authenticity token on sign-in page")

    login_resp = session.post(
        f"{base_url}/users/sign_in",
        data={
            "authenticity_token": html_lib.unescape(match.group(1)),
            "user[login]": username,
            "user[password]": password,
            "user[remember_me]": "0",
        },
        headers={"Referer": f"{base_url}/users/sign_in"},
        timeout=30,
        allow_redirects=True,
    )
    login_resp.raise_for_status()

    response = session.get(f"{base_url}{project_path}", timeout=30)
    response.raise_for_status()
    page_html = response.text

    ssh_clone_url = None
    http_clone_url = None

    ssh_match = re.search(r'name=["\']ssh_project_clone["\'][^>]*value=["\']([^"\']+)', page_html, re.I | re.S)
    if not ssh_match:
        ssh_match = re.search(r'Clone with SSH.*?value=["\']([^"\']+)["\']', page_html, re.I | re.S)
    if not ssh_match:
        ssh_match = re.search(r'(git@[^"\'\s<>]+?\.git)', page_html, re.I)
    if ssh_match:
        ssh_clone_url = html_lib.unescape(ssh_match.group(1))

    http_match = re.search(r'name=["\']http_project_clone["\'][^>]*value=["\']([^"\']+)', page_html, re.I | re.S)
    if http_match:
        http_clone_url = html_lib.unescape(http_match.group(1))

    return {
        "project_path": project_path,
        "project_url": response.url,
        "ssh_clone_url": ssh_clone_url,
        "http_clone_url": http_clone_url,
    }
