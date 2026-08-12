# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --query ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['query']
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
import html as html_lib
import urllib.parse
import urllib.request
import http.cookiejar
from pathlib import Path


def get_workspace_dir() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", os.getcwd())).resolve()


WORKSPACE = get_workspace_dir()
ARTIFACTS_DIR = WORKSPACE / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = WORKSPACE / "skill_log.txt"


def log(message: str) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_taskspec(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_opener() -> urllib.request.OpenerDirector:
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def http_get(opener, url: str, headers: dict | None = None) -> tuple[str, str]:
    req = urllib.request.Request(url, headers=headers or {})
    resp = opener.open(req)
    body = resp.read().decode("utf-8", "ignore")
    return body, resp.geturl()


def http_post_form(opener, url: str, data: dict, headers: dict | None = None) -> tuple[str, str]:
    encoded = urllib.parse.urlencode(data).encode()
    req_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=encoded, headers=req_headers)
    resp = opener.open(req)
    body = resp.read().decode("utf-8", "ignore")
    return body, resp.geturl()


def strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return " ".join(text.split())


def extract_csrf_token(html: str) -> str | None:
    patterns = [
        r'name="authenticity_token"\s+value="([^"]+)"',
        r'value="([^"]+)"\s+name="authenticity_token"',
        r"name='authenticity_token'\s+value='([^']+)'",
        r"value='([^']+)'\s+name='authenticity_token'",
    ]
    for pattern in patterns:
        m = re.search(pattern, html, flags=re.I)
        if m:
            return html_lib.unescape(m.group(1))
    return None


def login_gitlab(opener, base_url: str, credentials: dict) -> None:
    username = credentials.get("username") or credentials.get("login") or credentials.get("user")
    password = credentials.get("password") or credentials.get("pass")
    if not username or not password:
        raise ValueError("Missing username/password in taskspec.credentials")

    sign_in_url = urllib.parse.urljoin(base_url.rstrip("/") + "/", "users/sign_in")
    sign_in_html, _ = http_get(opener, sign_in_url)
    csrf = extract_csrf_token(sign_in_html)
    if not csrf:
        raise RuntimeError("Could not find authenticity_token on sign-in page")

    _, landing_url = http_post_form(
        opener,
        sign_in_url,
        {
            "user[login]": username,
            "user[password]": password,
            "authenticity_token": csrf,
        },
        headers={"Referer": sign_in_url},
    )
    log(f"logged_in landing_url={landing_url}")


def language_name_to_code(language: str) -> str | None:
    mapping = {
        "python": "8",
    }
    return mapping.get(language.strip().lower())


def derive_search_strategy(query: str) -> dict:
    q = " ".join(query.split()).strip()
    q_lower = q.lower()

    language_code = None
    core_topic = q

    m = re.search(r"\b([A-Za-z+#]+)\s+implementation\b", q, flags=re.I)
    if m:
        language_code = language_name_to_code(m.group(1))
        core_topic = re.sub(r"\b([A-Za-z+#]+)\s+implementation\b", "", q, flags=re.I).strip()

    core_topic = re.sub(r"\b(best|top)\b", "", core_topic, flags=re.I).strip()
    core_topic = re.sub(r"\s+", " ", core_topic).strip()

    tokens = [t.lower() for t in re.split(r"[^a-z0-9]+", core_topic) if t]
    return {
        "original_query": q,
        "language_code": language_code,
        "topic_text": core_topic,
        "tokens": tokens,
        "sort": "stars_desc",
        "query_lower": q_lower,
    }


def open_explore_projects(opener, base_url: str, language_code: str | None, sort: str) -> tuple[str, str]:
    params = {}
    if language_code:
        params["language"] = language_code
    if sort:
        params["sort"] = sort
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", "explore/projects")
    if params:
        url += "?" + urllib.parse.urlencode(params)
    html, final_url = http_get(opener, url)
    log(f"opened_explore url={final_url}")
    return html, final_url


def normalize_project_path(href: str) -> str | None:
    href = html_lib.unescape(href).strip()
    if not href.startswith("/"):
        return None
    path = href.split("?", 1)[0].split("#", 1)[0]
    parts = [p for p in path.split("/") if p]
    if len(parts) != 2:
        return None
    if any(p in {"-", "users", "projects", "groups", "explore"} for p in parts):
        return None
    return "/" + "/".join(parts)


def extract_project_candidates(explore_html: str) -> list[dict]:
    candidates = []
    seen = set()

    href_matches = re.findall(
        r'<a[^>]+href=(["\'])(/[^"\']+)\1[^>]*>(.*?)</a>',
        explore_html,
        flags=re.I | re.S,
    )

    for _, href, inner in href_matches:
        path = normalize_project_path(href)
        if not path:
            continue
        if path in seen:
            continue
        seen.add(path)
        visible_text = strip_tags(inner)
        slug = path.strip("/").split("/")[-1]
        namespace = path.strip("/").split("/")[0]
        combined_text = " ".join(x for x in [visible_text, slug, namespace, path.strip("/")] if x).strip()
        candidates.append(
            {
                "href": path,
                "visible_text": visible_text,
                "combined_text": combined_text,
            }
        )

    return candidates


