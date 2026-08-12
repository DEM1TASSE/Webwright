import json
from pathlib import Path


ROOT = Path(__file__).parents[2]
SPLIT = json.loads(
    (ROOT / "evals/odysseys/pilot_10x10_split.json").read_text(encoding="utf-8")
)


def test_pilot_has_disjoint_ten_by_ten_tasks_and_templates():
    source = SPLIT["source"]
    heldout = SPLIT["heldout"]
    assert len(source) == len({row["task_id"] for row in source}) == 10
    assert len(heldout) == len({row["task_id"] for row in heldout}) == 10
    assert {row["task_id"] for row in source}.isdisjoint(
        row["task_id"] for row in heldout
    )
    for site in {row["site"] for row in source + heldout}:
        source_templates = {
            row["template_id"] for row in source if row["site"] == site
        }
        heldout_templates = {
            row["template_id"] for row in heldout if row["site"] == site
        }
        assert source_templates.isdisjoint(heldout_templates)


def test_every_heldout_has_substantive_site_capability_overlap():
    source = SPLIT["source"]
    for row in SPLIT["heldout"]:
        source_capabilities = {
            capability
            for candidate in source
            if candidate["site"] == row["site"]
            for capability in candidate["capabilities"]
        }
        overlap = source_capabilities.intersection(row["capabilities"])
        assert overlap
        assert any(
            capability.split(".", 1)[-1]
            not in {"open_homepage", "search_web", "close_cookie"}
            for capability in overlap
        )
