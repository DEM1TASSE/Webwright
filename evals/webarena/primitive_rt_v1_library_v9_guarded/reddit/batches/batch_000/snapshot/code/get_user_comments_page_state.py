def get_user_comments_page_state(self, username: str):
    if not isinstance(username, str) or not username.strip():
        raise ValueError("username must be a non-empty string")

    username = username.strip()
    response = self.page.goto(f"/user/{username}/comments", wait_until="domcontentloaded")
    document_status = response.status if response else None
    body_text = self.page.locator("body").inner_text()

    empty_state_message = "There are no entries to display."
    is_explicitly_empty = empty_state_message in body_text

    return {
        "username": username,
        "comments_url": self.page.url,
        "document_status": document_status,
        "is_explicitly_empty": is_explicitly_empty,
        "empty_state_message": empty_state_message if is_explicitly_empty else None,
    }
