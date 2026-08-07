# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --param ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = []
    argv = sys.argv[1:]
    # A single positional, non-flag argument is a taskspec.json path -> original behaviour,
    # sys.argv left untouched. This is the path replay uses, so it must not change.
    if len(argv) == 1 and not argv[0].startswith("-"):
        return
    ap = argparse.ArgumentParser(
        prog="skill.py",
        description="Run this skill directly. Pass --flags, or a taskspec.json path.")
    for _p in _PARAMS:
        ap.add_argument("--" + _p.replace("_", "-"), dest=_p, default=None)
    ap.add_argument("taskspec", nargs="?", help="path to a taskspec.json (instead of --flags)")
    a = ap.parse_args(argv)
    # A taskspec path given alongside/without flags -> honour it, stay untouched.
    if a.taskspec and not any(getattr(a, _p) is not None for _p in _PARAMS):
        sys.argv = [sys.argv[0], a.taskspec]
        return
    params = {_p: getattr(a, _p) for _p in _PARAMS if getattr(a, _p) is not None}
    if not params:
        ap.print_help()
        ex = " ".join("--" + _p.replace("_", "-") + " <" + _p + ">" for _p in _PARAMS)
        print("\n  example:  python skill.py " + ex)
        print("  or:       python skill.py taskspec.json  "
              '(taskspec = {"params": {' + ", ".join('"' + _p + '": ...' for _p in _PARAMS)
              + "}})")
        raise SystemExit(0)
    spec = {"params": params}
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(spec, f)
    f.close()
    sys.argv = [sys.argv[0], f.name]
_skillfactory_cli()
# --- end CLI entry shim ---------------------------------------------------------------------

import json
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


PHONE_REGEX = re.compile(
    r"(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})"
)


def get_workspace_dir() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", os.getcwd())).resolve()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_taskspec(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def append_log(log_path: Path, message: str) -> None:
    with log_path.open("a", encoding="utf-8") as f:
        f.write(message.rstrip() + "\n")


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_phone(phone: str) -> str:
    return normalize_whitespace(phone)


def make_session(credentials: Optional[Dict[str, Any]] = None) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; CustomerServicePhoneSkill/1.0)"
        }
    )
    if credentials:
        if "headers" in credentials and isinstance(credentials["headers"], dict):
            session.headers.update(credentials["headers"])
        if "cookies" in credentials and isinstance(credentials["cookies"], dict):
            session.cookies.update(credentials["cookies"])
    return session


def fetch_page(session: requests.Session, url: str, timeout: int = 20) -> Optional[str]:
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype and "<html" not in resp.text.lower():
        return None
    return resp.text


def parse_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def extract_visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return normalize_whitespace(soup.get_text(" "))


def extract_phone_candidates_from_text(text: str) -> List[str]:
    return [normalize_phone(m.group(0)) for m in PHONE_REGEX.finditer(text or "")]


def find_contact_links(
    soup: BeautifulSoup,
    current_url: str,
    keywords: Optional[List[str]] = None,
) -> List[str]:
    if keywords is None:
        keywords = [
            "contact",
            "contact us",
            "customer service",
            "help",
            "support",
            "customer support",
            "service",
        ]

    found: List[Tuple[int, str]] = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        text = normalize_whitespace(a.get_text(" "))
        aria = normalize_whitespace(a.get("aria-label", ""))
        title = normalize_whitespace(a.get("title", ""))
        combined = f"{text} {aria} {title} {href}".lower()

        score = 0
        for kw in keywords:
            if kw in combined:
                score += len(kw)

        if score <= 0:
            continue

        abs_url = urljoin(current_url, href)
        if abs_url in seen:
            continue
        seen.add(abs_url)
        found.append((score, abs_url))

    found.sort(key=lambda x: x[0], reverse=True)
    return [u for _, u in found]


def same_site(url1: str, url2: str) -> bool:
    p1 = urlparse(url1)
    p2 = urlparse(url2)
    return (p1.scheme, p1.netloc) == (p2.scheme, p2.netloc)


def search_phone_number(
    session: requests.Session,
    start_url: str,
    log_path: Path,
    max_pages: int = 8,
) -> Optional[str]:
    visited = set()
    queue: List[str] = [start_url]

    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        append_log(log_path, f"Visiting: {url}")

        try:
            html = fetch_page(session, url)
        except Exception as e:
            append_log(log_path, f"Fetch failed for {url}: {e}")
            continue

        if not html:
            append_log(log_path, f"Non-HTML or empty response at: {url}")
            continue

        soup = parse_html(html)
        text = extract_visible_text(soup)
        phones = extract_phone_candidates_from_text(text)
        if phones:
            append_log(log_path, f"Found phone candidate on {url}: {phones[0]}")
            return phones[0]

        for link in find_contact_links(soup, url):
            if same_site(start_url, link) and link not in visited and link not in queue:
                queue.append(link)

        append_log(log_path, f"No phone found on {url}; queued {len(queue)} pages total.")

    return None


def build_output(phone: Optional[str]) -> Dict[str, Any]:
    return {"customer_service_phone_number": phone}


def validate_output_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("retrieved_data must be an object")
    if set(data.keys()) != {"customer_service_phone_number"}:
        raise ValueError("retrieved_data must contain exactly 'customer_service_phone_number'")
    value = data["customer_service_phone_number"]
    if value is not None and not isinstance(value, str):
        raise ValueError("'customer_service_phone_number' must be string or null")
    return data


def main() -> int:
    workspace = ensure_dir(get_workspace_dir())
    logs_dir = ensure_dir(workspace / "logs")
    artifacts_dir = ensure_dir(workspace / "artifacts")
    log_path = logs_dir / "skill.log"
    append_log(log_path, "Starting customer service phone retrieval skill.")

    agent_response_path = workspace / "agent_response.json"

    try:
        taskspec_path = sys.argv[1]
        taskspec = read_taskspec(taskspec_path)
        start_url = taskspec.get("start_url")
        credentials = taskspec.get("credentials") or {}

        if not start_url or not isinstance(start_url, str):
            raise ValueError("taskspec.start_url must be a non-empty string")

        append_log(log_path, f"Start URL: {start_url}")

        session = make_session(credentials)

        phone = search_phone_number(
            session=session,
            start_url=start_url,
            log_path=log_path,
            max_pages=int(taskspec.get("params", {}).get("max_pages", 8)),
        )

        retrieved_data = validate_output_schema(build_output(phone))
        write_json(agent_response_path, {"retrieved_data": retrieved_data})

        evidence = {
            "start_url": start_url,
            "phone_found": phone,
        }
        write_json(artifacts_dir / "evidence.json", evidence)

        append_log(log_path, f"Completed. customer_service_phone_number={phone!r}")
        return 0

    except Exception as e:
        append_log(log_path, f"ERROR: {e}")
        append_log(log_path, traceback.format_exc())
        retrieved_data = validate_output_schema(build_output(None))
        write_json(agent_response_path, {"retrieved_data": retrieved_data})
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
