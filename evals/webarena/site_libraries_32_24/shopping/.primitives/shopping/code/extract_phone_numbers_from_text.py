import re
from typing import List

_PHONE_PATTERN = re.compile(
    r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})"
)


def _normalize_phone(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def extract_phone_numbers_from_text(text: str) -> List[str]:
    if not text:
        return []
    matches = [_normalize_phone(m.group(0)) for m in _PHONE_PATTERN.finditer(text)]
    seen = set()
    ordered = []
    for phone in matches:
        if phone not in seen:
            seen.add(phone)
            ordered.append(phone)
    return ordered
