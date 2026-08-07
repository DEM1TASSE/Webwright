import re
from html.parser import HTMLParser
from typing import Dict, List, Optional


class _ProductCardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_product = False
        self.product_depth = 0
        self.capture_name = False
        self.capture_price = False
        self.current_name_parts: List[str] = []
        self.current_price_parts: List[str] = []
        self.current: Dict[str, str] = {}
        self.items: List[Dict[str, object]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "")
        class_tokens = set(classes.split()) if classes else set()

        if tag == "li" and "product-item" in class_tokens and not self.in_product:
            self.in_product = True
            self.product_depth = 1
            self.current = {}
            self.current_name_parts = []
            self.current_price_parts = []
            return

        if self.in_product:
            self.product_depth += 1
            if "product-item-link" in class_tokens:
                self.capture_name = True
            if "price" in class_tokens:
                self.capture_price = True

    def handle_endtag(self, tag: str) -> None:
        if self.capture_name and tag == "a":
            self.capture_name = False
            name = _collapse("".join(self.current_name_parts))
            if name:
                self.current["name"] = name
            self.current_name_parts = []

        if self.capture_price and tag in {"span", "div"}:
            self.capture_price = False
            price_text = _collapse("".join(self.current_price_parts))
            if price_text and "price_text" not in self.current:
                self.current["price_text"] = price_text
            self.current_price_parts = []

        if self.in_product:
            self.product_depth -= 1
            if self.product_depth <= 0:
                parsed = _finalize_product(self.current)
                if parsed is not None:
                    self.items.append(parsed)
                self.in_product = False
                self.product_depth = 0
                self.current = {}

    def handle_data(self, data: str) -> None:
        if self.capture_name:
            self.current_name_parts.append(data)
        if self.capture_price:
            self.current_price_parts.append(data)


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _parse_price(text: str) -> Optional[float]:
    match = re.search(r"\$\s*([\d,]+(?:\.\d{2})?)", text)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _finalize_product(raw: Dict[str, str]) -> Optional[Dict[str, object]]:
    name = raw.get("name", "").strip()
    price_text = raw.get("price_text", "").strip()
    if not name:
        return None
    price = _parse_price(price_text) if price_text else None
    return {
        "name": name,
        "price": price,
        "price_text": price_text or None,
    }


def parse_search_result_product_cards(html: str) -> List[Dict[str, object]]:
    parser = _ProductCardParser()
    parser.feed(html or "")
    return parser.items
