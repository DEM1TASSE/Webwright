def get_user_follower_count_from_profile_page(self, profile_url: str) -> dict:
    import re

    if not isinstance(profile_url, str) or not profile_url.strip():
        raise ValueError("profile_url must be a non-empty string")

    response = self.page.goto(profile_url, wait_until="networkidle")
    if response is not None and response.status >= 400:
        raise RuntimeError(f"Failed to load profile page: HTTP {response.status}")

    follower_link = self.page.locator('a[href$="/followers"]').first
    follower_text = follower_link.inner_text().strip()
    match = re.search(r'(\d+)\s+followers?', follower_text)
    if not match:
        raise RuntimeError(f"Could not parse follower count from text: {follower_text!r}")

    follower_count = int(match.group(1))
    return {
        "follower_count": follower_count,
        "followers_link_text": follower_text,
    }
