def load_post_page(self, post_url: str):
    if not isinstance(post_url, str) or not post_url.strip():
        raise ValueError("post_url must be a non-empty string")

    post_url = post_url.strip()
    response = self.page.goto(post_url, wait_until="domcontentloaded")
    document_status = response.status if response else None
    final_url = self.page.url
    page_title = self.page.title()

    return {
        "requested_post_url": post_url,
        "final_url": final_url,
        "document_status": document_status,
        "page_title": page_title,
    }
