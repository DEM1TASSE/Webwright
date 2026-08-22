#!/usr/bin/env python3
"""Render the per-domain tables as box-drawn text, one per scoring framing."""
import json, pathlib, re, collections

ROOT = pathlib.Path('/data/ww_official')
LABEL = {'shopping':'Shopping','shopping_admin':'Shopping Admin','gitlab':'GitLab',
         'reddit':'Reddit','map':'Map','wikipedia':'Wikipedia'}
ORDER = ['Shopping','Shopping Admin','GitLab','Reddit','Map','Wikipedia','Multi-site']

def load(root):
    return {int(re.search(r'task(\d+)',p.name).group(1)): json.loads(p.read_text())
            for p in (ROOT/root).glob('*/task*.json')}

def box(rows, headers):
    w = [max(len(str(r[i])) for r in [headers]+rows) for i in range(len(headers))]
    def line(l,m,r): return l + m.join('─'*(x+2) for x in w) + r
    def row(cells, center=False):
        # Header centred; body rows keep the label flush left and every number flush right, so
        # a column of rates lines up on the decimal point rather than drifting with name length.
        out = [f" {str(c):^{w[i]}} " if center
               else (f" {str(c):<{w[i]}} " if i == 0 else f" {str(c):>{w[i]}} ")
               for i, c in enumerate(cells)]
        return '│'+'│'.join(out)+'│'
    s=[line('┌','┬','┐'), row(headers, center=True)]
    for r in rows:
        s.append(line('├','┼','┤')); s.append(row(r))
    s.append(line('└','┴','┘'))
    return '\n'.join(s)

def main():
    tasks={t['task_id']:t for t in json.loads((ROOT/'webarena_official/config_files/test.raw.json').read_text())}
    nm,mu,rp=load('nonmutate_results'),load('mutate_results'),load('mutate_results_replay')
    dom=lambda t: 'Multi-site' if len(tasks[t]['sites'])>1 else LABEL.get(tasks[t]['sites'][0],tasks[t]['sites'][0])
    inline=lambda r:(r.get('evaluation') or {}).get('score')==1.0
    rpl=lambda t:(((rp.get(t,{}).get('replay') or {}).get('evaluation') or {}).get('score'))
    recs=[]
    for t,r in nm.items():
        recs.append((dom(t),'non-mutate',inline(r),inline(r),inline(r),inline(r)))
    for t,r in mu.items():
        i,v=inline(r),rpl(t)
        recs.append((dom(t),'mutate',i,v==1.0,(v==1.0) if v is not None else i,(i or v==1.0)))
    IDX={'a':2,'b':3,'c':4,'m':5}
    def table(key, lane=None):
        g=collections.defaultdict(lambda:[0,0])
        for r in recs:
            if lane and r[1]!=lane: continue
            g[r[0]][0]+=1; g[r[0]][1]+=bool(r[IDX[key]])
        rows=[]; rates=[]
        for d in ORDER:
            if d not in g: continue
            n,ok=g[d]; rates.append(ok/n)
            rows.append([d,n,ok,f"{ok/n:.1%}"])
        N=sum(v[0] for v in g.values()); OK=sum(v[1] for v in g.values())
        rows.append(['Micro',N,OK,f"{OK/N:.1%}"])
        rows.append(['Macro',f"{len(rates)} domains",'—',f"{sum(rates)/len(rates):.1%}"])
        return box(rows,['Domain','N','Correct','Rate'])
    for key,name,note in (('a','① inline','主表。agent 这一集跑完后的站点状态'),
                          ('b','② replay 原样','冻结脚本从干净态重现;64 个未产出产物的计 0'),
                          ('c','③ 累加写修正','重放能判的以重放为准,判不了的回退 inline'),
                          ('m','④ best-of-2 上界','两次取高;与单 episode baseline 不可比')):
        print(f"\n{name} —— {note}\n")
        print(table(key))
main()
