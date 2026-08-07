# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --repo ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['repo']
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
import html as htmlmod
from pathlib import Path
from urllib.parse import urljoin

import requests


def get_workspace() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", os.getcwd())).resolve()


def ensure_output_dirs(workspace: Path):
    logs_dir = workspace / "logs"
    screenshots_dir = workspace / "screenshots"
    artifacts_dir = workspace / "artifacts"
    logs_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir, screenshots_dir, artifacts_dir


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_placeholder_png(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (1280, 1600), "white")
        draw = ImageDraw.Draw(img)
        y = 20
        for line in text.splitlines():
            if y > 1560:
                break
            draw.text((20, y), line[:180], fill="black")
            y += 22
        img.save(path)
    except Exception:
        import base64
        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7z8AAAAASUVORK5CYII="
        path.write_bytes(base64.b64decode(png_b64))


class RunContext:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.logs_dir, self.screenshots_dir, self.artifacts_dir = ensure_output_dirs(workspace)
        self.log_path = self.logs_dir / "skill.log"
        self.step = 1
        write_text(self.log_path, "")

    def log(self, message: str):
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(message + "\n")

    def save_html(self, name: str, html: str):
        write_text(self.artifacts_dir / name, html)

    def screenshot(self, name: str, text: str):
        write_placeholder_png(self.screenshots_dir / name, text)

    def step_log(self, message: str):
        self.log(f"step {self.step}: {message}")
        self.step += 1


