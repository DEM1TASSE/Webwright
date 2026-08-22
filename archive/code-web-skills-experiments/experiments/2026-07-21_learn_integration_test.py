"""Integration tests (need gateway; verify=off so no browser):
  ⑤ a dir with TWO intents (cheapest vs earliest-nonstop = different objective) -> TWO skills
  ⑥ incremental: a 2nd batch of the SAME template refines the existing skill in place (not a new one)

Builds plain trajectories by copying a real solve dir (for final_script.py) and editing the task
text + the exit-message answer to prose. Run:  python 2026-07-21_learn_integration_test.py
"""
import glob
import json
import shutil
import tempfile
from pathlib import Path

from webwright.skill_factory.learn import learn
from webwright.skill_factory.library import Library

_fx = Path(__file__).parent / "data" / "plain_solve_fixture"
SRC = str(_fx) if (_fx / "trajectory.json").exists() else sorted(glob.glob("/tmp/plain_solve/outputs/plain_solve_*"))[-1]
npass = ntot = 0
def check(name, cond, extra=""):
    global npass, ntot
    ntot += 1; npass += bool(cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  ' + str(extra)) if extra else ''}")


def make_run(root, name, task_text, prose, task_id):
    d = Path(root) / name
    shutil.copytree(SRC, d)
    (d / "agent_response.json").unlink(missing_ok=True)   # ensure plain
    tj = d / "task.json"; t = json.loads(tj.read_text())
    t["task"] = task_text; t["task_id"] = task_id
    tj.write_text(json.dumps(t))
    trj = d / "trajectory.json"; tr = json.loads(trj.read_text())
    for m in reversed(tr["messages"]):
        if m.get("role") == "exit":
            m["content"] = prose; m["extra"]["submission"] = prose; m["extra"]["final_response"] = prose
            break
    trj.write_text(json.dumps(tr))
    return d


CHEAP = "What is the cheapest flight from {} to {} on 2026-08-20 (one-way)?"
EARLY = "What is the earliest nonstop flight from {} to {} on 2026-08-20 (one-way)?"

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # ---------- ⑤ two intents -> two skills ----------
    print("── ⑤ mixed-intent dir -> two skills ──")
    d5 = tmp / "five"; (d5 / "outputs").mkdir(parents=True)
    make_run(d5 / "outputs", "c1", CHEAP.format("Seattle (SEA)", "Denver (DEN)"), "Cheapest is Frontier at $45.", "c1")
    make_run(d5 / "outputs", "c2", CHEAP.format("Los Angeles (LAX)", "Chicago (ORD)"), "Cheapest is Spirit at $52.", "c2")
    make_run(d5 / "outputs", "e1", EARLY.format("Seattle (SEA)", "Denver (DEN)"), "Earliest nonstop is United UA729 at 6:00 AM.", "e1")
    make_run(d5 / "outputs", "e2", EARLY.format("San Francisco (SFO)", "Boston (BOS)"), "Earliest nonstop is JetBlue B6434 at 6:10 AM.", "e2")
    lib5 = d5 / "library"
    learn(str(d5 / "outputs"), str(lib5), verify="off")
    skills5 = Library(str(lib5)).list()
    templs = {s.meta.get("template", "")[:40] for s in skills5}
    check("two skills learned", len(skills5) == 2, [s.skill_id for s in skills5])
    check("templates are distinct intents", len(templs) == 2, list(templs))

    # ---------- ⑥ incremental refine ----------
    print("── ⑥ incremental: 2nd batch refines the same skill in place ──")
    d6 = tmp / "six"; (d6 / "b1").mkdir(parents=True); (d6 / "b2").mkdir(parents=True)
    make_run(d6 / "b1", "c1", CHEAP.format("Seattle (SEA)", "Denver (DEN)"), "Cheapest is Frontier at $45.", "c1")
    make_run(d6 / "b1", "c2", CHEAP.format("Los Angeles (LAX)", "Chicago (ORD)"), "Cheapest is Spirit at $52.", "c2")
    lib6 = d6 / "library"
    learn(str(d6 / "b1"), str(lib6), verify="off")
    s1 = Library(str(lib6)).list()
    n_before = len(s1)
    rev_before = s1[0].meta.get("revisions") if s1 else None
    nsolves_before = s1[0].meta.get("n_solves") if s1 else None

    make_run(d6 / "b2", "c3", CHEAP.format("New York (JFK)", "Miami (MIA)"), "Cheapest is Frontier at $60.", "c3")
    learn(str(d6 / "b2"), str(lib6), verify="off")
    s2 = Library(str(lib6)).list()

    check("still ONE skill (refined, not duplicated)", len(s2) == n_before == 1, [x.skill_id for x in s2])
    if s2:
        m = s2[0].meta
        check("revisions incremented", (m.get("revisions") or 0) > (rev_before or 0), f"{rev_before}->{m.get('revisions')}")
        check("n_solves grew (3)", (m.get("n_solves") or 0) > (nsolves_before or 0), f"{nsolves_before}->{m.get('n_solves')}")
        check("provenance = incremental", "incremental" in (m.get("provenance") or ""), m.get("provenance"))

print(f"\n{npass}/{ntot} checks passed")
raise SystemExit(0 if npass == ntot else 1)
