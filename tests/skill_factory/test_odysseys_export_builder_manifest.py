import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location(
    "odysseys_export_builder_manifest",
    ROOT / "evals/odysseys/export_builder_manifest.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_exports_only_admitted_segments(tmp_path):
    review = tmp_path / "review.json"
    review.write_text(json.dumps({
        "task_id": "t", "run_dir": "/run", "segments": [
            {"segment_id": "S1", "site": "a_com", "goal": "a",
             "template_id": "a.lookup", "rubric_ids": ["R1"],
             "required_fields": ["x"], "code_path": "/a.py", "admitted": True},
            {"segment_id": "S2", "site": "b_com", "goal": "b",
             "template_id": "b.lookup", "rubric_ids": ["R2"],
             "required_fields": [], "code_path": "/b.py", "admitted": False},
        ],
    }))
    result = MODULE.export([review], tmp_path / "out")
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert result["site_segments"] == 1
    assert manifest["sources"][0]["segment_code"] == {"S1": "/a.py"}
