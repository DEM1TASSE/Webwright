def open_post_from_listing_by_title(self, link_title: str):
    if not isinstance(link_title, str) or not link_title.strip():
        raise ValueError("link_title must be a non-empty string")

    link_title = link_title.strip()
    source_url = self.page.url
    target = self.page.get_by_role("link", name=link_title).first
    if target.count() == 0:
        raise ValueError("No matching post link found on the current page")

    target.click()
    self.page.wait_for_load_state("domcontentloaded")

    return {
        "source_listing_url": source_url,
        "selected_link_title": link_title,
        "post_url": self.page.url,
    }
