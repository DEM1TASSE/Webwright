#!/usr/bin/env python3
"""A deliberately loosened re-match of the same expectation, run alongside the
official one. Deterministic -- no model, no judge.

The official NetworkEventEvaluator anchors on the exact request the site's own UI
produces. A code-as-action agent frequently reaches the same end state by a
different but equivalent request, and scores 0:

    expected  POST /f/space/subscribe.json
    actual    POST /f/space/subscribe            <- same action, no .json

    expected  POST .../set/9/back/edit   product[price]=38.25
    actual    POST .../set/9/           product[price]=38.25

Relaxed match keeps method and every expected post_data field, and keeps the
response in the same status class, but drops the anchors on the URL: a trailing
extension, extra or missing trailing segments, and the `$` end anchor.

Report both. Strict is the number that is comparable with everyone else's;
the strict/relaxed gap measures how much the trace anchor costs this agent.
"""
import json
import os
import re
import sys
from pathlib import Path

DATASET = os.environ.get("WA_DATASET", "")
CONFIG = os.environ.get("WA_CONFIG", "")


def site_urls():
    cfg = json.loads(Path(CONFIG).read_text())
    return {k: v["urls"][0].rstrip("/") for k, v in cfg["environments"].items()}


def expand(url_pattern, urls):
    out = str(url_pattern)
    for ph, base in urls.items():
        out = out.replace(ph, base)
    return out


def loosen(pattern):
    """Turn the expected URL into a pattern that tolerates equivalent shapes.

    Dataset urls come in two flavours: a literal, or a regex (starts with '^').
    Escaping a regex would destroy it, so the two are handled separately.
    """
    is_regex = pattern.startswith("^")
    body = pattern.rstrip("$")
    body = re.sub(r"(\\?\.)json$", "", body)      # .json variant of the same endpoint
    body = re.sub(r"/back/edit$", "", body)      # Magento form-action tail
    body = body.rstrip("/")
    if not is_regex:
        body = "^" + re.escape(body)
        body = body.replace(r"\.\*", ".*")        # keep any wildcards the literal had
    return body + r"(?:\.json)?/?(?:[^?#]*)?$"


def parse_body(body):
    """form-encoded or JSON -> flat dict of str -> str"""
    if not body:
        return {}
    body = str(body)
    if body.lstrip().startswith("{"):
        try:
            obj = json.loads(body)
            return {k: str(v) for k, v in obj.items()}
        except Exception:
            return {}
    from urllib.parse import parse_qsl, unquote_plus
    try:
        return {unquote_plus(k): unquote_plus(v) for k, v in parse_qsl(body)}
    except Exception:
        return {}


def status_class(a, b):
    if a is None or b is None:
        return True
    return a // 100 == b // 100


def relaxed_hit(spec, records, urls):
    want_urls = spec.get("url", "")
    want_urls = want_urls if isinstance(want_urls, list) else [want_urls]
    method = (spec.get("http_method") or "").upper()
    want_body = {k: str(v) for k, v in (spec.get("post_data") or {}).items() if v is not None}
    want_status = spec.get("response_status")

    pats = []
    for u in want_urls:
        try:
            pats.append(re.compile(loosen(expand(u, urls))))
        except re.error:
            pats.append(None)

    for r in records:
        if method and (r.get("method") or "").upper() != method:
            continue
        if not any(p and p.match(r.get("url", "")) for p in pats):
            continue
        body = parse_body(r.get("post_data"))
        if any(body.get(k) != v for k, v in want_body.items()):
            continue
        if not status_class(r.get("status"), want_status):
            continue
        return r
    return None


def main(task_id, rec_dir):
    task_id = int(task_id)
    task = next(t for t in json.loads(Path(DATASET).read_text()) if t["task_id"] == task_id)
    specs = [e["expected"] for e in task["eval"] if e.get("evaluator") == "NetworkEventEvaluator"]
    records = []
    for f in Path(rec_dir).glob("http_*.jsonl"):
        for line in f.read_text(errors="replace").splitlines():
            try:
                records.append(json.loads(line))
            except Exception:
                pass
    records.sort(key=lambda r: r.get("ts", 0))
    urls = site_urls()

    hits = [relaxed_hit(s, records, urls) for s in specs]
    ok = all(h is not None for h in hits) and bool(hits)
    print(f"task {task_id}  relaxed={'1.0' if ok else '0.0'}  ({sum(h is not None for h in hits)}/{len(hits)} specs matched)")
    for s, h in zip(specs, hits):
        u = s.get("url")
        u = u[0] if isinstance(u, list) else u
        if h:
            print(f"  MATCH  {str(u)[:66]}")
            print(f"      -> {h['method']} {h.get('status')} {h['url'].split('//')[-1].split('/',1)[-1][:66]}")
        else:
            print(f"  MISS   {str(u)[:66]}")
    return ok


if __name__ == "__main__":
    main(*sys.argv[1:])
