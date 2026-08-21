#!/usr/bin/env python3
"""A 50/50 split of WebArena's templates: half to build a skill library from, half never seen.

The unit is the template, not the task. Every instance of a template lands on the same side, so
a library built on the train half has never met the test half's phrasing -- splitting by task
would leak, since instances of one template differ only in their parameters.

Balance is enforced per stratum rather than globally. A single 50/50 draw over all 190 templates
can leave GitLab or Map lopsided, and a library evaluated on a test half that is short of one
site measures site coverage as much as it measures reuse. Strata are (site, task_type), and
inside each one templates are dealt to whichever side currently holds fewer *tasks*, largest
template first, so both the template count and the task count come out even.

Two labelling details, both checked rather than assumed:

  task_type   WebArena Verified annotates it per task, and five templates come back mixed --
              "Buy the highest rated product ...", "Add the following users ... as {{role}}",
              "Open an issue ...", "Like/DisLike all submissions ..." have some instances marked
              retrieve and the rest mutate, for the same operation. The template takes the
              majority label, overridden to mutate when the intent's leading verb writes.

  site        one template (42, "path and travel time from {{city1}} to {{city2}}") has two
              instances on map alone and two on map plus shopping_admin. The template is keyed
              by the union of its instances' sites, which puts it in Multi-site.
"""
import argparse, collections, json, os, pathlib, random

ROOT = pathlib.Path(os.environ.get('WEBARENA_HARNESS_ROOT', '/data/ww_official'))
VERIFIED = pathlib.Path(os.environ.get(
    'WEBARENA_VERIFIED_JSON',
    '/home/t-demiwang/Code-Web-Agent/webarena-verified/assets/dataset/webarena-verified.json'))
LABEL = {'shopping': 'Shopping', 'shopping_admin': 'ShopAdmin', 'gitlab': 'GitLab',
         'reddit': 'Reddit', 'map': 'Map', 'wikipedia': 'Wiki'}
SITES = ['Shopping', 'ShopAdmin', 'GitLab', 'Reddit', 'Map', 'Wiki', 'Multi']
TYPES = ['retrieve', 'navigate', 'mutate']
WRITE_VERB = None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--out', default=str(pathlib.Path(__file__).resolve().parent.parent / 'splits'),
                    help='defaults to the splits/ directory beside this skill')
    args = ap.parse_args()

    import importlib.util, sys
    spec = importlib.util.spec_from_file_location(
        'pt', ROOT / 'webwright/skills/official-webarena/scripts/partition_tasks.py')
    pt = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, ['x']
    try:
        spec.loader.exec_module(pt)
    except SystemExit:
        pass
    sys.argv = argv

    tasks = json.loads((ROOT / 'webarena_official/config_files/test.raw.json').read_text())
    by_id = {t['task_id']: t for t in tasks}
    verified = {t['task_id']: t for t in json.loads(VERIFIED.read_text())}

    def task_type(tid):
        for e in (verified[tid].get('eval') or []):
            x = e.get('expected')
            if isinstance(x, dict) and x.get('task_type'):
                return x['task_type']
        return 'retrieve'

    templates = collections.defaultdict(list)
    for t in tasks:
        templates[t['intent_template_id']].append(t['task_id'])
    for ids in templates.values():
        ids.sort()

    meta = {}
    for tid, ids in templates.items():
        sites = set()
        for i in ids:
            sites |= set(by_id[i]['sites'])
        site = 'Multi' if len(sites) > 1 else LABEL.get(next(iter(sites)), next(iter(sites)))
        counts = collections.Counter(task_type(i) for i in ids)
        kind = counts.most_common(1)[0][0]
        if any(pt.writes_despite_annotation(by_id[i]) for i in ids):
            kind = 'mutate'
        meta[tid] = {'site': site, 'type': kind, 'n': len(ids)}

    rng = random.Random(args.seed)
    strata = collections.defaultdict(list)
    for tid, m in meta.items():
        strata[(m['site'], m['type'])].append(tid)

    train_t, test_t = [], []
    for key in sorted(strata):
        group = strata[key]
        rng.shuffle(group)
        # Largest template first, each one dealt to the side currently holding fewer tasks in
        # this stratum. Alternating by template alone would balance the counts and not the sizes.
        group.sort(key=lambda t: -meta[t]['n'])
        load = [0, 0]
        for tid in group:
            side = 0 if load[0] <= load[1] else 1
            (train_t if side == 0 else test_t).append(tid)
            load[side] += meta[tid]['n']
    train_t, test_t = sorted(train_t), sorted(test_t)

    train = sorted(i for t in train_t for i in templates[t])
    test = sorted(i for t in test_t for i in templates[t])
    assert not (set(train) & set(test)) and len(train) + len(test) == 812

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'cross_template.json').write_text(json.dumps(
        {'train': train, 'test': test, 'train_templates': train_t, 'test_templates': test_t,
         'seed': args.seed, 'unit': 'intent_template_id',
         'stratified_by': ['site', 'task_type'],
         'template_meta': {str(k): v for k, v in sorted(meta.items())}}, indent=1) + '\n')
    (out / 'cross_template_train_ids.json').write_text(json.dumps(train) + '\n')
    (out / 'cross_template_test_ids.json').write_text(json.dumps(test) + '\n')

    def cell(ids, pred):
        return sum(1 for i in ids if pred(i))

    print(f"  按 template 50/50 分层划分  seed {args.seed}\n")
    print(f"    {'':<12}{'train模板':>10}{'test模板':>10}{'train题':>9}{'test题':>8}{'test占比':>10}")
    print(f"    {'合计':<10}{len(train_t):>10}{len(test_t):>10}{len(train):>9}{len(test):>8}"
          f"{len(test)/812:>10.1%}")
    print()
    print(f"    {'site':<12}{'train模板':>10}{'test模板':>10}{'train题':>9}{'test题':>8}{'test占比':>10}")
    for s in SITES:
        a = [t for t in train_t if meta[t]['site'] == s]
        b = [t for t in test_t if meta[t]['site'] == s]
        if not a and not b:
            continue
        na = sum(meta[t]['n'] for t in a); nb = sum(meta[t]['n'] for t in b)
        print(f"    {s:<12}{len(a):>10}{len(b):>10}{na:>9}{nb:>8}{nb/(na+nb):>10.1%}")
    print()
    print(f"    {'task_type':<12}{'train模板':>10}{'test模板':>10}{'train题':>9}{'test题':>8}{'test占比':>10}")
    for k in TYPES:
        a = [t for t in train_t if meta[t]['type'] == k]
        b = [t for t in test_t if meta[t]['type'] == k]
        na = sum(meta[t]['n'] for t in a); nb = sum(meta[t]['n'] for t in b)
        print(f"    {k:<12}{len(a):>10}{len(b):>10}{na:>9}{nb:>8}{nb/(na+nb):>10.1%}")


main()
