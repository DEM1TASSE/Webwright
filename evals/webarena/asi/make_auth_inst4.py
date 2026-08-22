#!/usr/bin/env python3
"""Regenerate the Official WebArena storage_state files for instance 4.

Needed because cross_task_eval.py's official path now resolves `storage_state` through
`official_auth_state()`, which raises when the file is missing -- and because
`replica.sh reset` drops the server-side sessions while leaving any existing file on disk
looking perfectly valid (lanes.md section 6 step 4: the failure shows up as an
element-not-found timeout, not an auth error).

Runs the combinations SERIALLY. auto_login.main() fans out over a ThreadPoolExecutor and
never calls .result(), so a browser that fails to launch under load is swallowed and the
run reports success having written nothing.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

AUTH_ROOT = Path("/data/ww_official/.auth_inst4")
WA_ROOT = Path("/data/ww_official/webarena_official")
# auto_login imports browser_env, which needs numpy/gymnasium; the webwright venv has neither.
LOGIN_PYTHON = Path("/home/t-demiwang/agent-skill-induction/.venv/bin/python")
DEPLOYMENT = Path("/data/ww_official/deployment_inst4.json")

COMBOS = [["shopping"], ["shopping_admin"], ["reddit"], ["gitlab"], ["gitlab", "reddit"]]
PLACEHOLDER = {"SHOPPING": "__SHOPPING__", "SHOPPING_ADMIN": "__SHOPPING_ADMIN__",
               "REDDIT": "__REDDIT__", "GITLAB": "__GITLAB__", "WIKIPEDIA": "__WIKIPEDIA__",
               "MAP": "__MAP__", "HOMEPAGE": "__HOMEPAGE__"}


def site_env():
    env = dict(os.environ)
    environments = json.loads(DEPLOYMENT.read_text())["environments"]
    for var, key in PLACEHOLDER.items():
        urls = (environments.get(key) or {}).get("urls") or []
        if urls:
            env[var] = urls[0]
    env["PYTHONPATH"] = str(WA_ROOT)
    return env


def main():
    AUTH_ROOT.mkdir(parents=True, exist_ok=True)
    stale = sorted(AUTH_ROOT.glob("*_state.json"))
    for path in stale:
        path.unlink()
    if stale:
        print(f"removed {len(stale)} stale state files (a reset invalidated them server-side)")
    env = site_env()
    failed = []
    for combo in COMBOS:
        name = ".".join(sorted(combo)) + "_state.json"
        script = ("from browser_env.auto_login import renew_comb;"
                  f"renew_comb({sorted(combo)!r}, auth_folder={str(AUTH_ROOT)!r})")
        started = time.monotonic()
        proc = subprocess.run([str(LOGIN_PYTHON), "-c", script], cwd=str(WA_ROOT), env=env,
                              capture_output=True, text=True, timeout=600)
        path = AUTH_ROOT / name
        ok = proc.returncode == 0 and path.is_file() and path.stat().st_size > 0
        print(f"{name:34s} {'ok' if ok else 'FAILED':6s} {time.monotonic() - started:5.1f}s"
              f"{'' if ok else '  ' + (proc.stderr or proc.stdout).strip()[-300:]}")
        if not ok:
            failed.append(name)
    print()
    for path in sorted(AUTH_ROOT.glob("*_state.json")):
        print(f"  {path.name:34s} {path.stat().st_size:6d} bytes")
    if failed:
        print(f"\nFAILED: {failed}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
