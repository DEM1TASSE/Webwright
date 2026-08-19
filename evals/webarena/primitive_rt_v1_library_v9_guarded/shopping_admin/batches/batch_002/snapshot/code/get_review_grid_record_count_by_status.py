def get_review_grid_record_count_by_status(self, status: str) -> dict:
    import re

    if not isinstance(status, str) or not status.strip():
        raise ValueError("status must be a non-empty string")
    status = status.strip()

    review_url = "http://GCRSANDBOX410.redmond.corp.microsoft.com:7780/admin/review/product/index/"
    self.page.goto(review_url, wait_until="domcontentloaded")
    self.page.wait_for_load_state("networkidle")

    self.page.select_option("#reviewGrid_filter_status", label=status)
    self.page.get_by_role("button", name="Search").click()
    self.page.wait_for_load_state("networkidle")

    summary_texts = self.page.locator(".admin__data-grid-header .admin__control-support-text").all_inner_texts()
    summary_text = " | ".join(t.strip() for t in summary_texts if t and t.strip())
    body_text = self.page.locator("body").inner_text()

    match = re.search(r"(\d+)\s+records\s+found", summary_text, re.I)
    if not match:
        match = re.search(r"(\d+)\s+records\s+found", body_text, re.I)
    if not match:
        raise RuntimeError("Could not parse filtered review grid record count")

    return {
        "status": status,
        "record_count": int(match.group(1)),
        "summary_text": summary_text,
        "grid_url": self.page.url,
    }
