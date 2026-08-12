"""How much of what the sources demonstrated actually reached the library?

An earlier attempt matched URL paths between the source workflows and the generated methods.
It does not work, and the failure is instructive: a primitive's whole job is to *parameterize*
the path that identifies it, so the literal disappears. That heuristic called a GitLab primitive
uncovered while the library plainly contained it, and reported 13% against 17% — noise.

So this uses the pipeline's own records instead, which are exact:

* extraction — what each workflow was found to demonstrate;
* candidate_attribution — what happened to each of those candidates;
* workflow_attribution — which workflows contributed to an operation at all.

Its blind spot is stated rather than hidden: it measures coverage of what extraction *found*.
A capability the extraction never enumerated is invisible here, because nothing downstream ever
knew about it. Catching those needs a second independent extraction of the same workflow and a
diff of the two — see `compare_extractions`.
"""
from __future__ import annotations

import json
from pathlib import Path

_KEPT = {"ADD", "UPDATE", "COVERED"}


def _load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def report(library: Path) -> dict:
    """Coverage of one built library, from its own extraction and attribution records."""
    library = Path(library)
    extractions: dict[str, dict] = {}
    for path in sorted(library.glob("extractions/*/extraction.json")):
        extractions[path.parent.name] = _load(path)

    kept, dropped = {}, {}
    contributed: dict[str, dict] = {}
    for batch_dir in sorted(library.glob("batches/batch_*")):
        proposal = _load(batch_dir / "proposal.json")
        for entry in proposal.get("candidate_attribution") or []:
            target = kept if entry.get("decision") in _KEPT else dropped
            target[str(entry.get("candidate_id"))] = entry
        for entry in proposal.get("workflow_attribution") or []:
            contributed[str(entry.get("workflow_id"))] = entry

    rows = []
    for workflow_id, extraction in sorted(extractions.items()):
        candidates = [str(c.get("candidate_id")) for c in extraction.get("candidates") or []]
        attribution = contributed.get(workflow_id, {})
        rows.append({
            "workflow_id": workflow_id,
            "demonstrated": len(candidates),
            "kept": sum(1 for c in candidates if c in kept),
            "dropped": [{"candidate_id": c, "reason": dropped[c].get("reason", "")}
                        for c in candidates if c in dropped],
            "decision": attribution.get("decision", "?"),
            "skip_reason": attribution.get("reason", ""),
            "extracted_nothing": not candidates,
        })

    demonstrated = sum(r["demonstrated"] for r in rows)
    return {
        "site": library.name,
        "workflows": rows,
        "demonstrated": demonstrated,
        "kept": sum(r["kept"] for r in rows),
        "ratio": round(sum(r["kept"] for r in rows) / demonstrated, 3) if demonstrated else 1.0,
        "contributed_nothing": [r["workflow_id"] for r in rows
                                if r["decision"] == "SKIP" or (r["demonstrated"] and not r["kept"])],
        "blind_spot": "counts only capabilities extraction enumerated; a missed capability is "
                      "invisible here — compare two independent extractions to find those",
    }


def compare_extractions(libraries: list[Path]) -> dict:
    """Diff what independent runs found in the same workflows.

    A workflow that yields two candidates in one run and one in another is where a real
    capability was missed; this is the only signal that sees past extraction's own blind spot.
    """
    per_run: list[dict[str, int]] = []
    for library in libraries:
        counts = {}
        for path in sorted(Path(library).glob("extractions/*/extraction.json")):
            counts[path.parent.name] = len(_load(path).get("candidates") or [])
        per_run.append(counts)

    workflow_ids = sorted({wid for counts in per_run for wid in counts})
    rows = []
    for workflow_id in workflow_ids:
        counts = [run.get(workflow_id) for run in per_run]
        present = [c for c in counts if c is not None]
        rows.append({"workflow_id": workflow_id, "counts": counts,
                     "stable": len(set(present)) <= 1,
                     "max_seen": max(present) if present else 0})
    return {"runs": [str(x) for x in libraries], "workflows": rows,
            "unstable": [r["workflow_id"] for r in rows if not r["stable"]]}


def format_report(data: dict) -> str:
    lines = [f"Extraction-to-library coverage for {data['site']}: "
             f"{data['kept']}/{data['demonstrated']} demonstrated capabilities kept "
             f"({data['ratio']:.0%})", ""]
    for row in data["workflows"]:
        if row["extracted_nothing"]:
            mark, detail = "[-]", "extraction found nothing reusable"
        elif row["kept"] == row["demonstrated"]:
            mark, detail = "[x]", f"{row['kept']}/{row['demonstrated']}"
        else:
            mark, detail = "[ ]", f"{row['kept']}/{row['demonstrated']}"
        lines.append(f"  {mark} {row['workflow_id']:16s} {detail}")
        for entry in row["dropped"]:
            lines.append(f"        dropped {entry['candidate_id']}: {entry['reason'][:80]}")
        if row["decision"] == "SKIP" and row["skip_reason"]:
            lines.append(f"        workflow SKIP: {row['skip_reason'][:80]}")
    lines += ["", f"Blind spot: {data['blind_spot']}"]
    return "\n".join(lines)


def format_comparison(data: dict) -> str:
    lines = ["Independent extraction runs — candidates found per workflow", ""]
    for row in data["workflows"]:
        counts = " ".join("?" if c is None else str(c) for c in row["counts"])
        lines.append(f"  {'[x]' if row['stable'] else '[!]'} {row['workflow_id']:16s} {counts}")
    if data["unstable"]:
        lines += ["", "Unstable — some run found a capability another missed: "
                  + ", ".join(data["unstable"])]
    else:
        lines += ["", "Every workflow yielded the same count in every run."]
    return "\n".join(lines)
