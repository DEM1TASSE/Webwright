def list_dashboard_issues_by_actor_and_state(self, base_url: str, filter_type: str, username: str, state: str, page_number: int | None = None) -> dict:
    from urllib.parse import urlencode

    if filter_type not in {"author_username", "assignee_username"}:
        raise ValueError("filter_type must be 'author_username' or 'assignee_username'")

    params = {filter_type: username, "state": state}
    if page_number is not None:
        params["page"] = str(page_number)

    url = base_url.rstrip("/") + "/dashboard/issues?" + urlencode(params)
    self.page.goto(url, wait_until="domcontentloaded")

    issues = self.page.locator("a").evaluate_all(
        """
        els => els
          .map(e => ({title:(e.innerText||'').trim(), web_url:e.href}))
          .filter(x => x.title && /\/issues\/\d+$/.test(x.web_url))
        """
    )

    next_href = self.page.locator('a[rel="next"], a').evaluate_all(
        """
        els => {
          const found = els.find(e => (e.getAttribute('rel') || '') === 'next' || (e.innerText || '').trim() === 'Next');
          return found ? found.href : '';
        }
        """
    )

    current_page_number = page_number if page_number is not None else 1
    next_page_number = current_page_number + 1 if next_href else None

    return {
        "issues": issues,
        "page_number": current_page_number,
        "next_page_number": next_page_number,
        "has_next_page": bool(next_href),
        "is_complete": not bool(next_href),
        "source_url": self.page.url,
    }
