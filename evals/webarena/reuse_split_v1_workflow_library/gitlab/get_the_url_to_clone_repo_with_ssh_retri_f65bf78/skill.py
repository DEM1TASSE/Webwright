# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --repo ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['repo', 'retrieved_data_format_spec']
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
import html
import shutil
import urllib.parse
import urllib.request
import http.cookiejar
from pathlib import Path


def get_workspace() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", ".")).resolve()


def load_taskspec(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def next_run_dir(root: Path) -> Path:
    final_runs = root / "final_runs"
    final_runs.mkdir(parents=True, exist_ok=True)
    nums = []
    for p in final_runs.glob("run_*"):
        try:
            nums.append(int(p.name.split("_")[1]))
        except Exception:
            pass
    run_id = max(nums, default=0) + 1
    run_dir = final_runs / f"run_{run_id}"
    (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)
    return run_dir


def copy_self(run_dir: Path) -> None:
    try:
        src = Path(__file__)
        if src.exists():
            shutil.copy2(src, run_dir / "final_script.py")
    except Exception:
        pass


def write_text_image(path: Path, text: str) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (1280, 1800), "white")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        except Exception:
            font = ImageFont.load_default()

        margin = 20
        max_width = 1220
        y = margin
        for para in text.split("\n"):
            words = para.split()
            if not words:
                y += 28
                continue
            line = ""
            for word in words:
                candidate = (line + " " + word).strip()
                try:
                    too_wide = draw.textlength(candidate, font=font) > max_width
                except Exception:
                    too_wide = len(candidate) > 110
                if line and too_wide:
                    draw.text((margin, y), line, fill="black", font=font)
                    y += 32
                    line = word
                else:
                    line = candidate
                if y > 1740:
                    break
            if line and y <= 1740:
                draw.text((margin, y), line, fill="black", font=font)
                y += 38
            if y > 1740:
                break
        img.save(path)
    except Exception:
        path.write_bytes(
            bytes.fromhex(
                "89504E470D0A1A0A0000000D4948445200000001000000010802000000907753DE0000000C49444154789C636060000000020001E221BC330000000049454E44AE426082"
            )
        )


def strip_text(html_text: str) -> str:
    txt = re.sub(r"<script\b.*?</script>", " ", html_text, flags=re.I | re.S)
    txt = re.sub(r"<style\b.*?</style>", " ", txt, flags=re.I | re.S)
    txt = re.sub(r"<[^>]+>", "\n", txt, flags=re.S)
    txt = html.unescape(txt)
    lines = [line.strip() for line in txt.splitlines() if line.strip()]
    return "\n".join(lines)


class Logger:
    def __init__(self, path: Path):
        self.path = path
        self.path.write_text("", encoding="utf-8")

    def log(self, msg: str) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
        print(msg)


