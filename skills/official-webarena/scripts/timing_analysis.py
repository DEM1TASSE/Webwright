#!/usr/bin/env python3
"""How long the batch took, and how much of that was one chain waiting on itself.

Scope-serial scheduling trades wall clock for non-interference: chains run side by side, but
a chain is one task at a time, so the batch cannot finish before its longest chain does. This
prints what that cost, in a form that says whether a different partition would have helped.
"""
import json, pathlib, re, collections, datetime, sys

ROOT = pathlib.Path('/data/ww_official')

def load(root):
    out = {}
    for p in (ROOT/root).glob('*/task*.json'):
        try: out[int(re.search(r'task(\d+)', p.name).group(1))] = json.loads(p.read_text())
        except Exception: pass
    return out

def started(rec):
    rd = (rec.get('run') or {}).get('run_dir') or ''
    m = re.search(r'(\d{8}_\d{6})$', rd)
    return datetime.datetime.strptime(m.group(1), '%Y%m%d_%H%M%S') if m else None

def main():
    gen = load('mutate_results')
    groups = json.loads((ROOT/'partition/serial_groups.json').read_text())
    # Duration lives in the progress stream, not the result file; the last line for a task
    # wins, so a task re-run after a restart is counted once, at its final attempt.
    secs = {}
    prog = ROOT / 'mutate_progress.jsonl'
    if prog.is_file():
        for line in prog.read_text().splitlines():
            try: row = json.loads(line)
            except Exception: continue
            if isinstance(row.get('wall_seconds'), (int, float)) and 'task_id' in row:
                secs[row['task_id']] = row['wall_seconds']
    starts = {t: started(r) for t, r in gen.items()}
    starts = {t: s for t, s in starts.items() if s}
    if not starts:
        print("no timing data yet"); return
    t0, t1 = min(starts.values()), max(starts.values())
    tail = max((starts[t] + datetime.timedelta(seconds=secs.get(t, 0))) for t in starts)
    wall = (tail - t0).total_seconds()
    print(f"  Phase 1 墙钟   {wall/3600:6.2f} 小时   ({t0:%H:%M} → {tail:%H:%M})")
    print(f"  任务数         {len(gen)}   累计 CPU 时间 {sum(secs.values())/3600:.1f} 小时")
    print(f"  平均并发       {sum(secs.values())/wall:6.2f}   (上限 24)")

    print("\n  每条链的串行下界（该链所有任务耗时之和）")
    chain = []
    for name, ids in groups.items():
        s = sum(secs.get(i, 0) for i in ids)
        n = sum(1 for i in ids if i in secs)
        chain.append((s, n, len(ids), name))
    chain.sort(reverse=True)
    for s, n, tot, name in chain[:8]:
        print(f"    {name[:44]:<44} {n:3d}/{tot:<3d} 任务  下界 {s/3600:5.2f} 小时")
    longest = chain[0][0]
    print(f"\n  最长链下界 {longest/3600:.2f} 小时 = 墙钟的 {longest/wall:.0%}")
    if longest / wall > 0.8:
        others = sum(c[0] for c in chain[1:]) / 3600
        print(f"  → 墙钟由这一条链决定。其余 {len(chain)-1} 条链合计仅 {others:.1f} 小时的工作，")
        print(f"    在它跑完之前早已空转；拆分这一条是唯一能缩短批次的手段。")
    else:
        print("  → 墙钟不由单一条链决定，并发上限或任务耗时才是瓶颈。")

    print("\n  最长链的构成")
    top = chain[0][3]
    for i in groups[top][:6]:
        print(f"    task{i:<5} {secs.get(i,0):5.0f}s")
    print(f"    ... 共 {len(groups[top])} 个")

main()
