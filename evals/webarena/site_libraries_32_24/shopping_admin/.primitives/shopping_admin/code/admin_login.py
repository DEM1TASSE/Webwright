from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor, Request
from http.cookiejar import CookieJar
import re


def _extract_form_key(html: str):
    m = re.search(r'name=["\']form_key["\']\s+type=["\']hidden["\']\s+value=["\']([^"\']+)["\']', html, re.I)
    return m.group(1) if m else None


def _looks_authenticated(html: str, final_url: str) -> bool:
    text = html.lower()
    return ('dashboard' in text or 'all reviews' in text or 'pending reviews' in text or '/admin/' in final_url) and 'login[password]' not in text


def admin_login(base_admin_url: str, username: str, password: str):
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    login_html = opener.open(base_admin_url, timeout=30).read().decode('utf-8', 'ignore')
    form_key = _extract_form_key(login_html)
    payload = {'login[username]': username, 'login[password]': password}
    if form_key:
        payload['form_key'] = form_key
    req = Request(
        base_admin_url,
        data=urlencode(payload).encode('utf-8'),
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    resp = opener.open(req, timeout=30)
    html = resp.read().decode('utf-8', 'ignore')
    final_url = resp.geturl()
    if not _looks_authenticated(html, final_url):
        raise RuntimeError('admin_login_failed')
    return {
        'opener': opener,
        'cookie_jar': jar,
        'base_admin_url': base_admin_url,
        'final_url': final_url,
        'dashboard_html': html,
    }
