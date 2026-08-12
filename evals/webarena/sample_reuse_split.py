#!/usr/bin/env python3
"""Build the retrieve-only split for the reuse-radius study.

Two libraries, measured at two radii, from one corpus of solves.

    workflow library   one parameterized skill per template, distilled from that
                       template's own solves. Only ever useful on the template it
                       came from, so it is measured with a fixed split.

    primitive library  site-level acquisition capabilities distilled across
                       templates. Measured leave-one-template-out: for held-out
                       template X the library is rebuilt from every other template
                       on that site, so X is genuinely unseen.

Leave-one-out is affordable because collecting solves costs agent runs while
*building* a library from solves already collected is offline distillation. Every
template therefore serves as both source and held-out without being spent.

Per template the instances are divided once:

    build instances    -> solves that feed the libraries (gold-gated, retryable)
    heldout instances  -> never enter any library; evaluated under all arms

Arms on each held-out instance:

    scratch      no library
    +workflow    only where the template has its own skill  -> T1 (same template)
    +primitive   library built without this template        -> T2 (unseen template)

The scratch arm is shared between the two comparisons, so T1 and T2 are paired
against the same baseline runs.

Effective sample size is the number of *templates*, not tasks: a skill either fits
a template's shape or it does not, so instances of one template win or lose
together.

Usage:
  sample_reuse_split.py <dataset.json> --out split.json [--md summary.md]
                        [--seed 20260812] [--prev-splits DIR] [--t1-per-site 4]
"""
import argparse
import collections
import hashlib
import json
import glob
import os
from pathlib import Path

MAX_BUILD = 3        # solves per template that feed the workflow library
MAX_HELDOUT = 2      # instances reserved for evaluation


def retrieve_only(tasks):
    return [t for t in tasks
            if {e.get("evaluator") for e in t.get("eval", [])} == {"AgentResponseEvaluator"}]


def previously_used(prev_dir):
    used = set()
    for f in glob.glob(os.path.join(prev_dir or "", "*.json")):
        if "manifest" in os.path.basename(f):
            continue
        try:
            j = json.loads(Path(f).read_text())
        except Exception:
            continue
        for key in ("train", "test", "source", "heldout"):
            v = j.get(key)
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, dict) and "intent_template_id" in x:
                        used.add(x["intent_template_id"])
            elif isinstance(v, dict):
                used.update(v.get("intent_template_ids", []))
    return used


def stable(items, seed, key):
    return sorted(items, key=lambda x: hashlib.sha256(f"{seed}:{key(x)}".encode()).hexdigest())


def split_instances(insts, seed, tpl):
    """build vs heldout. A template with one instance can only build."""
    ordered = stable(insts, seed, lambda t: f"{tpl}:{t['task_id']}")
    n = len(ordered)
    if n == 1:
        return [ordered[0]], []
    heldout_n = min(MAX_HELDOUT, n - 1)
    build_n = min(MAX_BUILD, n - heldout_n)
    return ordered[:build_n], ordered[build_n:build_n + heldout_n]


