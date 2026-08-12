import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "evals/webarena/build_reuse_workflow_library.py"
SPEC = importlib.util.spec_from_file_location("build_reuse_workflow_library", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_eligible_templates_respects_workflow_flag_and_empty_gold():
    split = {"train": {"map": [
        {"intent_template_id": 1, "workflow_skill": True},
        {"intent_template_id": 2, "workflow_skill": False},
        {"intent_template_id": 3, "workflow_skill": True},
    ]}}
    manifests = {"map": {"1": ["one.json"], "2": ["two.json"]}}
    assert list(MODULE.eligible_templates(split, manifests)) == [
        ("map", "1", ["one.json"]),
        ("map", "3", []),
    ]


def test_built_skill_ids_joins_ledger_to_skill_meta(tmp_path):
    library, runs = tmp_path / "library", tmp_path / "runs"
    (library / "skill_abc").mkdir(parents=True)
    (runs / "run_1").mkdir(parents=True)
    (library / ".learned.json").write_text(json.dumps({
        "runs": {str(runs / "run_1"): {"template": "Do {{thing}}"}}
    }))
    (library / "skill_abc/meta.json").write_text(json.dumps({"template": "Do {{thing}}"}))
    assert MODULE.built_skill_ids(library, runs) == ["skill_abc"]
