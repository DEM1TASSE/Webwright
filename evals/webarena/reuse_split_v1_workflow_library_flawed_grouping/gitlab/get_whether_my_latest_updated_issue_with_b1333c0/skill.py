# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --title-substring ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['title_substring']
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
import textwrap
import struct
import zlib
import urllib.parse
import urllib.request
import urllib.error
import http.cookiejar
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", os.getcwd()))
RUN_DIR = WORKSPACE / "final_runs" / "run_1"
SCREENSHOTS_DIR = RUN_DIR / "screenshots"
LOG_PATH = RUN_DIR / "final_script_log.txt"
AGENT_RESPONSE_PATH = WORKSPACE / "agent_response.json"


def ensure_dirs() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("", encoding="utf-8")


def log(msg: str) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)


def write_text_screenshot(path: Path, text: str) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore

        img = Image.new("RGB", (1400, 1800), "white")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        except Exception:
            font = ImageFont.load_default()

        y = 20
        for para in text.split("\n"):
            for line in textwrap.wrap(para, width=100) or [""]:
                draw.text((20, y), line, fill="black", font=font)
                y += 30
                if y > 1760:
                    break
            if y > 1760:
                break
            y += 8
        img.save(path)
        return
    except Exception:
        pass

    def png_chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack("!I", len(data))
            + tag
            + data
            + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    width, height = 20, 20
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(raw, 9))
        + png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def write_response(status: str, retrieved_data: Optional[List[Any]], error_details: Any = None) -> None:
    payload = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    AGENT_RESPONSE_PATH.write_text(json.dumps(payload), encoding="utf-8")
    log("final_response: " + json.dumps(payload))
    write_text_screenshot(
        SCREENSHOTS_DIR / "final_response.png",
        json.dumps(payload, ensure_ascii=False, indent=2),
    )