def build(tasks, seed, prev_used, t1_per_site):
    by_site = collections.defaultdict(lambda: collections.defaultdict(list))
    for t in retrieve_only(tasks):
        by_site[",".join(sorted(t["sites"]))][t["intent_template_id"]].append(t)

    corpus, t1, folds = {}, {}, []
    fold_id = 0
    for site in sorted(by_site):
        tpls = by_site[site]
        rows = []
        for tpl in sorted(tpls):
            b, h = split_instances(tpls[tpl], seed, tpl)
            rows.append({
                "intent_template_id": tpl,
                "n_instances": len(tpls[tpl]),
                "build_task_ids": [x["task_id"] for x in b],
                "heldout_task_ids": [x["task_id"] for x in h],
                "unseen_in_earlier_splits": tpl not in prev_used,
            })
        corpus[site] = rows

        # workflow skills: deep templates only -- distillation needs several solves
        # of the same template to align, and 2 instances must stay held out
        deep = [r for r in rows
                if len(r["build_task_ids"]) >= MAX_BUILD and len(r["heldout_task_ids"]) >= 1]
        chosen = stable(deep, seed, lambda r: f"{site}:t1:{r['intent_template_id']}")[:t1_per_site]
        t1[site] = [{
            "intent_template_id": r["intent_template_id"],
            "library": "workflow",
            "build_task_ids": r["build_task_ids"],
            "heldout_task_ids": r["heldout_task_ids"],
            "arms": ["scratch", "workflow"],
            "measures": "T1 same-template reuse: unseen instance of a template whose own skill is in the library",
        } for r in chosen]

        # primitive library, leave one template out
        all_tpls = [r["intent_template_id"] for r in rows]
        for r in rows:
            if not r["heldout_task_ids"]:
                continue                       # nothing to evaluate on
            fold_id += 1
            folds.append({
                "fold_id": fold_id,
                "site": site,
                "library": "primitive",
                "heldout_template": r["intent_template_id"],
                "heldout_task_ids": r["heldout_task_ids"],
                "library_from_templates": [x for x in all_tpls if x != r["intent_template_id"]],
                "arms": ["scratch", "primitive"],
                "measures": "T2 cross-template reuse: template unseen by this fold's library",
            })

    return {
        "schema_version": 3,
        "seed": seed,
        "task_type": "retrieve",
        "design": {
            "workflow_library": "per template, from that template's build solves; fixed split; measures T1",
            "primitive_library": "per site, from build solves of every template except the held-out one; leave-one-template-out; measures T2",
            "arms": ["scratch", "workflow (T1 only)", "primitive (T2, fold-specific library)"],
            "note": "the scratch arm is shared, so T1 and T2 are paired against the same baseline runs",
            "effective_sample_unit": "template",
        },
        "solve_corpus": corpus,
        "t1_fixed_split": t1,
        "t2_leave_one_out_folds": folds,
    }


def validate(split, tasks):
    by_id = {t["task_id"]: t for t in tasks}
    errs = []
    for site, rows in split["solve_corpus"].items():
        for r in rows:
            if set(r["build_task_ids"]) & set(r["heldout_task_ids"]):
                errs.append(f"{site} tpl{r['intent_template_id']}: a task both builds and evaluates")
            for tid in r["build_task_ids"] + r["heldout_task_ids"]:
                t = by_id.get(tid)
                if t is None:
                    errs.append(f"task {tid} missing from dataset")
                elif {e.get("evaluator") for e in t["eval"]} != {"AgentResponseEvaluator"}:
                    errs.append(f"task {tid} is not retrieve-only")
    build_of = {}
    for site, rows in split["solve_corpus"].items():
        for r in rows:
            build_of[(site, r["intent_template_id"])] = set(r["build_task_ids"])
    for f in split["t2_leave_one_out_folds"]:
        if f["heldout_template"] in f["library_from_templates"]:
            errs.append(f"fold {f['fold_id']}: held-out template is in its own library")
        leaked = set(f["heldout_task_ids"]) & build_of.get((f["site"], f["heldout_template"]), set())
        if leaked:
            errs.append(f"fold {f['fold_id']}: held-out task also builds: {sorted(leaked)}")
    for site, rows in split["t1_fixed_split"].items():
        for r in rows:
            if set(r["build_task_ids"]) & set(r["heldout_task_ids"]):
                errs.append(f"t1 {site} tpl{r['intent_template_id']}: overlap")
    return errs


