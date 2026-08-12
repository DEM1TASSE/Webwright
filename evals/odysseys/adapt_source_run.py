#!/usr/bin/env python3
"""Adapt one judged multi-site Odysseys run into reviewable site evidence.

The adapter is deliberately conservative. It discovers sites from executed URLs, associates
screenshots/actions, proposes rubric mappings, and emits per-site source excerpts. Ambiguous
mappings stay in ``needs_review`` and cannot be consumed by the library builder.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlparse

from site_primitives import canonical_site


URL_RE = re.compile(r"https?://[^\s\]\[(){}<>\"']+")
IGNORED_HOSTS = {"google.com", "www.google.com", "localhost", "127.0.0.1"}
SITE_ALIASES = {
    "google_maps": ("google maps", "maps", "route", "directions"),
    "reddit_com": ("reddit", "subreddit", "r/"),
    "cnn_com": ("cnn",),
    "irs_gov": ("irs", "gift tax"),
    "dfas_mil": ("dfas", "survivor benefit", "sbp"),
    "frac_org": ("frac", "snap", "shutdown"),
    "boredpanda_com": ("bored panda",),
    "wikipedia_org": ("wikipedia",),
    "hulu_com": ("hulu",),
    "memory_alpha_fandom_com": ("memory alpha",),
}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def completed_run(workspace: str | Path) -> Path:
    runs = sorted((Path(workspace) / "final_runs").glob("run_*"))
    successful = []
    for run in runs:
        try:
            label = load_json(run / "self_reflect_result.json").get("predicted_label")
        except (OSError, ValueError):
            label = None
        if label in (1, True) and (run / "final_script.py").is_file():
            successful.append(run)
    if successful:
        return successful[-1]
    valid = [run for run in runs if (run / "final_script.py").is_file()]
    if not valid:
        raise ValueError(f"no final run in {workspace}")
    return valid[-1]


def urls_in_text(text: str) -> list[str]:
    return [value.rstrip(".,;:") for value in URL_RE.findall(text)]


def site_for_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host == "maps.google.com" or (
        host in {"google.com", "www.google.com"}
        and (parsed.path == "/maps" or parsed.path.startswith("/maps/"))
    ):
        return "google_maps"
    if not host or host in IGNORED_HOSTS or host.endswith("googleusercontent.com"):
        return None
    # Accessible Reddit frontends remain evidence about reddit.com, not a new library site.
    if host == "reddit.com" or host.endswith(".reddit.com") or host in {
        "safereddit.com", "redlib.catsarch.com",
    }:
        return "reddit_com"
    if host == "r.jina.ai":
        nested = re.search(r"/(?:https?://)([^/]+)", url)
        if not nested or nested.group(1) in {"http:", "https:"}:
            return None
        return site_for_url("https://" + nested.group(1))
    for suffix, site in {
        "boredpanda.com": "boredpanda_com", "cnn.com": "cnn_com",
        "irs.gov": "irs_gov", "dfas.mil": "dfas_mil",
        "wikipedia.org": "wikipedia_org", "hulu.com": "hulu_com",
        "memory-alpha.fandom.com": "memory_alpha_fandom_com",
    }.items():
        if host == suffix or host.endswith("." + suffix):
            return site
    if host[0].isdigit():
        host = "site." + host
    return canonical_site(host)


def site_code_ranges(script_lines: list[str], site: str, urls: list[str]) -> list[tuple[int, int]]:
    """Locate both URL declarations and the Playwright block that executes them.

    Final scripts commonly declare ``YT_URL`` near the top, then use it much later in a
    dedicated ``yt = await context.new_page()`` block.  Token windows around the declaration
    alone are not executable evidence, so trace URL constants into ``page.goto(...)`` and keep
    the corresponding page block through the next page creation.
    """
    tokens = set(SITE_ALIASES.get(site, ()))
    tokens.update((urlparse(url).hostname or "").lower() for url in urls)
    url_vars: set[str] = set()
    for line in script_lines:
        match = re.match(r"^\s*([A-Za-z_]\w*)\s*=\s*(['\"])(https?://.+?)\2\s*$", line)
        if match and site_for_url(match.group(3)) == site:
            url_vars.add(match.group(1))

    selected: list[tuple[int, int]] = []
    for number, line in enumerate(script_lines, start=1):
        if any(token and token in line.lower() for token in tokens):
            selected.append((max(1, number - 2), min(len(script_lines), number + 3)))

        goto = re.search(r"\b([A-Za-z_]\w*)\.goto\((.*)", line)
        if not goto:
            continue
        page, args = goto.groups()
        direct_urls = urls_in_text(args)
        targets_site = any(site_for_url(url) == site for url in direct_urls)
        targets_site = targets_site or any(re.search(rf"\b{re.escape(var)}\b", args)
                                           for var in url_vars)
        if not targets_site:
            continue

        start = number
        for previous in range(number - 1, 0, -1):
            candidate = script_lines[previous - 1]
            if re.search(rf"^\s*{re.escape(page)}\s*=\s*await\s+.*new_page\(", candidate):
                start = previous
                break
            if re.search(rf"\b{re.escape(page)}\.goto\(", candidate):
                break
        end = len(script_lines)
        base_indent = len(script_lines[start - 1]) - len(script_lines[start - 1].lstrip())
        for following in range(number + 1, len(script_lines) + 1):
            candidate = script_lines[following - 1]
            indent = len(candidate) - len(candidate.lstrip())
            new_page = re.match(r"^\s*([A-Za-z_]\w*)\s*=\s*await\s+.*new_page\(", candidate)
            if new_page and new_page.group(1) != page and indent == base_indent:
                end = following - 1
                break
            next_goto = re.search(rf"\b{re.escape(page)}\.goto\((.*)", candidate)
            if next_goto:
                next_urls = urls_in_text(next_goto.group(1))
                if next_urls and not any(site_for_url(url) == site for url in next_urls):
                    end = following - 1
                    break
        selected.append((start, end))

    merged: list[tuple[int, int]] = []
    for lo, hi in sorted(selected):
        if merged and lo <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def discover_site_evidence(run_dir: str | Path) -> dict[str, dict]:
    run = Path(run_dir)
    log = (run / "final_script_log.txt").read_text(encoding="utf-8", errors="ignore")
    script = (run / "final_script.py").read_text(encoding="utf-8", errors="ignore")
    by_site: dict[str, dict] = {}
    for line_number, line in enumerate(log.splitlines(), start=1):
        sites = {site_for_url(url) for url in urls_in_text(line)} - {None}
        for site in sites:
            item = by_site.setdefault(site, {"urls": [], "action_lines": [], "screenshots": []})
            for url in urls_in_text(line):
                if site_for_url(url) == site and url not in item["urls"]:
                    item["urls"].append(url)
            item["action_lines"].append({"line": line_number, "text": line})
    # Include URL constants from the executed final artifact. These are code evidence only until
    # review; action-log URLs remain separately attributable above.
    for url in urls_in_text(script):
        site = site_for_url(url)
        if not site:
            continue
        item = by_site.setdefault(site, {"urls": [], "action_lines": [], "screenshots": []})
        if url not in item["urls"]:
            item["urls"].append(url)
    for shot in sorted((run / "screenshots").glob("*.png")):
        name = shot.stem.lower().replace("_", " ")
        matches = []
        for site in by_site:
            fallback = site.split("_")[0]
            tokens = SITE_ALIASES.get(site, (fallback,) if len(fallback) >= 3 else ())
            if any(token in name for token in tokens):
                matches.append(site)
        if len(matches) == 1:
            by_site[matches[0]]["screenshots"].append(str(shot))
    script_lines = script.splitlines()
    for site, item in by_site.items():
        merged = site_code_ranges(script_lines, site, item["urls"])
        item["code_ranges"] = merged
        item["code_excerpt"] = "\n\n".join(
            f"# source lines {lo}-{hi}\n" + "\n".join(script_lines[lo - 1:hi])
            for lo, hi in merged
        )
    return by_site


def propose_rubric_mapping(task: dict, sites: dict[str, dict]) -> dict[str, list[str]]:
    mapping = {site: [] for site in sites}
    for rubric_id, rubric in (task.get("rubrics") or {}).items():
        text = " ".join((str(rubric.get("requirement") or ""),
                         str(rubric.get("verification") or ""))).lower()
        matches = []
        for site in sites:
            aliases = SITE_ALIASES.get(site, (site.replace("_", " "), site.split("_")[0]))
            if any(alias in text for alias in aliases):
                matches.append(site)
        if len(matches) == 1:
            mapping[matches[0]].append(str(rubric_id))
    return mapping


def adapt(task: dict, run_dir: str | Path, judge_results: str | Path,
          output: str | Path, *, approvals: dict | None = None) -> dict:
    task_id = str(task["task_id"])
    judge = next((row for row in load_json(judge_results).get("tasks", [])
                  if str(row.get("task_id")) == task_id), None)
    if judge is None:
        raise ValueError(f"judge result missing for {task_id}")
    scores = {str(key): int(value) for key, value in (judge.get("rubric_scores") or {}).items()}
    evidence = discover_site_evidence(run_dir)
    proposed = propose_rubric_mapping(task, evidence)
    approvals = approvals or {}
    root = Path(output) / task_id
    root.mkdir(parents=True, exist_ok=True)
    script_lines = (Path(run_dir) / "final_script.py").read_text(
        encoding="utf-8", errors="ignore").splitlines()
    segments = []
    for number, (site, item) in enumerate(sorted(evidence.items()), start=1):
        override = approvals.get(site) or {}
        rubric_ids = [str(x) for x in override.get("rubric_ids", proposed.get(site, []))]
        template_id = str(override.get("template_id") or "")
        approved = override.get("review_status") == "approved"
        rubric_passed = bool(rubric_ids) and all(scores.get(rid) == 1 for rid in rubric_ids)
        if "code_ranges" in override:
            reviewed_ranges = []
            for value in override["code_ranges"]:
                if (not isinstance(value, list) or len(value) != 2
                        or not all(isinstance(x, int) for x in value)):
                    raise ValueError(f"invalid reviewed code range for {site}: {value!r}")
                lo, hi = value
                if lo < 1 or hi < lo or hi > len(script_lines):
                    raise ValueError(f"reviewed code range out of bounds for {site}: {value!r}")
                reviewed_ranges.append((lo, hi))
            item["code_ranges"] = reviewed_ranges
            item["code_excerpt"] = "\n\n".join(
                f"# source lines {lo}-{hi}\n" + "\n".join(script_lines[lo - 1:hi])
                for lo, hi in reviewed_ranges
            )
        code_path = root / f"{site}.source_excerpt.py"
        code_path.write_text(item["code_excerpt"] or "# no site-specific code located\n",
                             encoding="utf-8")
        segment = {
            "segment_id": f"S{number}", "site": site,
            "goal": str(override.get("goal") or ""), "template_id": template_id,
            "rubric_ids": rubric_ids, "required_fields": override.get("required_fields") or [],
            "rubric_scores": {rid: scores.get(rid) for rid in rubric_ids},
            "rubric_passed": rubric_passed,
            "review_status": "approved" if approved else "needs_review",
            "admitted": bool(approved and rubric_passed and template_id and item["code_excerpt"]),
            "urls": item["urls"], "action_lines": item["action_lines"],
            "screenshots": item["screenshots"], "code_ranges": item["code_ranges"],
            "code_path": str(code_path),
        }
        segments.append(segment)
    payload = {"task_id": task_id, "run_dir": str(run_dir), "judge_results": str(judge_results),
               "segments": segments}
    (root / "adapter_review.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_id")
    parser.add_argument("--tasks", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--judge-results", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--approvals", help="Reviewed site mapping JSON keyed by canonical site")
    args = parser.parse_args(argv)
    tasks = {str(row["task_id"]): row for row in load_json(args.tasks)}
    if args.task_id not in tasks:
        raise SystemExit(f"unknown task_id: {args.task_id}")
    run = completed_run(args.workspace)
    approvals = load_json(args.approvals) if args.approvals else None
    result = adapt(tasks[args.task_id], run, args.judge_results, args.output,
                   approvals=approvals)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
