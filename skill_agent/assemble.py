"""Assemble a stage proposal from the small per-part files the agent writes.

The scripted pipeline had to emit one enormous JSON object per stage, with every primitive's
Python body escaped inside a JSON string, in a single model response. A terminal agent does
not have to: it writes one file per operation and keeps method bodies as real ``.py`` files,
then runs this command to compose them.

    python -m skill_agent.assemble build          # out/ops/*.json -> out/proposal.json
    python -m skill_agent.assemble consolidate

Each operation file may set ``method_code_file`` (relative to ``out/``) instead of
``method_code``; the referenced file's text is inlined here. Operation index is the sorted
order of ``out/ops/*.json``, and that mapping is printed so attribution indices can be
checked against it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ATTRIBUTIONS = {
    "build": ["workflow_attribution", "candidate_attribution"],
    "consolidate": [],
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _inline_code(primitive: dict, out_dir: Path, where: str, errors: list[str]) -> dict:
    """Replace method_code_file with the file's literal text."""
    if not isinstance(primitive, dict):
        errors.append(f"{where}: expected an object, got {type(primitive).__name__}")
        return primitive
    code_file = primitive.pop("method_code_file", None)
    if code_file is None:
        if not primitive.get("method_code"):
            errors.append(f"{where}: needs either method_code or method_code_file")
        return primitive
    if primitive.get("method_code"):
        errors.append(f"{where}: sets both method_code and method_code_file; keep only one")
        return primitive
    resolved = (out_dir / str(code_file)).resolve()
    try:
        resolved.relative_to(out_dir.resolve())
    except ValueError:
        errors.append(f"{where}: method_code_file must stay inside out/ ({code_file})")
        return primitive
    if not resolved.is_file():
        errors.append(f"{where}: method_code_file not found: {code_file}")
        return primitive
    primitive["method_code"] = resolved.read_text(encoding="utf-8")
    return primitive


def _resolve_operation(op: dict, out_dir: Path, index: int, errors: list[str]) -> dict:
    where = f"operation {index}"
    if "replacement" in op:
        op["replacement"] = _inline_code(op["replacement"], out_dir, f"{where} replacement", errors)
    if "replacements" in op and isinstance(op["replacements"], list):
        op["replacements"] = [
            _inline_code(item, out_dir, f"{where} replacements[{i}]", errors)
            for i, item in enumerate(op["replacements"])
        ]
    return op


def assemble(stage: str, workspace: Path) -> tuple[dict, list[str], list[dict]]:
    out_dir = (Path(workspace) / "out").resolve()
    errors: list[str] = []
    ops_dir = out_dir / "ops"
    if not ops_dir.is_dir():
        return {}, [f"{ops_dir} does not exist; write one JSON file per operation there"], []

    op_files = sorted(p for p in ops_dir.glob("*.json"))
    if not op_files:
        return {}, [f"{ops_dir} contains no *.json operation files"], []

    operations, index_map = [], []
    for index, path in enumerate(op_files):
        try:
            op = _load(path)
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}: invalid JSON: {exc}")
            continue
        if not isinstance(op, dict):
            errors.append(f"{path.name}: must contain a JSON object")
            continue
        operations.append(_resolve_operation(op, out_dir, index, errors))
        replacement = op.get("replacement") or {}
        index_map.append({
            "operation_index": index,
            "file": path.name,
            "op": op.get("op") or op.get("operation") or op.get("decision") or "?",
            "primitive_id": replacement.get("primitive_id") or op.get("source") or "",
        })

    proposal: dict = {"operations": operations}
    for key in _ATTRIBUTIONS[stage]:
        path = out_dir / f"{key}.json"
        if not path.is_file():
            errors.append(f"missing out/{key}.json")
            continue
        try:
            proposal[key] = _load(path)
        except json.JSONDecodeError as exc:
            errors.append(f"{key}.json: invalid JSON: {exc}")
    return proposal, errors, index_map


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("stage", choices=sorted(_ATTRIBUTIONS))
    parser.add_argument("--workspace", default=".", help="Stage workspace (default: cwd)")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    proposal, errors, index_map = assemble(args.stage, workspace)
    if index_map:
        print("Operation index map (index is sorted order of out/ops/*.json):")
        for row in index_map:
            print(f"  [{row['operation_index']}] {row['file']:<24} {row['op']:<8} {row['primitive_id']}")
        print()
    if errors:
        print(json.dumps({"assembled": False, "errors": errors}, ensure_ascii=False, indent=2))
        print(f"\nASSEMBLY FAILED: {len(errors)} error(s). Nothing was written.")
        return 1
    target = workspace / "out" / "proposal.json"
    target.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {target} with {len(proposal['operations'])} operation(s).")
    print(f"Now run: python -m skill_agent.check {args.stage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
