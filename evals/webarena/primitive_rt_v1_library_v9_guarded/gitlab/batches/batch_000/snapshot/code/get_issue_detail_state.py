def get_issue_detail_state(self, issue_url):
    import html
    import re

    response = self.page.goto(issue_url, wait_until="domcontentloaded")
    if response is None:
        raise RuntimeError("Failed to load issue detail page")

    final_url = self.page.url
    html_text = self.page.content()
    title_match = re.search(r"<title>(.*?)</title>", html_text, re.S | re.I)
    raw_title = html.unescape(title_match.group(1)).strip() if title_match else final_url
    issue_title = raw_title.split("(#")[0].strip() if "(#" in raw_title else raw_title
    visible_text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", html_text)).split())
    lowered = f" {visible_text.lower()} "
    is_closed = " closed " in lowered

    return {
        "issue_title": issue_title,
        "issue_url": final_url,
        "is_closed": is_closed,
    }