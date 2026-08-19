def get_admin_reviews_total_count_via_http_session(self, base_url: str, username: str, password: str) -> dict:
    import html
    import http.cookiejar
    import re
    import urllib.parse
    import urllib.request

    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("base_url must be a non-empty string")
    if not isinstance(username, str) or not username:
        raise ValueError("username must be a non-empty string")
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")

    base_url = base_url.rstrip("/")
    start_url = base_url + "/admin"
    reviews_url = base_url + "/admin/review/product/index/"

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    login_resp = opener.open(start_url)
    login_html = login_resp.read().decode("utf-8", "ignore")
    form_inputs = dict(
        re.findall(
            r'<input[^>]+name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\']',
            login_html,
            re.I,
        )
    )
    form_inputs["login[username]"] = username
    form_inputs["login[password]"] = password

    dashboard_req = urllib.request.Request(
        start_url,
        data=urllib.parse.urlencode(form_inputs).encode(),
    )
    dashboard_resp = opener.open(dashboard_req)
    dashboard_html = dashboard_resp.read().decode("utf-8", "ignore")
    dashboard_text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", dashboard_html, flags=re.I | re.S)
    dashboard_text = re.sub(r"<[^>]+>", " ", dashboard_text)
    dashboard_text = re.sub(r"\s+", " ", html.unescape(dashboard_text)).strip()
    if "Dashboard / Magento Admin" not in dashboard_html and "Dashboard" not in dashboard_text:
        raise RuntimeError("Login did not reach dashboard")

    reviews_resp = opener.open(reviews_url)
    reviews_html = reviews_resp.read().decode("utf-8", "ignore")
    reviews_text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", reviews_html, flags=re.I | re.S)
    reviews_text = re.sub(r"<[^>]+>", " ", reviews_text)
    reviews_text = re.sub(r"\s+", " ", html.unescape(reviews_text)).strip()

    match = re.search(r"(\d+)\s+records\s+found", reviews_text, re.I)
    if not match:
        raise RuntimeError("Could not find total review record count on All Reviews page")

    title_match = re.search(r"<title>(.*?)</title>", reviews_html, re.I | re.S)
    page_title = html.unescape(title_match.group(1).strip()) if title_match else ""

    return {
        "reviews_total_count": int(match.group(1)),
        "reviews_url": reviews_resp.geturl(),
        "reviews_status": getattr(reviews_resp, "status", None),
        "page_title": page_title,
    }
