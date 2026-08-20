#!/usr/bin/env python3
"""Separate what the agent could not do from what the harness broke.

Two scores per mutating task: inline, measured on the site the generation run left behind,
and replay, measured on a freshly reset site with the frozen script executed exactly once.
They disagree in two directions, and each direction names a cause.

Idempotent tasks are the control. Re-executing "set the price to 42" three times leaves the
price at 42, so for them the two scores should agree; whatever gap remains there is task
difficulty, not mechanism. The gap that appears only on non-idempotent tasks is the mechanism.
"""
import json, pathlib, re, collections

ROOT = pathlib.Path('/data/ww_official')
REL = re.compile(r'\b(by \$?\d|by \d+%|reduce .* by|increase .* by)\b', re.I)
CREATE = re.compile(r'\b(create|add|post|submit|open a|start a|make a|draft|leave a|reply'
                    r'|comment|invite|assign|fork|upload)\b', re.I)


def kind(task):
    if REL.search(task['intent']): return '非幂等·相对量'
    if CREATE.search(task['intent']): return '非幂等·创建追加'
    return '幂等'


def load(root):
    out = {}
    for p in (ROOT / root).glob('*/task*.json'):
        try: out[int(re.search(r'task(\d+)', p.name).group(1))] = json.loads(p.read_text())
        except Exception: pass
    return out


def main():
    tasks = {t['task_id']: t for t in
             json.loads((ROOT / 'webarena_official/config_files/test.raw.json').read_text())}
    gen, rep = load('mutate_results'), load('mutate_results_replay')
    if not rep:
        print("  replay 结果尚不存在"); return

    rows = []
    for tid, g in gen.items():
        r = rep.get(tid)
        inline = (g.get('evaluation') or {}).get('score')
        replay = (((r or {}).get('replay') or {}).get('evaluation') or {}).get('score')
        rstatus = ((r or {}).get('replay') or {}).get('status')
        rd = (g.get('run') or {}).get('run_dir')
        runs = len(list((pathlib.Path(rd) / 'final_runs').glob('run_*'))) \
            if rd and (pathlib.Path(rd) / 'final_runs').is_dir() else 0
        rows.append(dict(tid=tid, kind=kind(tasks[tid]), inline=inline, replay=replay,
                         rstatus=rstatus, runs=runs, site=g.get('run', {}).get('run_dir', '')))

    scored = [r for r in rows if r['replay'] is not None]
    n = len(rows)
    oi = sum(1 for r in rows if r['inline'] == 1.0)
    orp = sum(1 for r in scored if r['replay'] == 1.0)
    print(f"  mutate {n} 个")
    print(f"    inline 通过 {oi}/{n} = {oi/n:.1%}")
    print(f"    replay 通过 {orp}/{len(scored)} = {orp/len(scored):.1%}"
          f"   (另有 {n-len(scored)} 个重放未产出可评状态)")

    print("\n  inline × replay 一致性")
    cell = collections.Counter((r['inline'] == 1.0, r['replay'] == 1.0) for r in scored)
    print(f"    都过              {cell[(True,True)]:4d}")
    print(f"    inline过 replay挂 {cell[(True,False)]:4d}   脚本硬编码了跑时读到的值")
    print(f"    inline挂 replay过 {cell[(False,True)]:4d}   门禁重跑把状态写坏了")
    print(f"    都挂              {cell[(False,False)]:4d}   agent 确实没做成")

    print("\n  按幂等性分解（对照组 = 幂等，重放对它们本应等价）")
    print(f"  {'类别':<16}{'N':>5}{'inline':>9}{'replay':>9}{'差':>8}{'重跑率':>9}")
    base = None
    for k in ('幂等', '非幂等·创建追加', '非幂等·相对量'):
        sub = [r for r in scored if r['kind'] == k]
        if not sub: continue
        a = sum(1 for r in sub if r['inline'] == 1.0) / len(sub)
        b = sum(1 for r in sub if r['replay'] == 1.0) / len(sub)
        m = sum(1 for r in sub if r['runs'] > 1) / len(sub)
        print(f"  {k:<14}{len(sub):>5}{a:>9.1%}{b:>9.1%}{b-a:>+8.1%}{m:>9.1%}")
        if k == '幂等': base = b - a
    if base is not None:
        print(f"\n  幂等组的变化 {base:+.1%} 是重放本身带来的噪声下界；")
        print(f"  非幂等组超出这个下界的部分，才是门禁重跑造成的评测损失。")

    print("\n  重放执行状态")
    for k, v in collections.Counter(r['rstatus'] for r in rows).most_common():
        print(f"    {str(k):<20} {v}")

    flip = sorted(r['tid'] for r in scored if r['inline'] != 1.0 and r['replay'] == 1.0)
    drop = sorted(r['tid'] for r in scored if r['inline'] == 1.0 and r['replay'] != 1.0)
    print(f"\n  重放救回 {len(flip)} 个: {flip[:30]}")
    print(f"  重放暴露 {len(drop)} 个: {drop[:30]}")


main()