def summarise(split):
    lines = []
    add = lines.append
    add("# Reuse-radius split (retrieve only)\n")
    d = split["design"]
    add(f"- workflow library: {d['workflow_library']}")
    add(f"- primitive library: {d['primitive_library']}")
    add(f"- {d['note']}")
    add(f"- effective sample unit: **{d['effective_sample_unit']}**\n")

    add("## Solve corpus (what to run to build the libraries)\n")
    add("| site | templates | build runs | held-out tasks | fresh templates |")
    add("|---|---:|---:|---:|---:|")
    tot = collections.Counter()
    for site in sorted(split["solve_corpus"]):
        rows = split["solve_corpus"][site]
        b = sum(len(r["build_task_ids"]) for r in rows)
        h = sum(len(r["heldout_task_ids"]) for r in rows)
        fresh = sum(1 for r in rows if r["unseen_in_earlier_splits"])
        add(f"| {site} | {len(rows)} | {b} | {h} | {fresh} |")
        tot.update(tpl=len(rows), build=b, held=h, fresh=fresh)
    add(f"| **total** | **{tot['tpl']}** | **{tot['build']}** | **{tot['held']}** | **{tot['fresh']}** |\n")

    add("## T1 — same-template reuse (fixed split, workflow library)\n")
    add("| site | templates | held-out tasks |")
    add("|---|---:|---:|")
    t1t = t1k = 0
    for site in sorted(split["t1_fixed_split"]):
        rows = split["t1_fixed_split"][site]
        h = sum(len(r["heldout_task_ids"]) for r in rows)
        add(f"| {site} | {len(rows)} | {h} |")
        t1t += len(rows); t1k += h
    add(f"| **total** | **{t1t}** | **{t1k}** |\n")
    add(f"Arms: `scratch` vs `+workflow`. Clusters: **{t1t} templates**.\n")

    add("## T2 — cross-template reuse (leave-one-template-out, primitive library)\n")
    folds = split["t2_leave_one_out_folds"]
    per_site = collections.Counter(f["site"] for f in folds)
    add("| site | folds | held-out tasks | library built from |")
    add("|---|---:|---:|---|")
    for site in sorted(per_site):
        sf = [f for f in folds if f["site"] == site]
        h = sum(len(f["heldout_task_ids"]) for f in sf)
        add(f"| {site} | {len(sf)} | {h} | {len(sf[0]['library_from_templates'])} other templates |")
    hk = sum(len(f["heldout_task_ids"]) for f in folds)
    add(f"| **total** | **{len(folds)}** | **{hk}** | |\n")
    add(f"Arms: `scratch` vs `+primitive`. Clusters: **{len(folds)} templates**. "
        f"Each fold needs its own offline library build ({len(folds)} distillations, no browser).\n")

    add("## Run budget\n")
    add(f"- collect solves: **{tot['build']}** agent runs (gold-gated; failures may be retried "
        f"on the same instance, since build material is not held out)")
    add(f"- scratch arm: **{tot['held']}** runs (shared by T1 and T2)")
    add(f"- workflow arm: **{t1k}** runs")
    add(f"- primitive arm: **{hk}** runs")
    add(f"- **total agent runs: {tot['build'] + tot['held'] + t1k + hk}**, "
        f"plus {len(folds)} offline library builds\n")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--out", default="reuse_split.json")
    ap.add_argument("--md", default="")
    ap.add_argument("--seed", default="20260812")
    ap.add_argument("--prev-splits", default="")
    ap.add_argument("--t1-per-site", type=int, default=4)
    a = ap.parse_args()

    tasks = json.loads(Path(a.dataset).read_text())
    split = build(tasks, a.seed, previously_used(a.prev_splits), a.t1_per_site)
    errs = validate(split, tasks)
    md = summarise(split)
    print(md)
    if errs:
        print("VALIDATION FAILED")
        for e in errs:
            print("  -", e)
        raise SystemExit(1)
    print("validation: ok")
    Path(a.out).write_text(json.dumps(split, indent=1))
    print(f"-> {a.out}")
    if a.md:
        Path(a.md).write_text(md)
        print(f"-> {a.md}")


if __name__ == "__main__":
    main()
