#!/usr/bin/env python3
"""Check emma.lopez's live wishlist on the WebArena shopping site."""
import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request

B = "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:7770"
USER, PW = "emma.lopez@gmail.com", "Password.123"

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders = [
    ("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"),
    ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"),
]

login_html = op.open(B + "/customer/account/login/", timeout=30).read().decode("utf8", "replace")
form_key = None
for pat in (r'name=["\']form_key["\'][^>]*value=["\']([^"\']+)',
            r'value=["\']([^"\']+)["\'][^>]*name=["\']form_key["\']',
            r'form_key["\']?\s*[:=]\s*["\']([^"\']+)'):
    m = re.search(pat, login_html)
    if m:
        form_key = m.group(1)
        break
if not form_key:                       # Magento also ships it as a cookie
    for c in cj:
        if c.name == "form_key":
            form_key = urllib.parse.unquote(c.value)
            break
print("form_key:", form_key or "NOT FOUND")
if not form_key:
    sys.exit("cannot proceed without form_key")

data = urllib.parse.urlencode({
    "form_key": form_key,
    "login[username]": USER,
    "login[password]": PW,
}).encode()
req = urllib.request.Request(B + "/customer/account/loginPost/", data=data,
                             headers={"Referer": B + "/customer/account/login/",
                                      "Content-Type": "application/x-www-form-urlencoded"})
r = op.open(req, timeout=30)
print("login ->", r.geturl())

acct = op.open(B + "/customer/account/", timeout=30).read().decode("utf8", "replace")
print("logged in:", "customer/account/logout" in acct)

wl = op.open(B + "/wishlist/", timeout=30).read().decode("utf8", "replace")
names = re.findall(r'product-item-link"[^>]*>\s*([^<]+?)\s*</a>', wl)
if not names:
    names = re.findall(r'class="product-item-name"[^>]*>\s*<a[^>]*>\s*([^<]+?)\s*</a>', wl)
print(f"\n心愿单条目 ({len(names)}):")
for n in names:
    print("   -", n.strip()[:78])

target = "Hawaiian Bamboo Orchid Roots"
print(f"\n目标商品在心愿单里: {any(target in n for n in names)}")
print("页面含 product id 22787:", "22787" in wl)
qty = re.findall(r'name="qty\[(\d+)\]"[^>]*value="([^"]*)"', wl)
if qty:
    print("各条目数量 (itemId, qty):", qty)
