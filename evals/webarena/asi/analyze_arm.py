#!/usr/bin/env python3
"""Cross-arm summary for the ASI library arm.

Library usage is detected by FUNCTION NAME, not by a marker comment: the prompt never asks the
agent to record its usage, because asking presupposes usage and usage rate is what this arm
measures. The 28 induced names are distinctive enough that a name hit is a real hit.

Reports per site and per task type: solved, steps, timed out, and -- for the asi arm -- how many
tasks referenced the library at all, which is the statistic that carries independently of any
accuracy delta.
"""
import argparse, ast, json, re, sys
from collections import defaultdict
from pathlib import Path

LIB = Path('/data/demiwang/results/webarena/ww_asi/library')
ASI_ACTIONS = Path('/home/t-demiwang/agent-skill-induction/asi/runs/cross_template_lib')


def induced_names():
    names = {}
    for f in sorted(ASI_ACTIONS.glob('*.py')):
        if f.name == '__init__.py':
            continue
        for node in ast.parse(f.read_text()).body:
            if isinstance(node, ast.FunctionDef):
                names[node.name] = f.stem
    return names


def scan_run(run_dir: Path, names) -> dict:
    text = []
    for p in [run_dir / 'final_script.py', *sorted((run_dir / 'steps').glob('*.sh'))]:
        try:
            text.append(p.read_text(errors='replace'))
        except OSError:
            pass
    blob = '\n'.join(text)
    hits = sorted(n for n in names if re.search(rf'\b{re.escape(n)}\b', blob))
    return {"library_names_used": hits,
            # A BARE call only. `page.locator(...).select_option('1')` is ordinary Playwright
            # selecting an option by value and must not count as a copied AXTree bid, so any
            # call reached through an attribute (`.select_option`) is excluded.
            "bid_style_call": bool(re.search(
                r"(?<![.\w])(click|fill|hover|select_option)\(\s*['\"]\d+['\"]", blob)),
            "get_by_test_id": 'get_by_test_id' in blob}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--results-root', required=True)
    ap.add_argument('--runs-root')
    ap.add_argument('--arm', required=True)
    a = ap.parse_args()
    names = induced_names()
    rows = []
    for rp in sorted(Path(a.results_root).rglob(f'task*_{a.arm}.json')):
        try:
            r = json.loads(rp.read_text())
        except (OSError, ValueError):
            continue
        tid = r.get('task_id')
        row = {"task_id": tid, "site": rp.parent.name, "correct": r.get('correct'),
               "steps": r.get('steps'), "timed_out": r.get('timed_out'),
               "status": r.get('run_status') or r.get('status')}
        if a.runs_root:
            cand = sorted(Path(a.runs_root).rglob(f'task{tid}_{a.arm}_*'))
            if cand:
                row.update(scan_run(cand[-1], names))
        rows.append(row)

    by_site = defaultdict(lambda: {"n": 0, "correct": 0, "timeout": 0, "used": 0, "steps": []})
    for r in rows:
        s = by_site[r['site']]
        s['n'] += 1
        s['correct'] += bool(r.get('correct'))
        s['timeout'] += bool(r.get('timed_out'))
        s['used'] += bool(r.get('library_names_used'))
        if r.get('steps'):
            s['steps'].append(r['steps'])
    print(f"{'site':16s} {'n':>4s} {'solved':>7s} {'rate':>7s} {'timeout':>8s} {'used lib':>9s} {'med steps':>10s}")
    tot = defaultdict(int); allsteps = []
    for site in sorted(by_site):
        s = by_site[site]
        med = sorted(s['steps'])[len(s['steps'])//2] if s['steps'] else 0
        allsteps += s['steps']
        for k in ('n', 'correct', 'timeout', 'used'): tot[k] += s[k]
        print(f"{site:16s} {s['n']:4d} {s['correct']:7d} {s['correct']/s['n']*100:6.1f}% "
              f"{s['timeout']:8d} {s['used']:9d} {med:10d}")
    med = sorted(allsteps)[len(allsteps)//2] if allsteps else 0
    print(f"{'TOTAL':16s} {tot['n']:4d} {tot['correct']:7d} "
          f"{tot['correct']/max(tot['n'],1)*100:6.1f}% {tot['timeout']:8d} {tot['used']:9d} {med:10d}")

    used = [r for r in rows if r.get('library_names_used')]
    if used:
        cnt = defaultdict(int)
        for r in used:
            for n in r['library_names_used']: cnt[n] += 1
        print('\nfunctions referenced:')
        for n, c in sorted(cnt.items(), key=lambda x: -x[1]):
            print(f'  {n:44s} x{c}  ({names[n]})')
    else:
        print('\nfunctions referenced: none')
    bid = sum(bool(r.get('bid_style_call')) for r in rows)
    tid_ = sum(bool(r.get('get_by_test_id')) for r in rows)
    print(f"\nbid-style calls copied verbatim: {bid} tasks | get_by_test_id attempts: {tid_} tasks")
    out = Path(a.results_root).parent / f'analysis_{a.arm}.json'
    out.write_text(json.dumps(rows, indent=2) + '\n')
    print('per-task ->', out)


if __name__ == '__main__':
    sys.exit(main())
