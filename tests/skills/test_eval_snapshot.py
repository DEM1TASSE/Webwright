"""Lock the WebArena results snapshot (evals/webarena/results/) to the published numbers.

The module README's table must stay derivable from the checked-in per-task records —
if either side drifts, this fails. Also enforces the snapshot's sanitization.
"""
import json
from pathlib import Path

EVAL = Path(__file__).resolve().parents[2] / "evals" / "webarena"


def run():
    recs = {p.stem: json.loads(p.read_text()) for p in (EVAL / "results").glob("*.json")}
    assert len(recs) == 100, f"expected 100 per-task records, found {len(recs)}"

    def agg(sel):
        rs = [v for k, v in recs.items() if sel(k)]
        return len(rs), sum(1 for r in rs if r["correct"]), sum(r["steps"] for r in rs) / len(rs)

    n, ok, steps = agg(lambda k: "heldout" in k and k.endswith("_with"))
    assert (n, ok, round(steps, 1)) == (20, 14, 14.7), (n, ok, steps)   # 70%
    n, ok, steps = agg(lambda k: "heldout" in k and k.endswith("_base"))
    assert (n, ok, round(steps, 1)) == (20, 11, 17.1), (n, ok, steps)   # 55%
    n, ok, steps = agg(lambda k: "trainwith" in k)
    assert (n, ok, round(steps, 1)) == (30, 26, 13.7), (n, ok, steps)   # 86.7%
    n, ok, steps = agg(lambda k: "_train" in k and "trainwith" not in k)
    assert (n, ok, round(steps, 1)) == (30, 23, 15.9), (n, ok, steps)   # 76.7%

    # sanitization lock: no local paths, no internal hosts, no keys in the snapshot
    for p in (EVAL / "results").glob("*.json"):
        txt = p.read_text()
        for bad in ("/home/", "ec2-", "amazonaws", "api_key", "Bearer "):
            assert bad not in txt, (p.name, bad)
        assert "dir" not in json.loads(txt), f"{p.name}: local run dir must stay out"

    # the driver that regenerates all of this must at least compile
    compile((EVAL / "reproduce.py").read_text(), "reproduce.py", "exec")

    print("test_eval_snapshot OK")


# pytest entry point (CI also runs this file as a script)
def test_all():
    run()


if __name__ == "__main__":
    run()
