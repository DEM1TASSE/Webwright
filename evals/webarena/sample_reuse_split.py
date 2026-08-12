#!/usr/bin/env python3
"""Build the retrieve-only split for the reuse-radius study.

A single fixed train/test split. Templates are partitioned once per site:

    TRAIN templates   their build solves feed both libraries
                        workflow library  -- one skill per train template that has
                                             enough distinct instances to align
                        primitive library -- site-level capabilities across all
                                             train templates
                      train templates that are deep enough also reserve instances
                      as T1 held-out

    TEST templates    disjoint from TRAIN, never touch either library

Two radii, one library pair:

    T1   unseen *instance* of a TRAIN template   arms: scratch | +workflow
    T2   unseen *template* (a TEST template)     arms: scratch | +workflow | +primitive

The workflow arm on T2 is the ablation that is expected to fail: a whole-task
skill built for template A should not transfer to template B. If the primitive arm
beats it, the reusable unit is the decomposed capability, not the whole solution.

Build solves must be *distinct instances*: distillation finds parameters by
aligning solves whose values differ, so re-running one instance adds no parameter
evidence (it only helps get past the gold gate).

Effective sample size is the number of templates, not tasks -- a skill either fits
a template's shape or it does not, so instances of one template win or lose
together.

Usage:
  sample_reuse_split.py <dataset.json> --out split.json [--md summary.md]
                        [--seed 20260812] [--prev-splits DIR] [--test-per-site 10]
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


def build(tasks, seed, prev_used, test_per_site, reserve_deep):
    by_site = collections.defaultdict(lambda: collections.defaultdict(list))
    for t in retrieve_only(tasks):
        by_site[",".join(sorted(t["sites"]))][t["intent_template_id"]].append(t)

    train, test = {}, {}
    for site in sorted(by_site):
        tpls = by_site[site]

        # Deep templates are the only ones that can yield a workflow skill and a T1
        # held-out, so they are reserved for TRAIN before TEST is drawn. TEST then
        # prefers templates earlier splits never touched.
        deep = sorted((k for k, v in tpls.items() if len(v) >= MAX_BUILD + 1),
                      key=lambda k: -len(tpls[k]))
        # never let the reserve swallow a whole site -- reddit has only 4 retrieve
        # templates, and reserving 8 left it with nothing to test on
        keep = min(reserve_deep, max(1, len(tpls) // 2))
        reserved = set(deep[:keep])
        cand = [k for k in tpls if k not in reserved]
        fresh = stable([k for k in cand if k not in prev_used], seed, lambda k: f"{site}:te:{k}")
        seen = stable([k for k in cand if k in prev_used], seed, lambda k: f"{site}:te:{k}")
        test_tpls = (fresh + seen)[:min(test_per_site, max(0, len(tpls) - keep))]
        train_tpls = [k for k in sorted(tpls) if k not in test_tpls]

        train_rows = []
        for tpl in train_tpls:
            b, h = split_instances(tpls[tpl], seed, tpl)
            has_skill = len(b) >= MAX_BUILD
            train_rows.append({
                "intent_template_id": tpl,
                "n_instances": len(tpls[tpl]),
                "build_task_ids": [x["task_id"] for x in b],
                "feeds": ["primitive"] + (["workflow"] if has_skill else []),
                "workflow_skill": has_skill,
                "t1_heldout_task_ids": [x["task_id"] for x in h] if has_skill else [],
                "unseen_in_earlier_splits": tpl not in prev_used,
            })
        train[site] = train_rows

        test[site] = [{
            "intent_template_id": tpl,
            "n_instances": len(tpls[tpl]),
            "t2_task_ids": [x["task_id"] for x in
                            stable(tpls[tpl], seed, lambda t: f"{tpl}:{t['task_id']}")[:MAX_HELDOUT]],
            "unseen_in_earlier_splits": tpl not in prev_used,
        } for tpl in test_tpls]

    return {
        "schema_version": 4,
        "seed": seed,
        "task_type": "retrieve",
        "design": {
            "split": "fixed train/test over templates, per site",
            "workflow_library": "one skill per TRAIN template with >= %d distinct build instances" % MAX_BUILD,
            "primitive_library": "site-level, from the build solves of all TRAIN templates",
            "t1": "unseen instance of a TRAIN template -- arms: scratch | +workflow",
            "t2": "unseen TEST template -- arms: scratch | +workflow | +primitive",
            "t2_workflow_arm": "ablation expected to fail: a whole-task skill should not transfer across templates",
            "effective_sample_unit": "template",
        },
        "train": train,
        "test": test,
    }


def validate(split, tasks):
    by_id = {t["task_id"]: t for t in tasks}
    errs = []
    for site in split["train"]:
        tr = {r["intent_template_id"] for r in split["train"][site]}
        te = {r["intent_template_id"] for r in split["test"][site]}
        if tr & te:
            errs.append(f"{site}: train and test templates overlap: {sorted(tr & te)}")
        build_ids, eval_ids = set(), set()
        for r in split["train"][site]:
            if set(r["build_task_ids"]) & set(r["t1_heldout_task_ids"]):
                errs.append(f"{site} tpl{r['intent_template_id']}: task both builds and evaluates")
            build_ids |= set(r["build_task_ids"])
            eval_ids |= set(r["t1_heldout_task_ids"])
            if r["workflow_skill"] and len(r["build_task_ids"]) < MAX_BUILD:
                errs.append(f"{site} tpl{r['intent_template_id']}: skill claimed with too few solves")
        for r in split["test"][site]:
            eval_ids |= set(r["t2_task_ids"])
        if build_ids & eval_ids:
            errs.append(f"{site}: overlap between build and eval tasks: {sorted(build_ids & eval_ids)[:5]}")
        for tid in build_ids | eval_ids:
            t = by_id.get(tid)
            if t is None:
                errs.append(f"task {tid} missing from dataset")
            elif {e.get("evaluator") for e in t["eval"]} != {"AgentResponseEvaluator"}:
                errs.append(f"task {tid} is not retrieve-only")
    return errs


def summarise(split):
    L=[]; add=L.append
    d=split["design"]
    add("# Reuse-radius split (retrieve only, fixed train/test)\n")
    for k in ("split","workflow_library","primitive_library","t1","t2","t2_workflow_arm"):
        add(f"- **{k}**: {d[k]}")
    add(f"- effective sample unit: **{d['effective_sample_unit']}**\n")

    add("## TRAIN (builds both libraries)\n")
    add("| site | templates | build runs | workflow skills | T1 templates | T1 tasks |")
    add("|---|---:|---:|---:|---:|---:|")
    tot=collections.Counter()
    for site in sorted(split["train"]):
        rows=split["train"][site]
        b=sum(len(r["build_task_ids"]) for r in rows)
        sk=sum(1 for r in rows if r["workflow_skill"])
        t1t=sum(1 for r in rows if r["t1_heldout_task_ids"])
        t1k=sum(len(r["t1_heldout_task_ids"]) for r in rows)
        add(f"| {site} | {len(rows)} | {b} | {sk} | {t1t} | {t1k} |")
        tot.update(tpl=len(rows),build=b,skill=sk,t1tpl=t1t,t1=t1k)
    add(f"| **total** | **{tot['tpl']}** | **{tot['build']}** | **{tot['skill']}** | "
        f"**{tot['t1tpl']}** | **{tot['t1']}** |\n")

    add("## TEST (never touches a library)\n")
    add("| site | templates | T2 tasks | fresh |")
    add("|---|---:|---:|---:|")
    for site in sorted(split["test"]):
        rows=split["test"][site]
        k=sum(len(r["t2_task_ids"]) for r in rows)
        fr=sum(1 for r in rows if r["unseen_in_earlier_splits"])
        add(f"| {site} | {len(rows)} | {k} | {fr} |")
        tot.update(t2tpl=len(rows),t2=k,fresh=fr)
    add(f"| **total** | **{tot['t2tpl']}** | **{tot['t2']}** | **{tot['fresh']}** |\n")

    add("## Clusters and runs\n")
    add(f"- T1: **{tot['t1tpl']} templates** / {tot['t1']} tasks -- scratch vs +workflow")
    add(f"- T2: **{tot['t2tpl']} templates** / {tot['t2']} tasks -- scratch vs +workflow vs +primitive")
    runs = tot['build'] + tot['t1']*2 + tot['t2']*3
    add(f"- runs: {tot['build']} build + {tot['t1']}x2 + {tot['t2']}x3 = **{runs}**\n")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--out", default="reuse_split.json")
    ap.add_argument("--md", default="")
    ap.add_argument("--seed", default="20260812")
    ap.add_argument("--prev-splits", default="")
    ap.add_argument("--test-per-site", type=int, default=10)
    ap.add_argument("--reserve-deep", type=int, default=8,
                    help="deepest templates per site kept in TRAIN so skills and T1 exist")
    a = ap.parse_args()

    tasks = json.loads(Path(a.dataset).read_text())
    split = build(tasks, a.seed, previously_used(a.prev_splits), a.test_per_site, a.reserve_deep)
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
