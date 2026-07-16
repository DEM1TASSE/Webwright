"""learn — the friendly entry: turn a folder of finished runs into library skills.

    python -m webwright.skill_factory learn <runs_dir> [--library ./library] [--golds golds.json]
                                     [--chunk 25] [--dry-run]

No manifest to write. For every run dir under <runs_dir> it reads task.json (task text,
start_url) and agent_response.json (the answer), gates it (gold if --golds has this
task_id, else self_verify), asks the LLM ONCE per chunk to group tasks into templates and
extract per-task params, then feeds the groups to evolve. Idempotent: processed run dirs
are remembered in <library>/.learned.json and skipped next time. The generated manifest
of each chunk is saved next to the ledger for auditing.
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from .gate import gate
from .library import Library
from .llm import llm_json
from .update import Trace, evolve


def infer_schema(answer):
    """Mechanically derive output_schema from the answer's shape."""
    if isinstance(answer, list):
        item = answer[0] if answer else ""
        t = ("number" if isinstance(item, (int, float)) and not isinstance(item, bool)
             else "object" if isinstance(item, dict) else "string")
        return {"type": "array", "items": {"type": t}}
    if isinstance(answer, (int, float)) and not isinstance(answer, bool):
        return {"type": "number"}
    if isinstance(answer, dict):
        return {"type": "object"}
    return {"type": "string"}


def collect_runs(runs_dir: Path, ledger: dict):
    """[{dir, task_id, task, start_url, answer}] for finished runs not yet learned."""
    out = []
    skipped_no_answer = 0
    for d in sorted(Path(runs_dir).iterdir()):
        if not d.is_dir() or str(d.resolve()) in ledger["runs"]:
            continue
        tj, ar = d / "task.json", d / "agent_response.json"
        if not tj.exists():
            continue
        if not ar.exists():
            skipped_no_answer += 1
            print(f"  skip {d.name}: no agent_response.json")
            continue
        try:
            t = json.loads(tj.read_text(encoding="utf-8"))
            resp = json.loads(ar.read_text(encoding="utf-8"))
            answer, status = resp.get("retrieved_data"), resp.get("status", "")
        except Exception as e:
            print(f"  skip {d.name}: unreadable ({e})")
            continue
        # strip pipeline text the wrapper may have carried into the prompt: the
        # skill-library hint and the answer-output instruction must not leak into templates
        task = t.get("task", "")
        if "## Skill library" in task:
            task = task.split("---", 1)[-1].strip()
        if "Additionally, write the final answer into" in task:
            task = task.split("Additionally, write the final answer into", 1)[0].strip()
        out.append({"dir": str(d.resolve()), "task_id": t.get("task_id", d.name),
                    "task": task, "start_url": t.get("start_url", ""),
                    "answer": answer, "status": status})
    if skipped_no_answer:
        print(f"  ! {skipped_no_answer} run(s) had no answer file and were skipped — their solves "
              f"cannot be aggregated. Solve via examples/solve_with_library.sh (it adds the "
              f"answer-output instruction), or see README 'Manual mode' step 1.")
    return out


_GROUP_SYS = (
    "You organize solved web tasks into task TEMPLATES. Tasks are instances of the same "
    "template when they differ only in parameter values (names, dates, places, counts).\n"
    "You are given existing template strings and a numbered task list. Return STRICT JSON:\n"
    '{"groups": [{"template": "sentence with {{param}} placeholders", '
    '"members": [{"i": <task index>, "params": {"<name>": "<value>", ...}}]}]}\n'
    "Rules: if a task matches an EXISTING template, use that exact template string verbatim. "
    "Every task index appears in exactly one group. A group may have a single member. "
    "Params must be the concrete values from the task text."
)


def group_chunk(runs, existing_templates):
    listing = "\n".join(f"{i}: {r['task'][:220]}" for i, r in enumerate(runs))
    existing = "\n".join(f"- {t}" for t in existing_templates) or "(none yet)"
    try:
        out = llm_json(_GROUP_SYS, f"## Existing templates\n{existing}\n\n## Tasks\n{listing}")
    except Exception as exc:
        raise SystemExit(
            f"learn: the grouping LLM call failed: {exc}\n"
            f"Check OPENAI_API_KEY — and on a custom gateway also set "
            f"OPENAI_ENDPOINT (and OPENAI_MODEL), or SKILL_MODEL_ENDPOINT/SKILL_MODEL_NAME. "
            f"The endpoint is the FULL request URL (e.g. https://gateway.example/api/responses), "
            f"not a base path.")
    return out.get("groups", [])


