# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --forum ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['forum', 'retrieved_data_format_spec']
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
import textwrap
import urllib.request
import urllib.parse
from html import unescape
from pathlib import Path


BASE_DEFAULT = "http://ec2-18-223-172-69.us-east-2.compute.amazonaws.com:9999"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def init_paths():
    workspace = Path(os.environ.get("WORKSPACE_DIR", os.getcwd()))
    final_runs = ensure_dir(workspace / "final_runs")
    existing = []
    for p in final_runs.glob("run_*"):
        try:
            existing.append(int(p.name.split("_")[1]))
        except Exception:
            pass
    run_id = max(existing, default=0) + 1
    run_dir = ensure_dir(final_runs / f"run_{run_id}")
    screenshots = ensure_dir(run_dir / "screenshots")
    log_path = run_dir / "final_script_log.txt"
    log_path.write_text("", encoding="utf-8")
    agent_response = workspace / "agent_response.json"
    return workspace, run_dir, screenshots, log_path, agent_response


WORKSPACE, RUN_DIR, SCREENSHOTS, LOG_PATH, AGENT_RESPONSE = init_paths()


def log(msg: str):
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)


def write_text_evidence(path: Path, title: str, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = title + "\n\n" + "\n".join(lines)
    try:
        from PIL import Image, ImageDraw, ImageFont
        width, height = 1280, 1800
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        y = 20
        for para in text.splitlines():
            wrapped = textwrap.wrap(para, width=120) or [""]
            for line in wrapped:
                draw.text((20, y), line, fill="black", font=font)
                y += 16
                if y > height - 30:
                    break
            if y > height - 30:
                break
        img.save(path)
    except Exception:
        txt_path = path.with_suffix(path.suffix + ".txt")
        txt_path.write_text(text, encoding="utf-8")


def read_taskspec(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_base_url(taskspec):
    return taskspec.get("start_url") or BASE_DEFAULT


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def join_url(base: str, path: str) -> str:
    return urllib.parse.urljoin(base.rstrip("/") + "/", path.lstrip("/")) if not path.startswith("http") else path


def strip_tags(s: str) -> str:
    s = re.sub(r"<script[\s\S]*?</script>", " ", s, flags=re.I)
    s = re.sub(r"<style[\s\S]*?</style>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    return " ".join(unescape(s).split())


def forum_path_candidates(forum: str):
    raw = forum.strip()
    compact = raw.replace(" ", "")
    return [
        f"/f/{raw}/new",
        f"/f/{compact}/new",
        f"/f/{raw}MA/new",
        f"/f/{compact}MA/new",
    ]


def discover_forum_new_url(base_url: str, forum: str):
    tried = []
    for path in forum_path_candidates(forum):
        url = join_url(base_url, path)
        tried.append(url)
        try:
            html = fetch_url(url)
            if re.search(r'<article class="\s*submission', html) or re.search(r'/f/[^/]+/\d+/', html):
                return url, html, tried
        except Exception:
            continue
    raise RuntimeError(f"Could not discover forum new URL for forum={forum!r}. Tried: {tried}")


def parse_first_submission_from_new(html: str, forum: str):
    patterns = [
        re.compile(
            r'<article class="\s*submission[\s\S]*?<h1 class="submission__title[^"]*">\s*<a href="([^"]+)"[^>]*>(.*?)</a>[\s\S]*?Submitted by\s*<a href="/user/[^"]+"[^>]*><strong>(.*?)</strong></a>[\s\S]*?<time[^>]*title="([^"]+)"',
            re.I,
        ),
        re.compile(
            r'<article class="\s*submission[\s\S]*?<a href="(/f/[^/]+/\d+/[^"]+)"[^>]*>(.*?)</a>[\s\S]*?Submitted by\s*<a href="/user/([^"]+)"',
            re.I,
        ),
    ]
    for pat in patterns:
        m = pat.search(html)
        if m:
            href = m.group(1)
            title = strip_tags(m.group(2))
            author = unescape(m.group(3)).strip()
            time_val = m.group(4) if len(m.groups()) >= 4 else None
            if href and title:
                return {"href": href, "title": title, "author": author, "time": time_val}

    href_pat = re.compile(r'href="(/f/[^/]+/\d+/[^"]+)"', re.I)
    hrefs = []
    for m in href_pat.finditer(html):
        href = m.group(1)
        if href not in hrefs:
            hrefs.append(href)
    forum_lower = forum.lower().replace(" ", "")
    for href in hrefs:
        if forum_lower in href.lower():
            return {"href": href, "title": "", "author": "", "time": None}
    if hrefs:
        return {"href": hrefs[0], "title": "", "author": "", "time": None}
    raise RuntimeError("Could not parse latest post from forum new page")


def extract_post_metadata(post_html: str, fallback_title: str = "", fallback_author: str = ""):
    title = fallback_title
    author = fallback_author

    title_patterns = [
        re.compile(r'<h1 class="submission__title[^>]*>[\s\S]*?<a [^>]*>(.*?)</a>', re.I),
        re.compile(r'<meta property="og:title" content="(.*?)"', re.I),
        re.compile(r"<title>\s*(.*?)\s*</title>", re.I | re.S),
    ]
    for pat in title_patterns:
        m = pat.search(post_html)
        if m:
            title = strip_tags(m.group(1))
            if title:
                break

    author_patterns = [
        re.compile(r'Submitted by\s*<a href="/user/([^"]+)"', re.I),
        re.compile(r'og:article:author" content="([^"]+)"', re.I),
        re.compile(r'<a href="/user/[^"]+" class="submission__submitter[^"]*"><strong>(.*?)</strong></a>', re.I),
    ]
    for pat in author_patterns:
        m = pat.search(post_html)
        if m:
            author = unescape(strip_tags(m.group(1)))
            if author:
                break

    comment_count_attr = None
    m = re.search(r'data-comment-count="(\d+)"', post_html, re.I)
    if m:
        comment_count_attr = int(m.group(1))

    return {
        "title": title,
        "author": author,
        "comment_count_attr": comment_count_attr,
    }


def split_comments(html: str):
    starts = [m.start() for m in re.finditer(r'<article class="comment', html, re.I)]
    comments = []
    for i, st in enumerate(starts):
        en = starts[i + 1] if i + 1 < len(starts) else html.find("</section>", st)
        if en == -1:
            en = len(html)
        comments.append(html[st:en])
    return comments


def parse_comment(seg: str):
    author = None
    for pat in [
        re.compile(r'<a href="/user/[^"]+" class="fg-inherit"><strong>(.*?)</strong></a>', re.I),
        re.compile(r'<a href="/user/([^"]+)"', re.I),
    ]:
        m = pat.search(seg)
        if m:
            author = unescape(strip_tags(m.group(1)))
            break

    score = None
    m = re.search(r'<span class="vote__net-score"[^>]*>([−\-]?\d+)</span>', seg, re.I)
    if m:
        score = int(m.group(1).replace("−", "-"))

    return {
        "author": author,
        "score": score,
        "is_op_marked": ("comment__author--op" in seg) or (re.search(r'>\s*OP\s*<', seg) is not None),
        "text": strip_tags(seg)[:300],
    }


def count_non_author_negative_comments(post_html: str, post_author: str):
    comments = [parse_comment(seg) for seg in split_comments(post_html)]
    qualifying = [
        c for c in comments
        if c.get("author")
        and c["author"] != post_author
        and c.get("score") is not None
        and c["score"] < 0
    ]
    return len(qualifying), comments


def self_verify_count(post_meta, comments, computed_count):
    attr = post_meta.get("comment_count_attr")
    if attr is not None and len(comments) > attr:
        raise RuntimeError(
            f"Parsed more comments than declared by page attribute: parsed={len(comments)} declared={attr}"
        )
    return True


def write_agent_response(retrieved_data, error_details=None, status="SUCCESS"):
    payload = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    AGENT_RESPONSE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    taskspec_path = os.sys.argv[1]
    taskspec = read_taskspec(taskspec_path)
    params = taskspec.get("params", {})
    forum = params.get("forum", "").strip()
    if not forum:
        raise RuntimeError("taskspec.params.forum is required")

    base_url = get_base_url(taskspec)

    step = 1
    new_url, forum_html, tried_urls = discover_forum_new_url(base_url, forum)
    latest = parse_first_submission_from_new(forum_html, forum)
    log(f"step {step} action: opened forum new page and identified first submission as most recent. forum={forum!r} new_url={new_url} href={latest['href']!r}")
    write_text_evidence(
        SCREENSHOTS / f"final_execution_{step}_forum_new.png",
        f"Latest post identification for forum {forum}",
        [
            f"Discovered new URL: {new_url}",
            f"Tried URLs: {tried_urls}",
            f"Latest post href: {latest.get('href')}",
            f"Latest post title from listing: {latest.get('title')}",
            f"Latest post author from listing: {latest.get('author')}",
            f"Latest post time from listing: {latest.get('time')}",
        ],
    )

    step += 1
    post_url = join_url(base_url, latest["href"])
    post_html = fetch_url(post_url)
    post_meta = extract_post_metadata(post_html, latest.get("title", ""), latest.get("author", ""))
    log(f"step {step} action: opened latest post page and extracted post metadata. post_url={post_url} author={post_meta['author']!r} title={post_meta['title']!r}")
    write_text_evidence(
        SCREENSHOTS / f"final_execution_{step}_post_metadata.png",
        "Post metadata evidence",
        [
            f"Post URL: {post_url}",
            f"Verified title: {post_meta['title']}",
            f"Verified author: {post_meta['author']}",
            f"data-comment-count attribute: {post_meta['comment_count_attr']}",
        ],
    )

    step += 1
    count, comments = count_non_author_negative_comments(post_html, post_meta["author"])
    self_verify_count(post_meta, comments, count)
    log(f"step {step} action: parsed comments and counted comments not by the author with negative displayed net score. parsed_comments={len(comments)} qualifying_count={count}")
    sample_lines = [
        f"Rule used: count comments whose author != post author and displayed net score < 0.",
        f"Post author: {post_meta['author']}",
        f"Parsed comment count: {len(comments)}",
        f"Declared comment count attribute: {post_meta['comment_count_attr']}",
        f"Qualifying count: {count}",
    ]
    for i, c in enumerate(comments[:15], 1):
        sample_lines.append(
            f"Comment {i}: author={c.get('author')} score={c.get('score')} is_op_marked={c.get('is_op_marked')}"
        )
    write_text_evidence(
        SCREENSHOTS / f"final_execution_{step}_comments.png",
        "Comment parsing evidence",
        sample_lines,
    )

    result = [{
        "username": post_meta["author"],
        "post_title": post_meta["title"],
        "count": count,
    }]

    step += 1
    write_agent_response(result, error_details=None, status="SUCCESS")
    log(f"step {step} action: wrote agent_response.json with retrieved_data={json.dumps(result, ensure_ascii=False)}")
    write_text_evidence(
        SCREENSHOTS / f"final_execution_{step}_final_response.png",
        "Final retrieved data",
        [json.dumps(result, ensure_ascii=False)],
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR: {e}")
        write_agent_response([], error_details=str(e), status="ERROR")
        raise
