async def extract_product_reviews_from_product_page(self, url: str) -> dict:
    await self.page.goto(url, wait_until="networkidle")
    await self.page.locator('#tab-label-reviews, #tab-label-reviews-title').first.click()
    await self.page.wait_for_timeout(2500)
    body_text = await self.page.locator('body').inner_text()
    reviews = self._parse_product_reviews_from_text(body_text)
    return {
        "product_url": self.page.url,
        "review_source": "product_reviews_tab_rendered_text",
        "reviews": reviews,
    }

def _normalize_review_text(self, value: str) -> str:
    import re
    return re.sub(r"\s+", " ", value).strip()

def _parse_product_reviews_from_text(self, raw_text: str) -> list:
    import re
    text = raw_text.replace("\r", "")
    pattern = re.compile(
        r"(?P<title>.+?)\nRating\s*\n(?P<rating>\d+)%\s*\n(?P<body>.*?)\nReview by (?P<name>.+?)\n\nPosted on (?P<date>.+?)(?=\n\n.+?\nRating\s*\n\d+%\s*\n|\Z)",
        re.S,
    )
    reviews = []
    for match in pattern.finditer(text):
        reviews.append({
            "title": self._normalize_review_text(match.group("title")),
            "rating_percent": int(self._normalize_review_text(match.group("rating"))),
            "body": self._normalize_review_text(match.group("body")),
            "reviewer_name": self._normalize_review_text(match.group("name")),
            "posted_date": self._normalize_review_text(match.group("date")),
        })
    return reviews