def learn(runs_dir, library_root, golds=None, chunk=25, dry_run=False, verify="strict",
          rounds=2, on_fail="reject", draws=2):
    lib = Library(library_root)
    ledger_path = Path(library_root) / ".learned.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {"runs": {}}
    golds = golds or {}

    runs = collect_runs(Path(runs_dir), ledger)
    if not runs:
        print("nothing new to learn"); return

    # gate first — wrong solves never reach the grouping step
    admitted = []
    for r in runs:
        g = (gate(r["answer"], gold=golds[r["task_id"]], method="gold")
             if r["task_id"] in golds
             else gate(r["answer"], method="self_verify", status=r.get("status", "")))
        r["admit"] = g.admit
        if g.admit:
            admitted.append(r)
        else:
            print(f"  gate ✗ {r['task_id']}: {g.reason}")
    print(f"{len(admitted)}/{len(runs)} runs admitted by gate "
          f"({'gold' if golds else 'self_verify'})")
    if not golds:
        print("  ! gate=self_verify: shape check + the agent's own SUCCESS report — an answer "
              "the agent wrongly believed still PASSES. Pass --golds for real verification.")
    if not admitted:
        return

    for lo in range(0, len(admitted), chunk):
        batch = admitted[lo:lo + chunk]
        existing = [s.meta.get("template", "") for s in lib.list()]
        groups = group_chunk(batch, existing)
        print(f"\nchunk {lo // chunk + 1}: {len(batch)} runs -> {len(groups)} template(s)")
        for g in groups:
            members = [m for m in g.get("members", []) if 0 <= m.get("i", -1) < len(batch)]
            print(f"  {g.get('template', '?')[:90]}  ({len(members)} solve(s))")
        if dry_run:
            continue
        for g in groups:
            tmpl = g.get("template", "")
            traces = []
            for m in g.get("members", []):
                if not (0 <= m.get("i", -1) < len(batch)):
                    continue
                r = batch[m["i"]]
                code_p = Path(r["dir"]) / "final_script.py"
                traces.append(Trace(
                    template=tmpl,
                    code=code_p.read_text(encoding="utf-8") if code_p.exists() else "",
                    answer=r["answer"], correct=True,
                    # existing template -> mark adapt so evolve REFINES instead of ignoring
                    verdict="adapt" if tmpl in existing else "skip",
                    meta={"params": m.get("params", {}),
                          "site": urlparse(r["start_url"]).netloc,
                          "start_url": r["start_url"],
                          "output_schema": infer_schema(r["answer"])}))
            if not traces:
                continue
            log = evolve(traces, lib, verify=verify, rounds=rounds, on_fail=on_fail, draws=draws)
            print(f"  evolve: {json.dumps(log)}")
            if log.get("rejected"):
                # skill did not land -> leave these runs OUT of the ledger so a later
                # learn (fixed model/site/verify mode) can try them again
                print(f"  ! runs kept un-learned (skill rejected) — re-run learn to retry")
                continue
            for m in g.get("members", []):
                if 0 <= m.get("i", -1) < len(batch):
                    ledger["runs"][batch[m["i"]]["dir"]] = {"template": tmpl}
        # audit trail + idempotence, saved per chunk
        ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    if not dry_run:
        print(f"\nlibrary now has {len(lib.list())} skill(s); ledger -> {ledger_path}")


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="python -m webwright.skill_factory learn",
                                description="Distill a folder of finished runs into library skills.")
    p.add_argument("runs_dir", help="Folder containing webwright run directories.")
    p.add_argument("--library", default="library")
    p.add_argument("--golds", default="", help="JSON file {task_id: gold_answer} -> gold gate.")
    p.add_argument("--chunk", type=int, default=25, help="Runs per LLM grouping call.")
    p.add_argument("--dry-run", action="store_true", help="Show the grouping plan, change nothing.")
    p.add_argument("--draws", type=int, default=2, metavar="N",
                   help="Independent distillation attempts before giving up (default 2). "
                        "Stops at the first that verifies.")
    p.add_argument("--verify-rounds", type=int, default=2,
                   help="Total build attempts (first + repairs) before giving up. Default 2.")
    p.add_argument("--on-fail", default="reject", choices=["reject", "reference"],
                   help="Failed verification: reject (default; runs stay retryable) or land as "
                        "grade=reference — readable prior for the agent, standalone NOT trusted.")
    p.add_argument("--verify", default="strict", choices=["off", "shape", "strict"],
                   help="A skill must REPLAY its own training taskspecs standalone before it may "
                        "enter the library. strict (default): it must reproduce the recorded "
                        "answers; shape: any non-empty, schema-shaped answer passes — use this for "
                        "task families whose answers are live data (prices, listings); off: skip.")
    a = p.parse_args(argv)
    golds = json.loads(Path(a.golds).read_text(encoding="utf-8")) if a.golds else {}
    learn(a.runs_dir, a.library, golds=golds, chunk=a.chunk, dry_run=a.dry_run,
          verify=a.verify, rounds=a.verify_rounds, on_fail=a.on_fail, draws=a.draws)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
