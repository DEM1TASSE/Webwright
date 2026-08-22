#!/usr/bin/env python3
"""Freeze the exact prompt the ASI arm will emit, plus the hashes that detect drift.

Written as a file rather than run inline because the harness it reads from is edited by other
work: on 2026-08-21 cross_task_eval.py changed mid-run, OFFICIAL_RETRIEVE_SPEC was replaced by
OFFICIAL_FINAL_STATE_SPEC, and 151 already-finished retrieve tasks ended up split across two
output contracts. The hashes here are what makes that visible instead of silent, so re-running
this after any harness change -- and diffing the result -- is part of starting a run, not an
optional extra.
"""
import hashlib, json, re, sys
from pathlib import Path

REPO = Path('/home/t-demiwang/webwright-primitive-v12-cross-template')
EVALS = REPO / 'evals' / 'webarena'
ROOT = Path('/data/demiwang/results/webarena/ww_asi')
SPLITS = Path('/data/ww_official/webwright/skills/official-webarena/splits')
DATASET = Path('/data/ww_official/webarena_official/config_files/test.raw.json')
DEPLOY = Path('/data/ww_official/deployment_inst4.json')
sys.path.insert(0, str(EVALS))
from asi_hint import prepare_asi_hint, _RUNTIME_NOTE, _UPSTREAM_MANDATE  # noqa: E402

sha = lambda x: hashlib.sha256(x.encode()).hexdigest()
PH = {'shopping': '__SHOPPING__', 'shopping_admin': '__SHOPPING_ADMIN__', 'gitlab': '__GITLAB__',
      'reddit': '__REDDIT__', 'map': '__MAP__', 'wikipedia': '__WIKIPEDIA__'}


def storage_state_note(task, config):
    """Verbatim port of cross_task_eval.official_storage_state_note."""
    raw = task.get('storage_state')
    auth_root = config.get('auth_root')
    if not raw:
        return ''
    if not auth_root:
        raise SystemExit(f"task {task.get('task_id')} needs storage_state but deployment has no auth_root")
    path = Path(auth_root) / Path(str(raw)).name
    if not path.is_file():
        raise SystemExit(f"task {task.get('task_id')} needs missing auth state: {path}")
    return (
        f'\nYou are already signed in. Create every browser context with '
        f'`storage_state="{path.resolve()}"` \u2014 always, unconditionally, in exploration '
        'scripts and in the final script alike. Never branch on whether to pass it, and never '
        'log in by hand.'
    )


def const(src, name):
    """A spec constant may be a literal or `OTHER + \"\"\"...\"\"\"`; resolve both."""
    m = re.search(rf'^{name}\s*=\s*([A-Z_]+)\s*\+\s*r?"""(.*?)"""', src, re.S | re.M)
    if m:
        return const(src, m.group(1)) + m.group(2)
    m = re.search(rf'^{name}\s*=\s*r?"""(.*?)"""', src, re.S | re.M)
    return m.group(1) if m else None