def get_base_url(taskspec: Dict[str, Any]) -> str:
    start_url = taskspec.get("start_url") or ""
    if start_url:
        parsed = urllib.parse.urlparse(start_url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:8023"


def get_credentials(taskspec: Dict[str, Any]) -> Dict[str, str]:
    creds = taskspec.get("credentials") or {}
    username = (
        creds.get("username")
        or creds.get("login")
        or creds.get("user")
        or creds.get("email")
    )
    password = creds.get("password") or creds.get("pass")
    if not username or not password:
        raise RuntimeError("Missing credentials.username/login and/or credentials.password in taskspec")
    return {"username": username, "password": password}


def title_matches(title: str, substring: str) -> bool:
    return substring.lower() in title.lower()


def parse_link_header(link_header: str) -> Dict[str, str]:
    links: Dict[str, str] = {}
    for part in link_header.split(","):
        m = re.search(r'<([^>]+)>;\s*rel="([^"]+)"', part.strip())
        if m:
            links[m.group(2)] = m.group(1)
    return links


class SimpleHttpClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        self.default_headers = {
            "User-Agent": "Mozilla/5.0 skill-client",
            "Accept": "*/*",
        }

    def _request(
        self,
        method: str,
        url: str,
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Dict[str, str], bytes, str]:
        req = urllib.request.Request(url=url, data=data, method=method)
        merged_headers = dict(self.default_headers)
        if headers:
            merged_headers.update(headers)
        for k, v in merged_headers.items():
            req.add_header(k, v)
        try:
            with self.opener.open(req, timeout=60) as resp:
                body = resp.read()
                final_url = resp.geturl()
                headers_dict = {k: v for k, v in resp.headers.items()}
                return resp.getcode(), headers_dict, body, final_url
        except urllib.error.HTTPError as e:
            body = e.read()
            headers_dict = {k: v for k, v in e.headers.items()}
            return e.code, headers_dict, body, e.geturl()

    def get(self, path_or_url: str, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Dict[str, str], bytes, str]:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            url = path_or_url
        else:
            url = self.base_url + path_or_url
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            sep = "&" if "?" in url else "?"
            url = url + sep + query
        return self._request("GET", url)

    def post_form(self, path_or_url: str, form: Dict[str, Any]) -> Tuple[int, Dict[str, str], bytes, str]:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            url = path_or_url
        else:
            url = self.base_url + path_or_url
        data = urllib.parse.urlencode(form).encode("utf-8")
        return self._request(
            "POST",
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )


class GitLabClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.http = SimpleHttpClient(self.base_url)

    def login(self) -> None:
        status, headers, body, final_url = self.http.get("/users/sign_in")
        if status >= 400:
            raise RuntimeError(f"Failed to load sign-in page: HTTP {status}")
        html = body.decode("utf-8", errors="replace")
        m = re.search(r'name="authenticity_token"\s+value="([^"]+)"', html)
        if not m:
            raise RuntimeError("Could not find authenticity token on sign-in page")

        status, headers, body, final_url = self.http.post_form(
            "/users/sign_in",
            {
                "authenticity_token": m.group(1),
                "user[login]": self.username,
                "user[password]": self.password,
                "user[remember_me]": "0",
            },
        )
        text = body.decode("utf-8", errors="replace")
        if status >= 400:
            raise RuntimeError(f"Login POST failed: HTTP {status}")
        if "/users/sign_in" in final_url and "Sign in" in text:
            raise RuntimeError("Login failed")

        log(f"logged in successfully as {self.username}")
        write_text_screenshot(
            SCREENSHOTS_DIR / "step_1_login.png",
            f"Logged in to {self.base_url} as {self.username}\nFinal URL: {final_url}",
        )

    def api_get_json(
        self,
        path_or_url: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, Dict[str, str], str]:
        status, headers, body, final_url = self.http.get(path_or_url, params=params)
        if status >= 400:
            raise RuntimeError(f"GET {path_or_url} failed: HTTP {status}")
        text = body.decode("utf-8", errors="replace")
        try:
            return json.loads(text), headers, final_url
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Non-JSON response from {path_or_url}: {e}") from e

    def iter_paginated(self, path: str, params: Optional[Dict[str, Any]] = None) -> List[Any]:
        current_url: Optional[str] = None
        current_path = path
        current_params = dict(params or {})
        items: List[Any] = []
        page_num = 0
        expected_total: Optional[int] = None

        while True:
            page_num += 1
            if current_url:
                data, headers, _ = self.api_get_json(current_url, params=None)
            else:
                data, headers, _ = self.api_get_json(current_path, params=current_params)

            if not isinstance(data, list):
                raise RuntimeError(f"Expected list from paginated endpoint {path}, got {type(data).__name__}")
            items.extend(data)

            if expected_total is None:
                total_header = headers.get("X-Total")
                if total_header and str(total_header).isdigit():
                    expected_total = int(total_header)
                    log(f"pagination evidence for {path}: expected total={expected_total}")

            next_url = None
            link_header = headers.get("Link", "")
            if link_header:
                next_url = parse_link_header(link_header).get("next")

            if not next_url:
                x_next = headers.get("X-Next-Page")
                if x_next:
                    if current_url:
                        parsed = urllib.parse.urlparse(current_url)
                        q = dict(urllib.parse.parse_qsl(parsed.query))
                        q["page"] = x_next
                        next_url = urllib.parse.urlunparse(
                            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, urllib.parse.urlencode(q), parsed.fragment)
                        )
                    else:
                        current_params["page"] = x_next

            if not next_url and not headers.get("X-Next-Page"):
                break

            if next_url:
                current_url = next_url
            else:
                current_url = None

        if expected_total is not None and len(items) != expected_total:
            log(f"warning: fetched {len(items)} items but header total was {expected_total} for {path}")
        return items

    def list_accessible_projects(self) -> List[Dict[str, Any]]:
        projects = self.iter_paginated(
            "/api/v4/projects",
            params={"membership": "true", "simple": "true", "per_page": 100},
        )
        log(f"fetched accessible projects: {len(projects)}")
        return projects

    def list_project_issues(self, project_id: int) -> List[Dict[str, Any]]:
        return self.iter_paginated(
            f"/api/v4/projects/{project_id}/issues",
            params={
                "scope": "all",
                "per_page": 100,
                "order_by": "updated_at",
                "sort": "desc",
            },
        )

    def get_issue_detail(self, project_path: str, iid: Any) -> Dict[str, Any]:
        encoded = urllib.parse.quote(project_path, safe="")
        data, _, _ = self.api_get_json(f"/api/v4/projects/{encoded}/issues/{iid}")
        if not isinstance(data, dict):
            raise RuntimeError("Issue detail response was not an object")
        return data


