import re
from urllib.parse import urlencode


REVIEW_ROW_RE = re.compile(r'/admin/review/product/edit/id/(\d+)/', re.I)
TD_RE = re.compile(r'<td\b[^>]*>(.*?)</td>', re.I | re.S)
TR_RE = re.compile(r'<tr\b[^>]*>(.*?)</tr>', re.I | re.S)
TAG_RE = re.compile(r'<[^>]+>')


def _strip_html(text: str) -> str:
    text = TAG_RE.sub(' ', text)
    text = text.replace('&nbsp;', ' ')
    return ' '.join(text.split())


def _extract_rows(html: str):
    rows = []
    for block in TR_RE.findall(html):
        rid_match = REVIEW_ROW_RE.search(block)
        if not rid_match:
            continue
        cells = [_strip_html(x) for x in TD_RE.findall(block)]
        rows.append({
            'review_id': rid_match.group(1),
            'cells': cells,
            'row_text': _strip_html(block),
            'title': cells[4] if len(cells) > 4 else None,
        })
    return rows


def fetch_review_grid_rows(opener, review_grid_url: str, product_name: str = None, product_filter_param: str = 'name'):
    url = review_grid_url
    if product_name:
        sep = '&' if '?' in review_grid_url else '?'
        url = review_grid_url + sep + urlencode({product_filter_param: product_name})
    html = opener.open(url, timeout=30).read().decode('utf-8', 'ignore')
    rows = _extract_rows(html)
    if product_name:
        lowered = product_name.lower()
        rows = [r for r in rows if lowered in r['row_text'].lower()]
    return {
        'url': url,
        'rows': rows,
        'row_count': len(rows),
        'html': html,
    }
