import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "evals/webarena/build_primitive_rt_split.py"
SPEC = importlib.util.spec_from_file_location("build_primitive_rt_split", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def row(task_id, template_id, site, task_type):
    return {
        "task_id": task_id,
        "intent_template_id": template_id,
        "sites": [site],
        "eval": [{"expected": {"task_type": task_type}}],
    }


def test_build_split_is_deterministic_and_template_disjoint(monkeypatch):
    quotas = {site: {kind: 1 for kind in MODULE.TASK_TYPES} for site in MODULE.SITES}
    monkeypatch.setattr(MODULE, "TRAIN_QUOTAS", quotas)
    verified = []
    task_id = 0
    for site in MODULE.SITES:
        for kind in MODULE.TASK_TYPES:
            for template in range(2):
                for _ in range(3):
                    verified.append(row(task_id, template + 1000 * len(verified), site, kind))
                    task_id += 1
    # Repair template grouping: each consecutive group of three has one template id.
    for index, item in enumerate(verified):
        item["intent_template_id"] = index // 3
    official = [
        {"task_id": item["task_id"], "intent_template_id": item["intent_template_id"],
         "sites": item["sites"]}
        for item in verified
    ]
    monkeypatch.setattr(MODULE, "validate_split", lambda split: {"ok": True})
    first = MODULE.build_split(verified, official, "seed")
    second = MODULE.build_split(verified, official, "seed")
    assert first == second
    train = {
        (site, row["task_type"], row["intent_template_id"])
        for site, rows in first["train"].items() for row in rows
    }
    test = {
        (site, row["task_type"], row["intent_template_id"])
        for site, rows in first["test"].items() for row in rows
    }
    assert not train & test
    assert all(len(row["build_task_ids"]) == 3 for rows in first["train"].values() for row in rows)


def test_official_identity_mismatch_is_rejected():
    verified = [row(1, 10, "map", "retrieve")]
    official = [{"task_id": 1, "intent_template_id": 11, "sites": ["map"]}]
    try:
        MODULE.validate_official(verified, official)
    except ValueError as exc:
        assert "intent_template_id differs" in str(exc)
    else:
        raise AssertionError("expected identity mismatch")