def find_latest_matching_issue(client: GitLabClient, title_substring: str) -> Optional[Dict[str, Any]]:
    projects = client.list_accessible_projects()
    matches: List[Dict[str, Any]] = []

    for idx, project in enumerate(projects, start=1):
        pid = project.get("id")
        if pid is None:
            continue
        project_path = project.get("path_with_namespace") or str(pid)
        try:
            issues = client.list_project_issues(int(pid))
        except Exception as e:
            log(f"warning: failed to fetch issues for project {project_path}: {e!r}")
            continue

        for issue in issues:
            title = issue.get("title", "") or ""
            if title_matches(title, title_substring):
                matches.append(
                    {
                        "project_id": pid,
                        "project": project_path,
                        "iid": issue.get("iid"),
                        "title": title,
                        "state": issue.get("state"),
                        "updated_at": issue.get("updated_at"),
                        "web_url": issue.get("web_url"),
                    }
                )

        if idx % 10 == 0 or idx == len(projects):
            log(f"scanned {idx}/{len(projects)} projects; current matches={len(matches)}")

    matches.sort(key=lambda x: x.get("updated_at") or "", reverse=True)

    write_text_screenshot(
        SCREENSHOTS_DIR / "step_2_matching_issues.png",
        "Matching issues sorted by updated_at desc:\n"
        + (
            "\n".join(json.dumps(m, ensure_ascii=False) for m in matches[:100])
            if matches
            else f"No matching issues found for substring: {title_substring!r}"
        ),
    )
    log(f"total matching issues for substring {title_substring!r}: {len(matches)}")
    return matches[0] if matches else None


def verify_issue_state(client: GitLabClient, candidate: Dict[str, Any], title_substring: str) -> bool:
    detail = client.get_issue_detail(candidate["project"], candidate["iid"])
    title = detail.get("title", candidate.get("title", ""))
    if not title_matches(title, title_substring):
        raise RuntimeError(
            f"Verification failed: selected issue title {title!r} no longer matches substring {title_substring!r}"
        )

    state = detail.get("state", candidate.get("state"))
    if state not in ("opened", "closed"):
        raise RuntimeError(f"Unexpected issue state: {state!r}")

    write_text_screenshot(
        SCREENSHOTS_DIR / "step_3_issue_detail.png",
        json.dumps(
            {
                "project": candidate["project"],
                "iid": candidate["iid"],
                "title": title,
                "state": state,
                "updated_at": detail.get("updated_at"),
                "web_url": detail.get("web_url"),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    log(f"verified issue detail: project={candidate['project']} iid={candidate['iid']} state={state}")
    return state == "closed"


def main() -> None:
    ensure_dirs()
    taskspec_path = Path(sys.argv[1])
    taskspec = json.loads(taskspec_path.read_text(encoding="utf-8"))

    params = taskspec.get("params") or {}
    title_substring = params.get("title_substring")
    if not isinstance(title_substring, str) or not title_substring.strip():
        raise RuntimeError("taskspec.params.title_substring must be a non-empty string")
    title_substring = title_substring.strip()

    creds = get_credentials(taskspec)
    base_url = get_base_url(taskspec)

    log(f"starting task for title_substring={title_substring!r} against base_url={base_url}")

    client = GitLabClient(base_url, creds["username"], creds["password"])
    client.login()

    latest = find_latest_matching_issue(client, title_substring)
    if latest is None:
        write_response("NOT_FOUND_ERROR", None, None)
        return

    write_text_screenshot(
        SCREENSHOTS_DIR / "step_2b_selected_latest.png",
        "Selected latest updated matching issue:\n" + json.dumps(latest, ensure_ascii=False, indent=2),
    )
    log("selected latest matching issue: " + json.dumps(latest, ensure_ascii=False))

    is_closed = verify_issue_state(client, latest, title_substring)
    write_response("SUCCESS", [is_closed], None)


if __name__ == "__main__":
    ensure_dirs()
    try:
        main()
    except Exception as e:
        log(f"fatal_error: {e!r}")
        write_response("ERROR", None, str(e))
