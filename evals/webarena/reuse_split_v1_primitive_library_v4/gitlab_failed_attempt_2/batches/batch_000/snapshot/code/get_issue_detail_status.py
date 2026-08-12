def get_issue_detail_status(self, issue_url: str) -> dict:
    self.page.goto(issue_url, wait_until="domcontentloaded")
    self.page.wait_for_timeout(2500)
    issue_text = self.page.locator("body").inner_text()

    is_closed = "\nClosed\n" in ("\n" + issue_text + "\n") or "Reopen issue" in issue_text
    is_open = "\nOpen\n" in ("\n" + issue_text + "\n") or "Close issue" in issue_text

    if is_closed:
        status = "closed"
    elif is_open:
        status = "open"
    else:
        status = "unknown"

    return {
        "issue_url": self.page.url,
        "status": status,
    }
