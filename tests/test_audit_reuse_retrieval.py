import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "evals/webarena/audit_reuse_retrieval.py"
SPEC = importlib.util.spec_from_file_location("audit_reuse_retrieval", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_validate_no_leakage_accepts_disjoint_templates():
    MODULE.validate_no_leakage({
        "train": {"map": [{"intent_template_id": 1}]},
        "test": {"map": [{"intent_template_id": 2}]},
    })


def test_validate_no_leakage_rejects_overlap():
    split = {
        "train": {"map": [{"intent_template_id": 1}]},
        "test": {"map": [{"intent_template_id": 1}]},
    }
    try:
        MODULE.validate_no_leakage(split)
    except ValueError as error:
        assert "leakage" in str(error)
    else:
        raise AssertionError("expected leakage rejection")
