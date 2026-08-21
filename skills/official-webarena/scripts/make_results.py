#!/usr/bin/env python3
"""Per-domain results for the full 812, under every scoring framing, with micro and macro means.

Domains follow WebArena-Verified's own reporting convention: a task touching more than one site
is its own category ("Multi-site"), not attributed to whichever site happens to come first. That
convention is checkable -- Verified's documentation counts 48 multi-site tasks of which 19 involve
Map, and this partition reproduces both numbers exactly.

Micro is the pooled rate (every task weighs the same). Macro is the unweighted mean over domains
(every domain weighs the same), which is what a table of per-domain rates implies when read as a
row of equals; the two come apart here because Reddit-mutate is large and weak while Wikipedia is
small, so both are reported rather than one.
"""
import json, pathlib, re, collections

ROOT = pathlib.Path('/data/ww_official')
LABEL = {'shopping': 'Shopping', 'shopping_admin': 'Shopping Admin', 'gitlab': 'GitLab',
         'reddit': 'Reddit', 'map': 'Map', 'wikipedia': 'Wikipedia'}
ORDER = ['Shopping', 'Shopping Admin', 'GitLab', 'Reddit', 'Map', 'Wikipedia', 'Multi-site']


def load(root):
    return {int(re.search(r'task(\d+)', p.name).group(1)): json.loads(p.read_text())
            for p in (ROOT / root).glob('*/task*.json')}


def main():
    tasks = {t['task_id']: t for t in
             json.loads((ROOT / 'webarena_official/config_files/test.raw.json').read_text())}
    nm, mu, rp = load('nonmutate_results'), load('mutate_results'), load('mutate_results_replay')

    def domain(tid):
        sites = tasks[tid]['sites']
        return 'Multi-site' if len(sites) > 1 else LABEL.get(sites[0], sites[0])

    inline = lambda r: (r.get('evaluation') or {}).get('score') == 1.0
    def replay(tid):
        return (((rp.get(tid, {}).get('replay') or {}).get('evaluation') or {}).get('score'))

    # ① inline  ② replay as-is (no scorable state counts as failure)
    # ③ cumulative-write corrected: replay's verdict wherever it has one, inline where the script
    #    produced nothing -- a script that does not reproduce is an artifact defect, not evidence
    #    that the agent failed the task.
    # ④ best-of-2 upper bound: appendix only, and not comparable to any single-episode baseline.
    rows = []
    for tid, r in nm.items():
        rows.append(dict(d=domain(tid), lane='non-mutate', a=inline(r), b=inline(r),
                         c=inline(r), m=inline(r)))
    for tid, r in mu.items():
        i, v = inline(r), replay(tid)
        rows.append(dict(d=domain(tid), lane='mutate', a=i, b=(v == 1.0),
                         c=(v == 1.0) if v is not None else i, m=(i or v == 1.0)))

    def table(keep, key, title):
        g = collections.defaultdict(lambda: [0, 0])
        for r in rows:
            if keep(r):
                g[r['d']][0] += 1
                g[r['d']][1] += bool(r[key])
        if not g:
            return None
        lines = [f"| Domain | N | Correct | Rate |", "|:--|--:|--:|--:|"]
        rates = []
        for d in ORDER:
            if d not in g:
                continue
            n, ok = g[d]
            rates.append(ok / n)
            lines.append(f"| {d} | {n} | {ok} | {ok/n:.1%} |")
        N = sum(v[0] for v in g.values())
        OK = sum(v[1] for v in g.values())
        lines.append(f"| **Micro (pooled)** | **{N}** | **{OK}** | **{OK/N:.1%}** |")
        lines.append(f"| **Macro (domain mean)** | {len(rates)} domains | — | **{sum(rates)/len(rates):.1%}** |")
        return f"### {title}\n\n" + "\n".join(lines) + "\n"

    out = ["# WebArena 812 — 分域结果",
           "",
           "Webwright (gpt-5.4) × 官方 WebArena `web-arena-x/webarena@dce04686`，全部 812 题。",
           "非 mutate 438 题跑实例 2（并行）；mutate 374 题跑实例 1（按写入作用域分 103 条链，链内串行），",
           "跑完重置实例 1 后按序重放一次。两条 lane 全程不共享部署。",
           "",
           "域的划分follow WebArena-Verified：跨站点任务自成一类，不摊回单站点。",
           "该口径可核对——Verified 文档记 48 个 multi-site、其中 19 个涉及 Map，本划分两个数都对上。",
           "",
           "**Micro** = 汇总率（每个任务等权）。**Macro** = 各域率的无权平均（每个域等权）。",
           "两者在此分开是因为 Reddit-mutate 又大又弱、Wikipedia 又小，加权方式会改变结论。",
           "",
           "---",
           "",
           "## ① inline —— 主表",
           "",
           "agent 这一集跑完后的站点状态。WebArena 协议本身，与所有 baseline 同源。",
           ""]
    out.append(table(lambda r: True, 'a', '全部 812'))
    out.append(table(lambda r: r['lane'] == 'non-mutate', 'a', '非 mutate 438'))
    out.append(table(lambda r: r['lane'] == 'mutate', 'a', 'mutate 374'))

    out += ["---", "", "## ② replay 原样 —— appendix", "",
            "冻结脚本从干净态独立重现。64 个未产出可评产物的任务一律计 0，",
            "因此它比 ① 低的部分**混入了脚本可重现性**，不单纯是累加写。非 mutate 不做重放，沿用 inline。", ""]
    out.append(table(lambda r: True, 'b', '全部 812'))
    out.append(table(lambda r: r['lane'] == 'mutate', 'b', 'mutate 374'))

    out += ["---", "", "## ③ 累加写修正 —— appendix", "",
            "重放能判的以重放为准（310 题，不挑方向），判不了的回退 inline（64 题）。",
            "分母不变，只换掉门禁重跑这一个混淆。", ""]
    out.append(table(lambda r: True, 'c', '全部 812'))
    out.append(table(lambda r: r['lane'] == 'mutate', 'c', 'mutate 374'))

    out += ["---", "", "## ④ best-of-2 上界 —— appendix", "",
            "两次判定取高。**与任何单 episode 的 baseline 不可比**，仅作上界。",
            "它对同一证据源两面取用：重放有利时采信，不利时丢弃。", ""]
    out.append(table(lambda r: True, 'm', '全部 812'))
    out.append(table(lambda r: r['lane'] == 'mutate', 'm', 'mutate 374'))

    out += ["---", "", "## 四种口径汇总（micro）", "",
            "| 口径 | mutate 374 | 全 812 |", "|:--|--:|--:|"]
    for key, name in (('a', '① inline（主表）'), ('b', '② replay 原样'),
                      ('c', '③ 累加写修正'), ('m', '④ best-of-2 上界')):
        m_ok = sum(1 for r in rows if r['lane'] == 'mutate' and r[key])
        t_ok = sum(1 for r in rows if r[key])
        out.append(f"| {name} | {m_ok}/374 = {m_ok/374:.1%} | {t_ok}/812 = {t_ok/812:.1%} |")
    out += ["",
            "分域表**只在 ① 上解读**。单域翻转样本仅 1–5 个，③ 在分域层面是噪声级抖动",
            "（Shopping 的 mutate 从 38 降到 37，只因该域恰有一个向下翻转 task434 而无向上翻转）。",
            ""]
    (pathlib.Path('/data/demiwang/results/webarena/webwright-full812/RESULTS.md')
     .write_text("\n".join(x for x in out if x is not None) + "\n"))
    print("wrote RESULTS.md")


main()
