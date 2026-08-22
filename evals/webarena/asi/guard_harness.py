#!/usr/bin/env python3
"""Fail loudly if the harness changes while a run is in flight.

On 2026-08-21 cross_task_eval.py was edited mid-run: 15 tasks crashed in the transition
window and 151 finished retrieve tasks ended up split across two output contracts. Nothing
in the pipeline noticed -- the split was found afterwards by hashing. This watches the files
whose hashes PROMPT_FREEZE.json pins and prints one line per divergence, so the same thing
cannot happen silently twice.
"""
import hashlib, json, sys, time
from pathlib import Path

FREEZE = Path('/data/demiwang/results/webarena/ww_asi/PROMPT_FREEZE.json')
EVALS = Path('/home/t-demiwang/webwright-primitive-v12-cross-template/evals/webarena')
WATCH = ['cross_task_eval.py', 'asi_hint.py']
LIB = Path('/data/demiwang/results/webarena/ww_asi/library/MANIFEST.json')


def digest(p):
    try:
        return hashlib.sha256(p.read_text().encode()).hexdigest()
    except OSError:
        return None


def main():
    pinned = json.loads(FREEZE.read_text())['hashes']
    reported = set()
    while True:
        for name in WATCH:
            cur = digest(EVALS / name)
            if cur != pinned.get(name) and name not in reported:
                reported.add(name)
                print(f'HARNESS DRIFT: {name} no longer matches PROMPT_FREEZE.json '
                      f'({pinned.get(name, "?")[:12]} -> {(cur or "missing")[:12]}) '
                      f'-- results after this point are not comparable', flush=True)
        cur = digest(LIB)
        if cur != pinned.get('library_MANIFEST.json') and 'library' not in reported:
            reported.add('library')
            print('HARNESS DRIFT: library MANIFEST.json changed -- the injected block moved',
                  flush=True)
        time.sleep(20)


if __name__ == '__main__':
    sys.exit(main())