def score_candidate(candidate: dict, strategy: dict) -> tuple[int, int, int, int]:
    text = candidate["combined_text"].lower()
    href = candidate["href"].lower()
    topic = strategy["topic_text"].lower()
    tokens = strategy["tokens"]

    score = 0

    if topic:
        if topic.lower() in text:
            score += 200
        topic_parts = [t for t in re.split(r"[^a-z0-9]+", topic.lower()) if t]
        ordered_hit = 0
        pos = -1
        for part in topic_parts:
            new_pos = text.find(part, pos + 1)
            if new_pos != -1:
                ordered_hit += 1
                pos = new_pos
        score += ordered_hit * 20

    token_hits = 0
    for t in tokens:
        if t in text or t in href:
            token_hits += 1
            score += 25

    slug = href.rsplit("/", 1)[-1]
    if topic and slug == topic.replace(" ", "-"):
        score += 50
    if topic and topic.replace(" ", "-") in slug:
        score += 25

    penalties = 0
    if "mirror" in text:
        penalties += 15
    if "fork" in text:
        penalties += 5
    score -= penalties

    return (score, token_hits, -penalties, -len(href))


def choose_best_project(explore_html: str, strategy: dict) -> str:
    candidates = extract_project_candidates(explore_html)
    if not candidates:
        raise RuntimeError("No project candidates found on explore page")

    ranked = sorted(candidates, key=lambda c: score_candidate(c, strategy), reverse=True)
    best = ranked[0]
    log(
        f"selected_project href={best['href']} combined_text={best['combined_text']!r} "
        f"score={score_candidate(best, strategy)}"
    )
    return best["href"]


def open_project_page(opener, base_url: str, project_href: str) -> tuple[str, str]:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", project_href.lstrip("/"))
    html, final_url = http_get(opener, url)
    log(f"opened_project url={final_url}")
    return html, final_url


def extract_ssh_clone_url(project_html: str) -> str | None:
    patterns = [
        r'ssh://git@[^\s"\'<>]+?\.git',
        r'git@[^\s"\'<>:]+:[^\s"\'<>]+?\.git',
    ]
    matches = []
    for pattern in patterns:
        for m in re.finditer(pattern, project_html):
            matches.append(m.group(0))
    if not matches:
        return None

    def score(url: str) -> tuple[int, int]:
        s = 0
        if url.startswith("ssh://git@"):
            s += 10
        if url.endswith(".git"):
            s += 2
        return (s, len(url))

    matches = sorted(set(matches), key=score, reverse=True)
    return matches[0]


def verify_project_matches_query(project_html: str, strategy: dict) -> bool:
    text = strip_tags(project_html).lower()
    tokens = strategy["tokens"]
    if not tokens:
        return True
    hits = sum(1 for t in tokens if t in text)
    return hits >= max(1, min(len(tokens), 1))


def retrieve_best_repo_ssh_url(taskspec: dict) -> list[str]:
    params = taskspec.get("params", {})
    query = params.get("query")
    if not query:
        raise ValueError("Missing params.query")

    base_url = taskspec.get("start_url")
    if not base_url:
        raise ValueError("Missing start_url")

    credentials = taskspec.get("credentials", {})
    opener = build_opener()
    login_gitlab(opener, base_url, credentials)

    strategy = derive_search_strategy(query)
    explore_html, _ = open_explore_projects(
        opener,
        base_url,
        strategy["language_code"],
        strategy["sort"],
    )
    project_href = choose_best_project(explore_html, strategy)
    project_html, _ = open_project_page(opener, base_url, project_href)

    if not verify_project_matches_query(project_html, strategy):
        log("warning project page weakly matched query tokens")

    ssh_url = extract_ssh_clone_url(project_html)
    if not ssh_url:
        raise RuntimeError("Could not extract SSH clone URL from project page")

    return [ssh_url]


def main():
    LOG_PATH.write_text("", encoding="utf-8")
    response_path = WORKSPACE / "agent_response.json"

    try:
        taskspec_path = sys.argv[1]
        taskspec = read_taskspec(taskspec_path)
        retrieved_data = retrieve_best_repo_ssh_url(taskspec)
        response = {
            "task_type": "RETRIEVE",
            "status": "SUCCESS",
            "retrieved_data": retrieved_data,
            "error_details": None,
        }
    except Exception as e:
        response = {
            "task_type": "RETRIEVE",
            "status": "ERROR",
            "retrieved_data": [],
            "error_details": str(e),
        }

    write_json(response_path, response)


if __name__ == "__main__":
    main()
