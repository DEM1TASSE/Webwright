def get_pending_review_grid_summary(self, username: str, password: str) -> dict:
    import http.cookiejar
    import re
    import urllib.parse
    import urllib.request

    if not isinstance(username, str) or not username:
        raise ValueError("username must be a non-empty string")
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")

    base = "http://GCRSANDBOX410.redmond.corp.microsoft.com:7780"
    login_url = base + "/admin"
    pending_url = base + "/admin/review/product/pending/"

    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    resp = opener.open(login_url)
    login_html = resp.read().decode("utf-8", "ignore")
    form_key_match = re.search(r'name="form_key" type="hidden" value="([^"]+)"', login_html)
    if not form_key_match:
        raise RuntimeError("Could not extract login form_key")
    form_key = form_key_match.group(1)

    post = urllib.parse.urlencode(
        {
            "form_key": form_key,
            "login[username]": username,
            "login[password]": password,
        }
    ).encode()
    login_resp = opener.open(login_url, post)
    login_resp.read().decode("utf-8", "ignore")

    resp = opener.open(pending_url)
    final_url = resp.geturl()
    pending_html = resp.read().decode("utf-8", "ignore")

    m = re.search(r'id="reviewGrid-total-count"[^>]*>\s*(\d+)\s*<', pending_html)
    if not m:
        raise RuntimeError("Could not find reviewGrid-total-count on Pending Reviews page")

    return {
        "review_status": "pending",
        "total_count": int(m.group(1)),
        "page_url": final_url,
        "authenticated": True,
    }
