def get_issue_state_from_page(self, issue_url: str) -> dict:
    import re

    self.page.goto(issue_url, wait_until="domcontentloaded")
    self.page.wait_for_load_state("networkidle")
    body_text = self.page.locator("body").inner_text()

    state = None
    if re.search(r'(^|\n)\s*Closed\s*(\n|$)', body_text, re.I):
        state = "closed"
    elif re.search(r'(^|\n)\s*Open\s*(\n|$)', body_text, re.I):
        state = "open"

    if state is None:
        raise RuntimeError(f"Could not determine issue state from page: {issue_url}")

    return {
        "issue_url": issue_url,
        "state": state,
    }
