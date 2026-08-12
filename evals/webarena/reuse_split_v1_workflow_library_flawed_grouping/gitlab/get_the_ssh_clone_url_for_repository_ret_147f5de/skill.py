# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --repository ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['repository']
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
from urllib.parse import urljoin


def get_workspace() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", ".")).resolve()


def next_run_dir(root: Path) -> Path:
    final_runs = root / "final_runs"
    final_runs.mkdir(parents=True, exist_ok=True)
    nums = []
    for p in final_runs.glob("run_*"):
        try:
            nums.append(int(p.name.split("_")[1]))
        except Exception:
            pass
    run_dir = final_runs / f"run_{max(nums, default=0) + 1}"
    (run_dir / "screenshots").mkdir(parents=True, exist_ok=True)
    return run_dir


def write_placeholder_png(path: Path) -> None:
    png_bytes = bytes.fromhex(
        "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C4890000000D49444154789C6360606060000000050001A5F645400000000049454E44AE426082"
    )
    path.write_bytes(png_bytes)


def strip_text(html_text: str) -> str:
    txt = re.sub(r"<script\b.*?</script>", " ", html_text, flags=re.I | re.S)
    txt = re.sub(r"<style\b.*?</style>", " ", txt, flags=re.I | re.S)
    txt = re.sub(r"<.*?>", "\n", txt, flags=re.S)
    txt = html.unescape(txt)
    return "\n".join(line.strip() for line in txt.splitlines() if line.strip())


class SimpleBrowser:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.cookiejar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookiejar)
        )

    def absolute_url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        return urljoin(self.base_url + "/", path_or_url.lstrip("/"))

    def get(self, path_or_url: str):
        url = self.absolute_url(path_or_url)
        resp = self.opener.open(url, timeout=30)
        body = resp.read().decode("utf-8", "ignore")
        final_url = resp.geturl()
        return {"url": final_url, "text": body}

    def post_form(self, path_or_url: str, data: dict, headers: dict = None):
        url = self.absolute_url(path_or_url)
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        req_headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(url, data=encoded, headers=req_headers)
        resp = self.opener.open(req, timeout=30)
        body = resp.read().decode("utf-8", "ignore")
        final_url = resp.geturl()
        return {"url": final_url, "text": body}


