def get_issue_detail_state(self, issue_url: str) -> dict:
    import re

    self.page.goto(issue_url, wait_until="domcontentloaded")
    body = self.page.locator("body").inner_text()
    page_title = self.page.title()

    has_open_label = bool(re.search(r"\bOpen\b", body))
    has_close_issue_action = "Close issue" in body
    has_closed_label = bool(re.search(r"\bClosed\b", body))
    has_reopen_issue_action = "Reopen issue" in body

    if has_closed_label and has_reopen_issue_action:
        state = "closed"
    elif has_open_label and has_close_issue_action:
        state = "opened"
    else:
        state = "unknown"

    return {
        "web_url": self.page.url,
        "page_title": page_title,
        "state": state,
        "state_signals": {
            "has_open_label": has_open_label,
            "has_close_issue_action": has_close_issue_action,
            "has_closed_label": has_closed_label,
            "has_reopen_issue_action": has_reopen_issue_action,
        },
    }