def main():
    src = (EVALS / 'cross_task_eval.py').read_text()
    specs = {n: const(src, n) for n in
             ('ANSWER_SPEC', 'NAVIGATE_SPEC', 'VANILLA_FINAL_STATE_SPEC',
              'OFFICIAL_RETRIEVE_SPEC', 'OFFICIAL_FINAL_STATE_SPEC')}
    specs = {k: v for k, v in specs.items() if v is not None}
    official = specs.get('OFFICIAL_FINAL_STATE_SPEC') or specs.get('OFFICIAL_RETRIEVE_SPEC')
    if official is None:
        raise SystemExit('no official spec constant found in cross_task_eval.py')

    deploy_cfg = json.loads(DEPLOY.read_text())
    tasks = {t['task_id']: t for t in json.loads(DATASET.read_text())}
    ids = json.loads((SPLITS / 'cross_template_test_ids.json').read_text())
    dep = json.loads(DEPLOY.read_text())['environments']

    frz = ROOT / 'prompt_freeze'
    frz.mkdir(parents=True, exist_ok=True)
    for f in frz.glob('*'):
        f.unlink()

    seen, rendered = set(), {}
    for tid in ids:
        t = tasks[tid]
        combo = tuple(t['sites'])
        if combo in seen:
            continue
        seen.add(combo)
        url = t['start_url']
        for ph, cfg in dep.items():
            url = url.replace(ph, cfg['urls'][0])
        # cross_task_eval.py's official path hands the agent a pre-authenticated session
        # instead of credentials (official_storage_state_note); mirror it exactly, including
        # the resolved auth path, or the freeze compares against a prompt nobody emits.
        login = storage_state_note(t, deploy_cfg)
        # task_spec picks OFFICIAL_FINAL_STATE_SPEC first for task_source == official_webarena,
        # so NAVIGATE_SPEC is unreachable on this dataset -- every one of the 399 is official.
        is_nav = 'string_match' not in (t.get('eval', {}).get('eval_types') or [])
        spec = official
        prompt = (prepare_asi_hint(t['sites'])['hint'] + '\n'
                  + f"Complete this web task.\n\nGoal: {t['intent']}\nStart URL: {url}{login}"
                  + spec)
        name = '+'.join(combo)
        (frz / f'{name}__task{tid}.txt').write_text(prompt)
        rendered[name] = {'example_task_id': tid,
                          'task_type': 'navigate' if is_nav else 'retrieve',
                          'spec': ('OFFICIAL_FINAL_STATE_SPEC'
                                   if 'OFFICIAL_FINAL_STATE_SPEC' in specs
                                   else 'OFFICIAL_RETRIEVE_SPEC'),
                          'chars': len(prompt), 'sha256': sha(prompt)}

    out = {
        'arm': 'asi',
        'frozen_for': 'cross_template TEST (399), WebArena instance 4',
        'harness': 'webwright evals/webarena/cross_task_eval.py @ primitive-v12-cross-template-run',
        'deployment': str(DEPLOY),
        'auth': 'plaintext credentials in the prompt; this path never uses storage_state',
        'hint_template': {'heading': '## Site action library', 'runtime_note': _RUNTIME_NOTE,
                          'upstream_mandate': _UPSTREAM_MANDATE,
                          'body': 'frozen describe(True, True) block, fenced as ```python'},
        'verbatim_from_asi': [
            'custom_action_set.py describe() output in full, incl. the trailing multiaction '
            'sentence (agent.py:88 sets multiaction=True)',
            'agent.py:263 mandate sentence; its unbalanced quoting is preserved',
            "site order follows the dataset, matching ASI's sites_for() which does not sort "
            '(run_official.py:44)'],
        'deviations_from_asi': [
            'dropped agent.py:264-272: two chain-of-thought examples and "Only wrap the '
            'to-be-executed action in triple backticks" -- they teach ASI\'s emission format, '
            "which contradicts Webwright's JSON+bash contract",
            'added one sentence: bids are per-render AXTree indices this runtime does not '
            'resolve. The only non-upstream text in the hint',
            'wikipedia has no ASI action module; wikipedia+map tasks receive the map block only',
            'no marker request and no usage-json request (unlike the primitive arm): asking '
            'presupposes usage, and usage rate is what this arm measures. Reuse is detected by '
            'function name',
            "the shared task spec is whatever cross_task_eval.py currently selects; it is hashed "
            'here so a harness-side change to it cannot enter a run unnoticed'],
        'hashes': {'asi_hint.py': sha((EVALS / 'asi_hint.py').read_text()),
                   'cross_task_eval.py': sha(src),
                   **{k: sha(v) for k, v in specs.items()},
                   'library_MANIFEST.json': sha((ROOT / 'library' / 'MANIFEST.json').read_text())},
        'rendered_examples': rendered,
    }
    (ROOT / 'PROMPT_FREEZE.json').write_text(json.dumps(out, indent=2, ensure_ascii=False) + '\n')
    for k, v in rendered.items():
        print(f"{k:24s} task{v['example_task_id']:<5d} {v['spec']:26s} {v['chars']:6d}")
    print('\nspecs found:', ', '.join(sorted(specs)))
    print('->', ROOT / 'PROMPT_FREEZE.json')


if __name__ == '__main__':
    main()
