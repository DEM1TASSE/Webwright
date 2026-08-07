# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --phrase ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['phrase']
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
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from playwright.sync_api import sync_playwright, Page


WORKSPACE_DIR = Path(os.environ.get("WORKSPACE_DIR", os.getcwd()))
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)


def load_taskspec(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_output_shape(retrieved_data: Any, output_schema: Dict[str, Any]) -> None:
    if output_schema.get("type") != "array":
        raise ValueError("Only array output_schema is supported by this skill.")
    if not isinstance(retrieved_data, list):
        raise ValueError("retrieved_data must be a list.")
    item_type = output_schema.get("items", {}).get("type")
    if item_type == "string":
        if not all(isinstance(x, str) for x in retrieved_data):
            raise ValueError("retrieved_data items must be strings.")
    else:
        raise ValueError("Only array-of-string output_schema is supported by this skill.")


class RunContext:
    def __init__(self) -> None:
        self.run_dir = self._next_run_dir()
        self.shots_dir = self.run_dir / "screenshots"
        self.shots_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.run_dir / "final_script_log.txt"
        self.step = 1
        self._write_log("Run started")

    def _next_run_dir(self) -> Path:
        final_runs = WORKSPACE_DIR / "final_runs"
        final_runs.mkdir(parents=True, exist_ok=True)
        nums = []
        for p in final_runs.iterdir():
            m = re.fullmatch(r"run_(\d+)", p.name)
            if m:
                nums.append(int(m.group(1)))
        nxt = (max(nums) + 1) if nums else 1
        run_dir = final_runs / f"run_{nxt:03d}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _write_log(self, msg: str) -> None:
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

    def log(self, msg: str) -> None:
        print(msg)
        self._write_log(msg)

    def snap(self, page: Page, name: str) -> None:
        page.screenshot(path=str(self.shots_dir / f"final_execution_{self.step}_{name}.png"), full_page=True)

    def next_step(self) -> None:
        self.step += 1


def normalize_base_url(start_url: str) -> str:
    m = re.match(r"^(https?://[^/]+)", start_url)
    if not m:
        raise ValueError(f"Could not derive base URL from start_url: {start_url}")
    return m.group(1)


def get_credentials(taskspec: Dict[str, Any]) -> Tuple[str, str]:
    creds = taskspec.get("credentials") or {}
    username = (
        creds.get("username")
        or creds.get("login")
        or creds.get("user")
        or creds.get("email")
    )
    password = creds.get("password")
    if not username or not password:
        raise ValueError("Missing credentials.username/login and/or credentials.password")
    return username, password


def login(page: Page, base_url: str, username: str, password: str, rc: RunContext) -> None:
    login_url = f"{base_url}/users/sign_in"
    rc.log(f"step {rc.step} action: open login page {login_url}")
    page.goto(login_url, wait_until="domcontentloaded")
    page.locator('input[name="user[login]"]').fill(username)
    page.locator('input[name="user[password]"]').fill(password)
    page.get_by_role("button", name=re.compile("sign in", re.I)).click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1200)
    rc.snap(page, "login_success")
    rc.log(f"logged in as {username}; landed at {page.url}")
    rc.next_step()


def build_issue_list_urls(base_url: str, username: str) -> List[str]:
    return [
        f"{base_url}/dashboard/issues?author_username={username}&state=all",
        f"{base_url}/dashboard/issues?assignee_username={username}&state=all",
    ]


def extract_issue_links(page: Page) -> List[Dict[str, str]]:
    links = page.locator("a").evaluate_all(
        """els => els
            .map(e => ({text: (e.innerText || '').trim(), href: e.href || ''}))
            .filter(x => x.text && /\\/issues\\/\\d+$/.test(x.href))
        """
    )
    dedup = []
    seen = set()
    for item in links:
        href = item.get("href", "")
        if href and href not in seen:
            seen.add(href)
            dedup.append({"title": item.get("text", "").strip(), "href": href})
    return dedup


def extract_next_page_url(page: Page) -> Optional[str]:
    href = page.locator("a[rel='next'], a").evaluate_all(
        """els => {
            const found = els.find(e =>
                (e.getAttribute('rel') || '') === 'next' ||
                ((e.innerText || '').trim() === 'Next')
            );
            return found ? found.href : '';
        }"""
    )
    return href or None