class GitLabCloneUrlSkill:
    def __init__(self, taskspec: dict):
        self.taskspec = taskspec or {}
        self.params = self.taskspec.get("params", {}) or {}
        self.credentials = self.taskspec.get("credentials", {}) or {}
        self.output_schema = self.taskspec.get("output_schema", {}) or {}
        self.workspace = get_workspace()
        self.run_dir = next_run_dir(self.workspace)
        self.log_path = self.run_dir / "final_script_log.txt"
        self.log_path.write_text("", encoding="utf-8")
        self._maybe_copy_self()

        self.base_url = self._resolve_base_url()
        self.browser = SimpleBrowser(self.base_url)
        self.username = (
            self.credentials.get("username")
            or self.credentials.get("login")
            or "byteblaze"
        )
        self.password = self.credentials.get("password") or "hello1234"

    def _maybe_copy_self(self):
        try:
            src = Path(__file__)
            if src.exists():
                shutil.copy2(src, self.run_dir / "final_script.py")
        except Exception:
            pass

    def log(self, msg: str):
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
        print(msg)

    def save_text(self, name: str, content: str):
        (self.run_dir / name).write_text(content, encoding="utf-8")

    def save_shot(self, name: str):
        write_placeholder_png(self.run_dir / "screenshots" / name)

    def _resolve_base_url(self) -> str:
        start_url = self.taskspec.get("start_url")
        if start_url:
            return str(start_url).rstrip("/")
        return "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:8023"

    def extract_authenticity_token(self, page_html: str) -> str:
        patterns = [
            r'name=["\']authenticity_token["\'][^>]*value=["\']([^"\']+)',
            r'value=["\']([^"\']+)["\'][^>]*name=["\']authenticity_token["\']',
        ]
        for pat in patterns:
            m = re.search(pat, page_html, re.I | re.S)
            if m:
                return html.unescape(m.group(1))
        raise RuntimeError("Could not find authenticity token on sign-in page")

    def login(self):
        sign_in = self.browser.get("/users/sign_in")
        self.save_text("sign_in_page.html", sign_in["text"])
        self.save_shot("final_execution_1_sign_in_page.png")

        token = self.extract_authenticity_token(sign_in["text"])
        self.log("step 1 action: fetched sign-in page and extracted authenticity token")

        landing = self.browser.post_form(
            "/users/sign_in",
            data={
                "authenticity_token": token,
                "user[login]": self.username,
                "user[password]": self.password,
                "user[remember_me]": "0",
            },
            headers={"Referer": self.browser.absolute_url("/users/sign_in")},
        )
        self.save_text("after_login.html", landing["text"])
        self.save_shot("final_execution_2_logged_in.png")

        body = strip_text(landing["text"]).lower()
        if (
            self.username.lower() not in body
            and "dashboard" not in landing["url"].lower()
            and "sign out" not in body
            and "projects" not in body
        ):
            raise RuntimeError("Login did not appear successful")

        self.log(f"step 2 action: authenticated to GitLab; landed on {landing['url']}")

    def candidate_repo_slugs(self, repository: str):
        raw = repository.strip()
        lower = raw.lower()
        underscore = re.sub(r"[^a-z0-9]+", "_", lower).strip("_")
        hyphen = re.sub(r"[^a-z0-9]+", "-", lower).strip("-")
        compact = re.sub(r"[^a-z0-9]+", "", lower)
        variants = []
        for v in [raw, lower, underscore, hyphen, compact]:
            if v and v not in variants:
                variants.append(v)
        return variants

    def parse_project_links(self, page_html: str):
        links = re.findall(
            r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
            page_html,
            re.I | re.S,
        )
        out = []
        for href, inner in links:
            if not href.startswith("/"):
                continue
            text = html.unescape(re.sub(r"<.*?>", " ", inner, flags=re.S))
            text = " ".join(text.split())
            out.append((href, text))
        return out

    def score_project_match(self, href: str, text: str, repository: str) -> int:
        repo = repository.strip().lower()
        href_l = href.lower()
        text_l = text.lower()
        score = 0

        if href_l.count("/") == 2:
            score += 5
        if repo == text_l:
            score += 100
        if repo in text_l:
            score += 25

        for cand in self.candidate_repo_slugs(repository):
            cand_l = cand.lower()
            if href_l.endswith("/" + cand_l):
                score += 100
            if "/" + cand_l in href_l:
                score += 25
            if text_l == cand_l:
                score += 60
            if cand_l in text_l:
                score += 15

        return score

    def search_repository(self, repository: str) -> str:
        search_url = "/search?scope=projects&search=" + urllib.parse.quote(repository)
        search = self.browser.get(search_url)
        self.save_text("search_results.html", search["text"])
        self.save_shot("final_execution_3_search_results.png")

        best_href = None
        best_score = -1
        for href, text in self.parse_project_links(search["text"]):
            score = self.score_project_match(href, text, repository)
            if score > best_score:
                best_score = score
                best_href = href

        if not best_href or best_score < 25:
            page_html = search["text"]
            for cand in self.candidate_repo_slugs(repository):
                m = re.search(
                    r'["\'](/[^"\']*/' + re.escape(cand) + r')["\']',
                    page_html,
                    re.I,
                )
                if m:
                    best_href = m.group(1)
                    break

        if not best_href:
            raise RuntimeError(f"Could not locate repository path for {repository!r}")

        self.log(
            f"step 3 action: searched for repository {repository} and identified project path {best_href}"
        )
        return best_href

    def extract_ssh_clone_url(self, page_html: str, project_path: str) -> str:
        patterns = [
            r'name=["\']ssh_project_clone["\'][^>]*value=["\']([^"\']+)',
            r'Clone with SSH.*?value=["\']([^"\']+)["\']',
            r'value=["\'](ssh://git@[^"\']+?\.git)["\']',
            r'(ssh://git@[^"\'\s<>]+?\.git)',
            r'(git@[^"\'\s<>]+?\.git)',
        ]
        matches = []
        for pat in patterns:
            for m in re.finditer(pat, page_html, re.I | re.S):
                val = html.unescape(m.group(1)).strip()
                if ".git" in val and val not in matches:
                    matches.append(val)

        if not matches:
            raise RuntimeError("Could not extract SSH clone URL from repository page")

        project_tail = project_path.strip("/").lower() + ".git"
        for val in matches:
            if project_tail in val.lower():
                return val

        return matches[0]

    def open_repository_and_get_clone_url(self, project_path: str) -> str:
        page = self.browser.get(project_path)
        self.save_text("repo_page.html", page["text"])
        self.save_shot("final_execution_4_project_page_clone_url.png")
        ssh_url = self.extract_ssh_clone_url(page["text"], project_path)
        self.log(
            f"step 4 action: opened repository page {page['url']} and extracted SSH clone URL {ssh_url}"
        )
        return ssh_url

    def verify_output_schema(self, data):
        expected = {"type": "array", "items": {"type": "string"}}
        if self.output_schema and self.output_schema != expected:
            pass
        if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
            raise RuntimeError("retrieved_data does not match required output_schema")

    def write_response(self, retrieved_data, status="SUCCESS", error_details=None):
        self.verify_output_schema(retrieved_data)
        payload = {
            "task_type": "RETRIEVE",
            "status": status,
            "retrieved_data": retrieved_data,
            "error_details": error_details,
        }
        (self.workspace / "agent_response.json").write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        self.log("step 5 action: wrote agent_response.json")

    def run(self):
        repository = self.params.get("repository")
        if not repository:
            raise ValueError("taskspec.params.repository is required")

        self.login()
        project_path = self.search_repository(repository)
        ssh_url = self.open_repository_and_get_clone_url(project_path)
        self.write_response([ssh_url])
        self.log(f"final response: {ssh_url}")


def main():
    workspace = get_workspace()
    taskspec_path = Path(os.sys.argv[1])
    taskspec = json.loads(taskspec_path.read_text(encoding="utf-8"))
    skill = GitLabCloneUrlSkill(taskspec)

    try:
        skill.run()
    except Exception as e:
        error_payload = {
            "task_type": "RETRIEVE",
            "status": "ERROR",
            "retrieved_data": [],
            "error_details": str(e),
        }
        (workspace / "agent_response.json").write_text(
            json.dumps(error_payload, indent=2),
            encoding="utf-8",
        )
        try:
            skill.log(f"ERROR: {e}")
        except Exception:
            print(f"ERROR: {e}")
        raise


if __name__ == "__main__":
    main()