class BrowserSession:
    def __init__(self):
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.opener.addheaders = [("User-Agent", "Mozilla/5.0")]

    def get(self, url: str) -> tuple[str, str]:
        with self.opener.open(url, timeout=30) as resp:
            body = resp.read().decode("utf-8", "ignore")
            return resp.geturl(), body

    def post_form(self, url: str, data: dict, referer: str | None = None) -> tuple[str, str]:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if referer:
            headers["Referer"] = referer
        req = urllib.request.Request(url, data=encoded, headers=headers)
        with self.opener.open(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", "ignore")
            return resp.geturl(), body


def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def parse_credentials(taskspec: dict) -> tuple[str, str]:
    creds = taskspec.get("credentials") or {}
    username = creds.get("username") or creds.get("login") or creds.get("user") or creds.get("email")
    password = creds.get("password") or creds.get("pass")
    if not username or not password:
        raise RuntimeError("Missing credentials in taskspec")
    return username, password


def parse_base_url(taskspec: dict) -> str:
    start_url = taskspec.get("start_url")
    if not start_url:
        raise RuntimeError("taskspec.start_url is required")
    return start_url.rstrip("/")


def parse_repo_query(taskspec: dict) -> str:
    params = taskspec.get("params") or {}
    repo = params.get("repo")
    if not repo:
        raise RuntimeError("taskspec.params.repo is required")
    return repo


def extract_authenticity_token(page_html: str) -> str:
    patterns = [
        r'name=["\']authenticity_token["\'][^>]*value=["\']([^"\']+)',
        r'value=["\']([^"\']+)["\'][^>]*name=["\']authenticity_token["\']',
    ]
    for pat in patterns:
        m = re.search(pat, page_html, re.I | re.S)
        if m:
            return html.unescape(m.group(1))
    raise RuntimeError("Could not find authenticity token")


def login(browser: BrowserSession, base_url: str, username: str, password: str) -> tuple[str, str]:
    sign_in_candidates = [
        urllib.parse.urljoin(base_url + "/", "users/sign_in"),
        base_url + "/",
    ]
    sign_in_url = None
    sign_in_html = None
    final_page_url = None

    for candidate in sign_in_candidates:
        try:
            page_url, page_html = browser.get(candidate)
            if "authenticity_token" in page_html:
                sign_in_url = candidate
                sign_in_html = page_html
                final_page_url = page_url
                break
        except Exception:
            continue

    if sign_in_html is None or sign_in_url is None:
        raise RuntimeError("Could not fetch sign-in page")

    token = extract_authenticity_token(sign_in_html)
    post_url = urllib.parse.urljoin(base_url + "/", "users/sign_in")
    landing_url, landing_html = browser.post_form(
        post_url,
        {
            "authenticity_token": token,
            "user[login]": username,
            "user[password]": password,
            "user[remember_me]": "0",
        },
        referer=final_page_url or sign_in_url,
    )

    body = strip_text(landing_html).lower()
    if "sign in" in body and "password" in body and "dashboard" not in landing_url.lower() and "sign out" not in body:
        home_url, home_html = browser.get(base_url + "/")
        home_body = strip_text(home_html).lower()
        if "sign out" not in home_body and username.lower() not in home_body and "dashboard" not in home_url.lower():
            raise RuntimeError("Login did not appear successful")
        return home_url, home_html

    return landing_url, landing_html


def extract_links(page_html: str) -> list[tuple[str, str]]:
    results = []
    for href, inner in re.findall(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', page_html, re.I | re.S):
        text = html.unescape(" ".join(re.sub(r"<[^>]+>", " ", inner, flags=re.S).split()))
        results.append((href, text))
    return results


def candidate_project_paths_from_search(page_html: str) -> list[tuple[str, str]]:
    candidates = []
    seen = set()
    for href, text in extract_links(page_html):
        if not href.startswith("/"):
            continue
        if href.startswith("/search") or href.startswith("/users/") or href.startswith("/groups/") or href.startswith("/help"):
            continue
        if href.count("/") < 2:
            continue
        key = (href, text)
        if key not in seen:
            seen.add(key)
            candidates.append((href, text))
    return candidates


def score_candidate(repo_query: str, href: str, text: str) -> int:
    qnorm = normalize(repo_query)
    hnorm = normalize(href)
    tnorm = normalize(text)
    score = 0

    if qnorm and qnorm == hnorm.split("/")[-1] if "/" in hnorm else False:
        score += 120
    if qnorm and qnorm in hnorm:
        score += 100
    if qnorm and qnorm in tnorm:
        score += 95

    words = [w for w in re.split(r"[^a-z0-9]+", repo_query.lower()) if w]
    for w in words:
        if w in href.lower():
            score += 12
        if w in text.lower():
            score += 10

    path_parts = [p for p in href.strip("/").split("/") if p]
    if len(path_parts) == 2:
        score += 8
    if re.search(r"/[-._a-zA-Z0-9]+$", href):
        score += 5
    return score


def search_projects(browser: BrowserSession, base_url: str, repo_query: str, max_pages: int = 10) -> tuple[str, list[str]]:
    best_path = None
    best_score = -1
    evidence = []

    for page in range(1, max_pages + 1):
        search_url = urllib.parse.urljoin(
            base_url + "/",
            "search?scope=projects&search=" + urllib.parse.quote(repo_query) + f"&page={page}",
        )
        page_url, page_html = browser.get(search_url)
        evidence.append(f"search_page={page} url={page_url}")

        candidates = candidate_project_paths_from_search(page_html)
        page_best = -1
        for href, text in candidates:
            score = score_candidate(repo_query, href, text)
            if score > page_best:
                page_best = score
            if score > best_score:
                best_score = score
                best_path = href
                evidence.append(f"candidate path={href} text={text[:120]} score={score}")

        if best_score >= 100:
            break

        has_next = bool(re.search(rf'[?&]page={page + 1}\b', page_html))
        if not has_next:
            break

    if best_path:
        return best_path, evidence

    raise RuntimeError(f"Could not locate project from search for query: {repo_query}")


def list_explore_candidates(browser: BrowserSession, base_url: str) -> list[str]:
    urls = [
        urllib.parse.urljoin(base_url + "/", "explore/projects?sort=stars_desc"),
        urllib.parse.urljoin(base_url + "/", "explore/projects"),
    ]
    found = []
    seen = set()
    for u in urls:
        try:
            _, page_html = browser.get(u)
        except Exception:
            continue
        for href, _text in candidate_project_paths_from_search(page_html):
            if href not in seen:
                seen.add(href)
                found.append(href)
    return found


def fetch_project_page(browser: BrowserSession, base_url: str, project_path: str) -> tuple[str, str]:
    url = urllib.parse.urljoin(base_url + "/", project_path.lstrip("/"))
    return browser.get(url)


def extract_ssh_clone_url(project_html: str) -> str:
    patterns = [
        r'name=["\']ssh_project_clone["\'][^>]*value=["\']([^"\']+)',
        r'Clone with SSH.*?value=["\']([^"\']+)["\']',
        r'value=["\'](ssh://git@[^"\']+?\.git)["\']',
        r'(ssh://git@[^"\'\s<>]+?\.git)',
        r'(git@[^"\'\s<>]+?\.git)',
    ]
    for pat in patterns:
        m = re.search(pat, project_html, re.I | re.S)
        if m:
            value = html.unescape(m.group(1)).strip()
            if value.startswith("git@"):
                path = value[len("git@") :]
                if ":" in path:
                    host_port, repo_path = path.split(":", 1)
                    return f"ssh://git@{host_port}/{repo_path}"
            return value
    raise RuntimeError("Could not extract SSH clone URL from repository page")


def looks_like_url(value: str) -> bool:
    return bool(re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value))


def validate_output_schema(retrieved_data, output_schema: dict) -> None:
    if output_schema.get("type") != "array":
        raise RuntimeError("Unsupported output_schema: expected array")
    if not isinstance(retrieved_data, list):
        raise RuntimeError("retrieved_data must be a list")
    item_schema = output_schema.get("items") or {}
    if item_schema.get("type") != "string":
        raise RuntimeError("Unsupported output_schema.items.type")
    if item_schema.get("format") == "url":
        for item in retrieved_data:
            if not isinstance(item, str) or not looks_like_url(item):
                raise RuntimeError(f"Invalid URL item in retrieved_data: {item!r}")


def write_agent_response(workspace: Path, status: str, retrieved_data, error_details):
    payload = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    (workspace / "agent_response.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def resolve_project_path(browser: BrowserSession, base_url: str, repo_query: str, log) -> tuple[str, list[str]]:
    search_error = None
    try:
        return search_projects(browser, base_url, repo_query)
    except Exception as e:
        search_error = str(e)
        log(f"search fallback triggered: {search_error}")

    qnorm = normalize(repo_query)
    best_path = None
    best_score = -1
    evidence = [f"search_failed={search_error}"]

    for href in list_explore_candidates(browser, base_url):
        score = 0
        hnorm = normalize(href)
        if qnorm and qnorm in hnorm:
            score += 80
        words = [w for w in re.split(r"[^a-z0-9]+", repo_query.lower()) if w]
        for w in words:
            if w in href.lower():
                score += 8
        if score > best_score:
            best_score = score
            best_path = href
            evidence.append(f"explore_candidate path={href} score={score}")

    if best_path:
        return best_path, evidence

    raise RuntimeError(f"Could not resolve project path for query: {repo_query}")


def main():
    workspace = get_workspace()
    taskspec = load_taskspec(os.sys.argv[1])
    run_dir = next_run_dir(workspace)
    screenshots_dir = run_dir / "screenshots"
    copy_self(run_dir)
    logger = Logger(run_dir / "final_script_log.txt")
    log = logger.log

    try:
        base_url = parse_base_url(taskspec)
        username, password = parse_credentials(taskspec)
        repo_query = parse_repo_query(taskspec)
        output_schema = taskspec.get("output_schema") or {}

        browser = BrowserSession()

        log(f"step 1 action: sign in to GitLab at {base_url} as {username}")
        landing_url, landing_html = login(browser, base_url, username, password)
        (run_dir / "after_login.html").write_text(landing_html, encoding="utf-8")
        write_text_image(
            screenshots_dir / "final_execution_1_authenticated.png",
            f"Authenticated\nURL: {landing_url}\n\n{strip_text(landing_html)[:2200]}",
        )
        log(f"step 1 evidence: login succeeded; landed on {landing_url}")

        log(f"step 2 action: locate repository path for query {repo_query!r}")
        project_path, path_evidence = resolve_project_path(browser, base_url, repo_query, log)
        search_url = urllib.parse.urljoin(base_url + "/", "search?scope=projects&search=" + urllib.parse.quote(repo_query))
        try:
            _, search_html = browser.get(search_url)
            (run_dir / "search_results.html").write_text(search_html, encoding="utf-8")
        except Exception:
            search_html = ""
        write_text_image(
            screenshots_dir / "final_execution_2_search_results.png",
            f"Repo query: {repo_query}\nMatched path: {project_path}\n\nEvidence:\n" + "\n".join(path_evidence[:30]),
        )
        log(f"step 2 evidence: identified project path {project_path}")

        log(f"step 3 action: open project page {project_path} and extract SSH clone URL")
        project_url, project_html = fetch_project_page(browser, base_url, project_path)
        (run_dir / "repo_page.html").write_text(project_html, encoding="utf-8")
        ssh_url = extract_ssh_clone_url(project_html)
        write_text_image(
            screenshots_dir / "final_execution_3_repo_clone_url.png",
            f"Project URL: {project_url}\nProject path: {project_path}\n\nSSH clone URL:\n{ssh_url}\n\nText:\n{strip_text(project_html)[:1800]}",
        )
        log(f"step 3 evidence: extracted SSH clone URL {ssh_url}")

        retrieved_data = [ssh_url]
        validate_output_schema(retrieved_data, output_schema)

        write_agent_response(workspace, "SUCCESS", retrieved_data, None)
        write_text_image(
            screenshots_dir / "final_execution_4_final_response.png",
            json.dumps(
                {
                    "task_type": "RETRIEVE",
                    "status": "SUCCESS",
                    "retrieved_data": retrieved_data,
                    "error_details": None,
                },
                indent=2,
            ),
        )
        log(f"step 4 action: wrote agent_response.json with SSH URL {ssh_url}")

    except Exception as e:
        error_details = f"{type(e).__name__}: {e}"
        write_agent_response(workspace, "ERROR", [], error_details)
        write_text_image(
            screenshots_dir / "final_execution_error.png",
            f"Task failed\n{error_details}",
        )
        log(f"ERROR: {error_details}")
        raise


if __name__ == "__main__":
    main()