def paginate_issue_lists(
    page: Page,
    start_urls: List[str],
    phrase: str,
    rc: RunContext,
) -> List[Dict[str, str]]:
    visited: Set[str] = set()
    matches: List[Dict[str, str]] = []
    phrase_lc = phrase.lower()

    for start_url in start_urls:
        url = start_url
        while url and url not in visited:
            visited.add(url)
            rc.log(f"step {rc.step} action: open issues list {url}")
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(1200)

            issue_links = extract_issue_links(page)
            page_matches = [x for x in issue_links if phrase_lc in x["title"].lower()]

            if page_matches:
                rc.log(
                    "found matching issue title(s): "
                    + " | ".join(f"{m['title']} -> {m['href']}" for m in page_matches)
                )
                rc.snap(page, "matching_issue_list")
                for m in page_matches:
                    matches.append(m)

            next_url = extract_next_page_url(page)
            if next_url == page.url:
                break
            url = next_url

    dedup: List[Dict[str, str]] = []
    seen_hrefs: Set[str] = set()
    for m in matches:
        if m["href"] not in seen_hrefs:
            seen_hrefs.add(m["href"])
            dedup.append(m)
    rc.next_step()
    return dedup


def parse_issue_iid_from_href(href: str) -> Optional[int]:
    m = re.search(r"/issues/(\d+)$", href)
    return int(m.group(1)) if m else None


def choose_latest_updated_match(matches: List[Dict[str, str]]) -> Dict[str, str]:
    if not matches:
        raise ValueError("No matching issues found")
    with_iid = []
    for m in matches:
        iid = parse_issue_iid_from_href(m["href"])
        with_iid.append((iid if iid is not None else -1, m))
    with_iid.sort(key=lambda t: t[0], reverse=True)
    return with_iid[0][1]


def extract_issue_closed_state(page: Page) -> bool:
    body = page.locator("body").inner_text()
    is_open = bool(re.search(r"\bOpen\b", body)) and ("Close issue" in body)
    is_closed = bool(re.search(r"\bClosed\b", body)) and ("Reopen issue" in body)
    if is_closed:
        return True
    if is_open:
        return False
    if re.search(r"\bClosed\b", body):
        return True
    if re.search(r"\bOpen\b", body):
        return False
    raise ValueError("Could not determine issue state from page content")


def open_issue_and_get_closed_state(page: Page, issue: Dict[str, str], rc: RunContext) -> bool:
    rc.log(f"step {rc.step} action: open issue detail {issue['href']}")
    page.goto(issue["href"], wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    rc.snap(page, "issue_detail_state")
    closed = extract_issue_closed_state(page)
    rc.log(f"issue title={issue['title']}; closed={closed}")
    rc.next_step()
    return closed


def write_response(status: str, retrieved_data: Optional[List[str]], error_details: Optional[str]) -> None:
    response = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    with open(WORKSPACE_DIR / "agent_response.json", "w", encoding="utf-8") as f:
        json.dump(response, f)


def run(taskspec_path: str) -> None:
    taskspec = load_taskspec(taskspec_path)
    params = taskspec.get("params", {})
    phrase = params.get("phrase")
    if not phrase:
        raise ValueError("params.phrase is required")

    output_schema = taskspec.get("output_schema", {})
    start_url = taskspec.get("start_url") or ""
    base_url = normalize_base_url(start_url)
    username, password = get_credentials(taskspec)

    rc = RunContext()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 1800})
        page = context.new_page()

        try:
            login(page, base_url, username, password, rc)

            issue_list_urls = build_issue_list_urls(base_url, username)
            matches = paginate_issue_lists(page, issue_list_urls, phrase, rc)

            if not matches:
                rc.log(f'No issue found with phrase "{phrase}" in title.')
                write_response("NOT_FOUND_ERROR", None, None)
                browser.close()
                return

            target = choose_latest_updated_match(matches)
            rc.log(
                f"selected latest-updated candidate by highest visible issue id: "
                f"{target['title']} -> {target['href']}"
            )

            closed = open_issue_and_get_closed_state(page, target, rc)

            # output_schema requires array of strings, so serialize boolean as lowercase string
            retrieved_data = ["true" if closed else "false"]
            ensure_output_shape(retrieved_data, output_schema)
            write_response("SUCCESS", retrieved_data, None)
            rc.log(f"step {rc.step} action: wrote agent_response.json with {retrieved_data}")
            rc.snap(page, "final_confirmation")

        except Exception as e:
            rc.log(f"ERROR: {type(e).__name__}: {e}")
            write_response("ERROR", None, str(e))
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    run(sys.argv[1])