def load_taskspec(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_base_url(taskspec: dict) -> str:
    start_url = taskspec.get("start_url")
    if not start_url:
        raise RuntimeError("taskspec.start_url is required")
    m = re.match(r"^(https?://[^/]+)", start_url)
    if not m:
        raise RuntimeError(f"Could not derive base URL from start_url: {start_url}")
    return m.group(1)


def get_credentials(taskspec: dict):
    creds = taskspec.get("credentials") or {}
    username = creds.get("username") or creds.get("login")
    password = creds.get("password")
    if not username or not password:
        raise RuntimeError("taskspec.credentials.username/login and password are required")
    return username, password


def extract_authenticity_token(html: str) -> str:
    m = re.search(r'name="authenticity_token"\s+value="([^"]+)"', html)
    if not m:
        m = re.search(r'value="([^"]+)"\s+name="authenticity_token"', html)
    if not m:
        raise RuntimeError("authenticity_token not found")
    return htmlmod.unescape(m.group(1))


def login(session: requests.Session, base_url: str, username: str, password: str, ctx: RunContext):
    signin_url = urljoin(base_url, "/users/sign_in")
    ctx.step_log(f"open sign-in page {signin_url}")
    r = session.get(signin_url, timeout=30)
    r.raise_for_status()
    ctx.save_html("sign_in.html", r.text)
    token = extract_authenticity_token(r.text)
    ctx.screenshot("step_login_page.png", f"URL: {r.url}\nFound authenticity token for sign-in.")

    ctx.step_log(f"submit credentials for {username}")
    r = session.post(
        signin_url,
        data={
            "authenticity_token": token,
            "user[login]": username,
            "user[password]": password,
            "user[remember_me]": "0",
        },
        allow_redirects=True,
        timeout=30,
    )
    r.raise_for_status()
    ctx.save_html("after_login.html", r.text)
    if "/users/sign_in" in r.url and "sign in" in r.text.lower():
        raise RuntimeError("Login appears to have failed")
    ctx.screenshot("step_after_login.png", f"URL: {r.url}\nAuthenticated as {username}.")


def extract_project_links(html: str):
    projects = []
    for href, text in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        clean = re.sub(r"<[^>]+>", " ", text)
        clean = re.sub(r"\s+", " ", htmlmod.unescape(clean)).strip()
        projects.append((href, clean))
    seen = set()
    deduped = []
    for href, clean in projects:
        if href in seen:
            continue
        seen.add(href)
        deduped.append((href, clean))
    return deduped


def find_repo_path_from_search(session: requests.Session, base_url: str, owner_username: str, repo: str, ctx: RunContext) -> str:
    search_url = urljoin(base_url, f"/dashboard/projects?name={repo}&personal=true&sort=name_asc")
    ctx.step_log(f"search owned projects for repo {repo}")
    r = session.get(search_url, timeout=30)
    r.raise_for_status()
    ctx.save_html("project_search.html", r.text)

    candidates = []
    for href, clean in extract_project_links(r.text):
        if not href.startswith(f"/{owner_username}/"):
            continue
        if "/-/" in href:
            continue
        repo_name = href.rstrip("/").split("/")[-1]
        if repo_name == repo or clean == repo or repo.lower() in href.lower() or repo.lower() in clean.lower():
            candidates.append(href)

    if not candidates:
        exact = f"/{owner_username}/{repo}"
        # fallback guess; verify below
        candidates = [exact]

    project_path = candidates[0]
    ctx.screenshot("step_project_search.png", "Candidates:\n" + "\n".join(candidates))
    return verify_project_exists(session, base_url, project_path, repo, ctx)


def verify_project_exists(session: requests.Session, base_url: str, project_path: str, repo: str, ctx: RunContext) -> str:
    ctx.step_log(f"verify project path {project_path}")
    r = session.get(urljoin(base_url, project_path), timeout=30)
    r.raise_for_status()
    ctx.save_html("project_page.html", r.text)
    page_text = htmlmod.unescape(re.sub(r"<[^>]+>", " ", r.text))
    if repo.lower() not in page_text.lower() and project_path.rstrip("/").split("/")[-1].lower() != repo.lower():
        raise RuntimeError(f"Verified page does not look like repo {repo}: {project_path}")
    ctx.screenshot("step_project_page.png", f"Verified project page: {project_path}")
    return project_path


def parse_members_blob(html: str):
    m = re.search(r'data-members-data="([^"]+)"', html)
    if not m:
        raise RuntimeError("Could not find data-members-data on members page")
    decoded = htmlmod.unescape(m.group(1))
    data = json.loads(decoded)

    members = (((data or {}).get("user") or {}).get("members")) or []
    parsed = []
    for member in members:
        user = member.get("user") or {}
        parsed.append({
            "username": user.get("username"),
            "name": user.get("name"),
            "access_level": ((member.get("access_level") or {}).get("string_value")),
            "type": member.get("type"),
        })
    return parsed, data


def open_project_members(session: requests.Session, base_url: str, project_path: str, ctx: RunContext):
    members_path = project_path.rstrip("/") + "/-/project_members"
    ctx.step_log(f"open members page {members_path}")
    r = session.get(urljoin(base_url, members_path), timeout=30)
    r.raise_for_status()
    ctx.save_html("project_members.html", r.text)
    parsed_members, raw = parse_members_blob(r.text)
    write_json(ctx.artifacts_dir / "project_members_data.json", parsed_members)
    return members_path, parsed_members, raw


def extract_other_usernames(parsed_members, current_username: str):
    usernames = []
    seen = set()
    for member in parsed_members:
        uname = member.get("username")
        if not uname:
            continue
        if uname == current_username:
            continue
        if uname in seen:
            continue
        seen.add(uname)
        usernames.append(uname)
    return usernames


def validate_output_schema(taskspec: dict, data):
    schema = taskspec.get("output_schema") or {}
    if schema.get("type") != "array":
        raise RuntimeError("Unsupported output_schema: expected array")
    item_type = (schema.get("items") or {}).get("type")
    if item_type != "string":
        raise RuntimeError("Unsupported output_schema.items.type: expected string")
    if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
        raise RuntimeError("Retrieved data does not match required schema")


def write_response(workspace: Path, retrieved_data=None, error_details=None, status="SUCCESS"):
    response = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    write_json(workspace / "agent_response.json", response)


def main():
    workspace = get_workspace()
    ctx = RunContext(workspace)
    taskspec = load_taskspec(sys.argv[1])

    try:
        params = taskspec.get("params") or {}
        repo = params.get("repo")
        if not repo:
            raise RuntimeError("taskspec.params.repo is required")

        base_url = get_base_url(taskspec)
        username, password = get_credentials(taskspec)

        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 skill-agent"})

        login(session, base_url, username, password, ctx)
        project_path = find_repo_path_from_search(session, base_url, username, repo, ctx)
        members_path, parsed_members, _raw = open_project_members(session, base_url, project_path, ctx)

        other_usernames = extract_other_usernames(parsed_members, username)
        validate_output_schema(taskspec, other_usernames)

        evidence = [f"Members page: {urljoin(base_url, members_path)}", "Parsed members:"]
        for m in parsed_members:
            evidence.append(
                f"- username={m.get('username')} name={m.get('name')} access={m.get('access_level')} type={m.get('type')}"
            )
        evidence.append("Other users with access:")
        evidence.extend(other_usernames or ["<none>"])
        ctx.screenshot("step_members_page.png", "\n".join(evidence))
        ctx.log("retrieved usernames: " + json.dumps(other_usernames))

        write_response(workspace, retrieved_data=other_usernames, error_details=None, status="SUCCESS")
        ctx.screenshot("step_final_response.png", json.dumps({
            "task_type": "RETRIEVE",
            "status": "SUCCESS",
            "retrieved_data": other_usernames,
            "error_details": None,
        }, indent=2))
    except Exception as e:
        ctx.log(f"ERROR: {e}")
        write_response(workspace, retrieved_data=[], error_details=str(e), status="ERROR")
        ctx.screenshot("step_error.png", f"ERROR\n{type(e).__name__}: {e}")
        raise


if __name__ == "__main__":
    main()
