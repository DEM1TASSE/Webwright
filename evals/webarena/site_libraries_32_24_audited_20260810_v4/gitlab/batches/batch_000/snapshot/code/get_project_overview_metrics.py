def get_project_overview_metrics(self, project_url: str) -> dict:
    import re

    self.page.goto(project_url, wait_until="domcontentloaded")
    body = self.page.locator("body").inner_text()

    id_match = re.search(r"Project ID:\s*(\d+)", body)
    star_match = re.search(r"\bStar\s*(\d+)\b", body)

    return {
        "project_url": self.page.url,
        "project_id": int(id_match.group(1)) if id_match else None,
        "stars_count": int(star_match.group(1)) if star_match else None,
    }
