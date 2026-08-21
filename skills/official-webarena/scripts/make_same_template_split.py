#!/usr/bin/env python3
"""The same-template split: hold out unseen *instances* of templates the library has seen.

The held-out unit is the instance, so one split covers every eligible template at once -- a
template can supply training and test instances at the same time without leaking, because the
instances differ only in their parameters. Cross-template lives in make_cross_template_split.py,
where the unit is the template and the construction is necessarily different.

Instances for the same-template train set are drawn at random rather than taken in task-id order.
Order is not neutral -- on this run the first three instances of a template pass 57.8% and the
rest 54.0%, so taking the head hands the tier a test set 3.8 points harder than its train set and
understates generalisation by construction. There is no monotone trend behind it (positions two
and three score highest), so it is an artefact of instantiation order, which is exactly what a
seeded draw removes.

A template needs at least four instances to appear here: three go to training, so a smaller one
has nothing left to hold out. Smaller templates are not lost -- they take part in the
cross-template tier, where the unit is the template rather than the instance.
"""
import argparse, collections, json, os, pathlib, random

ROOT = pathlib.Path(os.environ.get('WEBARENA_HARNESS_ROOT', '/data/ww_official'))
LABEL = {'shopping': 'Shopping', 'shopping_admin': 'ShopAdmin', 'gitlab': 'GitLab',
         'reddit': 'Reddit', 'map': 'Map', 'wikipedia': 'Wiki'}
ORDER = ['Shopping', 'ShopAdmin', 'GitLab', 'Reddit', 'Map', 'Multi']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--budget', default='3',
                    help="same-template train instances per template: an integer, or a fraction "
                         "like 0.6 for a proportional split")
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--out', default=str(pathlib.Path(__file__).resolve().parent.parent / 'splits'),
                    help='defaults to the splits/ directory beside this skill')
    args = ap.parse_args()

    frac = '.' in args.budget
    budget = float(args.budget) if frac else int(args.budget)
    tasks = json.loads((ROOT / 'webarena_official/config_files/test.raw.json').read_text())
    by_id = {t['task_id']: t for t in tasks}
    mutating = set(json.loads((ROOT / 'partition/serial_ids.json').read_text()))
    dom = lambda i: ('Multi' if len(by_id[i]['sites']) > 1
                     else LABEL.get(by_id[i]['sites'][0], by_id[i]['sites'][0]))

    templates = collections.defaultdict(list)
    for t in tasks:
        templates[t['intent_template_id']].append(t['task_id'])
    for ids in templates.values():
        ids.sort()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    # ---- T1: instance-level hold-out, every eligible template, instances drawn at random ----
    t1_train, t1_test, kept_templates = [], [], []
    for tid, ids in sorted(templates.items()):
        k = max(1, round(len(ids) * budget)) if frac else budget
        if len(ids) < k + 1:          # a template must keep at least one instance to hold out
            continue
        pick = rng.sample(ids, k)
        t1_train += pick
        t1_test += [i for i in ids if i not in set(pick)]
        kept_templates.append(tid)
    (out / 'same_template.json').write_text(json.dumps(
        {'tier': 'same_template', 'train': sorted(t1_train), 'test': sorted(t1_test),
         'templates': kept_templates, 'budget': args.budget, 'seed': args.seed,
         'selection': 'random within template'}, indent=1) + '\n')

    def line(name, ids):
        c = collections.Counter(dom(i) for i in ids)
        m = sum(1 for i in ids if i in mutating)
        tpl = len({by_id[i]['intent_template_id'] for i in ids})
        return (f"    {name:<26}{len(ids):>5}{tpl:>6}{m:>8}"
                + ''.join(f"{c.get(d, 0):>10}" for d in ORDER))

    head = f"    {'集合':<24}{'N':>5}{'模板':>6}{'mutate':>8}" + ''.join(f"{d:>10}" for d in ORDER)
    print(f"  T1 same-template  预算 {args.budget}/模板,模板内随机取,seed {args.seed}\n{head}")
    print(line('train', t1_train)); print(line('test', t1_test))
    print(f"\n    模板 {len(kept_templates)}   train {len(t1_train)}   test {len(t1_test)}")


main()
