import importlib.util
import json
import signal
import subprocess
from pathlib import Path


_PATH = Path(__file__).parents[2] / "evals" / "webarena" / "cross_task_eval.py"
_SPEC = importlib.util.spec_from_file_location("cross_task_eval", _PATH)
E = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(E)


def test_prepare_routed_hint_uses_primitive_only_cross_template_policy(tmp_path):
    seen = {}

    def fake_route(task, library, **kwargs):
        seen.update(task=task, library=library, kwargs=kwargs)
        return {
            "action": "agent",
            "hint": "selected material",
            "route_stage": "primitive",
            "route_decision": "adapt",
        }

    task = {"intent": "summarize commits", "sites": ["gitlab"]}
    out = E.prepare_routed_hint(task, tmp_path, route_fn=fake_route)
    assert out["hint"] == "selected material"
    assert seen["kwargs"]["primitive_site"] == "gitlab"
    assert seen["kwargs"]["cross_template_workflow_first"] is False
    assert "agent_fn" not in seen["kwargs"]


def test_empty_primitive_hint_is_byte_exact_noop():
    prompt = "Complete this web task.\nGoal: demo"
    assert E.prepend_nonempty_hint(prompt, "") == prompt
    assert E.prepend_nonempty_hint(prompt, "material") == "material\n" + prompt


def test_configure_router_model_uses_explicit_yaml_backend(tmp_path, monkeypatch):
    config = tmp_path / "model.yaml"
    config.write_text(
        "model:\n  model_class: openai\n  model_name: test-model\n"
        "  openai_endpoint: https://gateway.example/responses\n"
    )
    seen = []
    monkeypatch.setattr(
        "webwright.skill_factory.llm.configure_llm", lambda model: seen.append(model)
    )
    E.configure_router_model(config)
    assert seen == [{
        "model_class": "openai",
        "model_name": "test-model",
        "openai_endpoint": "https://gateway.example/responses",
    }]


def test_null_not_found_response_is_a_complete_artifact(tmp_path):
    run = tmp_path / "task7_scratch_001"
    run.mkdir()
    (run / "agent_response.json").write_text(
        '{"task_type":"RETRIEVE","status":"NOT_FOUND_ERROR",'
        '"retrieved_data":null,"error_details":null}'
    )
    assert E.has_complete_agent_response(tmp_path, "task7_scratch") is True
    assert E.collect_run(tmp_path, "task7_scratch")[1] is None


def test_missing_response_is_not_complete(tmp_path):
    run = tmp_path / "task8_scratch_001"
    run.mkdir()
    (run / "task.json").write_text("{}")
    assert E.has_complete_agent_response(tmp_path, "task8_scratch") is False


def test_navigate_completion_requires_saved_url_and_dom(tmp_path):
    run = tmp_path / "task44_scratch_001"
    run.mkdir()
    (run / "agent_response.json").write_text(
        '{"task_type":"NAVIGATE","status":"SUCCESS",'
        '"retrieved_data":null,"error_details":null}'
    )
    assert E.has_complete_agent_response(tmp_path, "task44_scratch", "navigate") is False
    (run / "final_state.json").write_text(json.dumps({
        "final_url": "https://example.test/dashboard/todos",
        "html_path": "final_state.html",
        "document_status": 200,
        "answer": "",
    }))
    (run / "final_state.html").write_text("<html><body>Todos</body></html>")
    assert E.has_complete_final_state(tmp_path, "task44_scratch") is True
    assert E.has_complete_agent_response(tmp_path, "task44_scratch", "navigate") is True


def test_vanilla_final_state_interface_does_not_reveal_task_type():
    assert "NAVIGATE" not in E.VANILLA_FINAL_STATE_SPEC
    assert "task_type" not in E.VANILLA_FINAL_STATE_SPEC
    assert "agent_response" not in E.VANILLA_FINAL_STATE_SPEC
    assert "final_state.json" in E.VANILLA_FINAL_STATE_SPEC


def test_validate_split_accepts_navigate_with_network_evaluators():
    split = {
        "site": "gitlab", "task_type": "navigate",
        "source": {"intent_template_ids": []},
        "heldout": [{"intent_template_id": 9, "task_ids": [44]}],
    }
    dataset = [{
        "task_id": 44, "intent_template_id": 9, "sites": ["gitlab"],
        "eval": [
            {"evaluator": "AgentResponseEvaluator", "expected": {"task_type": "navigate"}},
            {"evaluator": "NetworkEventEvaluator"},
        ],
    }]
    assert E.validate_split(split, dataset) == []


def test_validate_split_accepts_official_webarena_navigate_task():
    split = {
        "site": "gitlab", "task_type": "navigate",
        "source": {"intent_template_ids": []},
        "heldout": [{"intent_template_id": 303, "task_ids": [44]}],
    }
    dataset = [{
        "task_id": 44, "intent_template_id": 303, "sites": ["gitlab"],
        "intent": "Check out my todos", "start_url": "__GITLAB__",
        "eval": {"eval_types": ["url_match"]},
    }]
    assert E.is_official_webarena_task(dataset[0]) is True
    assert E.expected_task_type(dataset[0], default="navigate") == "navigate"
    assert E.validate_split(split, dataset) == []


def test_official_execution_task_keeps_verified_template_metadata_only(tmp_path):
    official = [{
        "task_id": 44,
        "intent_template_id": 303,
        "sites": ["gitlab"],
        "intent": "Check out my todos",
        "start_url": "__GITLAB__",
        "eval": {"eval_types": ["url_match"]},
    }]
    path = tmp_path / "test.raw.json"
    path.write_text(json.dumps(official))
    verified = {
        "task_id": 44,
        "intent_template_id": 303,
        "sites": ["gitlab"],
        "intent": "Open my todos page",
    }
    task = E.load_official_execution_task(verified, path)
    assert task["intent"] == "Check out my todos"
    assert task["start_url"] == "__GITLAB__"


def test_official_execution_task_rejects_template_mismatch(tmp_path):
    path = tmp_path / "test.raw.json"
    path.write_text(json.dumps([{
        "task_id": 44, "intent_template_id": 999, "sites": ["gitlab"],
    }]))
    try:
        E.load_official_execution_task(
            {"task_id": 44, "intent_template_id": 303, "sites": ["gitlab"]}, path,
        )
    except ValueError as error:
        assert "metadata mismatch" in str(error)
    else:
        raise AssertionError("expected mismatched template IDs to be rejected")


def test_resolve_url_accepts_official_singular_start_url():
    task = {"start_url": "__GITLAB__/dashboard/todos"}
    config = {"environments": {"__GITLAB__": {"urls": ["https://gitlab.test"]}}}
    assert E.resolve_url(task, config) == "https://gitlab.test/dashboard/todos"


def test_terminate_process_group_escalates_after_grace_period(monkeypatch):
    calls = []

    class Proc:
        pid = 42

        def wait(self, timeout=None):
            calls.append(("wait", timeout))
            if timeout is not None:
                raise subprocess.TimeoutExpired("agent", timeout)

    monkeypatch.setattr(
        E.os, "killpg", lambda pid, sig: calls.append(("killpg", pid, sig))
    )
    E.terminate_process_group(Proc(), grace_seconds=3)
    assert calls == [
        ("killpg", 42, signal.SIGTERM),
        ("wait", 3),
        ("killpg", 42, signal.SIGKILL),
        ("wait", None),
    ]


def test_process_start_failure_is_infrastructure_not_benchmark_failure():
    assert E.classify_result(False, None, False, 1) == (
        None, "agent_process_infrastructure_error"
    )
    assert E.classify_result(False, None, True, -15) == (
        False, "agent_timeout_or_incomplete"
    )
    assert E.classify_result(True, 1.0, False, 0) == (True, "scored_correct")


def test_strict_arm_isolation_rejects_opposite_arm_artifacts(tmp_path):
    (tmp_path / "task7_primitive_001").mkdir()
    try:
        E.assert_arm_isolation(tmp_path, "scratch")
    except ValueError as error:
        assert "opposite-arm artifacts" in str(error)
    else:
        raise AssertionError("expected scratch isolation failure")


def test_strict_arm_isolation_allows_same_arm_and_scratch_plan(tmp_path):
    (tmp_path / "task7_scratch_001").mkdir()
    (tmp_path / "task7.scratch_plan.json").write_text("{}")
    E.assert_arm_isolation(tmp_path, "scratch")


def test_strict_arm_isolation_rejects_workflow_artifacts_from_primitive(tmp_path):
    (tmp_path / "task7_workflow_001").mkdir()
    try:
        E.assert_arm_isolation(tmp_path, "primitive")
    except ValueError as error:
        assert "opposite-arm artifacts" in str(error)
    else:
        raise AssertionError("expected primitive isolation failure")


def test_prepare_workflow_hint_forced_exact_skill(tmp_path):
    skill = tmp_path / "wf_1"
    skill.mkdir()
    (skill / "meta.json").write_text(json.dumps({"template": "Find {{item}}"}))
    (skill / "skill.py").write_text("def solve(item): return item\n")
    out = E.prepare_workflow_hint(
        {"intent": "Find shoes", "sites": ["shopping"]},
        tmp_path,
        forced_skill_id="wf_1",
    )
    assert out["decision"] == "use"
    assert out["skill_id"] == "wf_1"
    assert "def solve(item)" in out["hint"]


def test_direct_primitive_router_does_not_require_scratch_plan(tmp_path):
    root = tmp_path / "map" / "final_candidate"
    root.mkdir(parents=True)
    (root / "index.json").write_text(json.dumps({
        "site": "map", "status": "candidate", "primitives": [{
            "primitive_id": "map/search", "method_code": "def search(): pass",
            "feature": "search", "method": "search", "capability": "search places",
        }],
    }))
    seen = {}

    def fake_llm(system, user):
        if system.startswith("Route site primitives"):
            seen.update(system=system, user=user)
            return {"decision": "adapt", "primitive_ids": ["map/search"],
                    "reason": "useful acquisition", "remaining_gap": ["filter"],
                    "task_structure": "single_stage"}
        if system.startswith("Classify exactly one structural property"):
            seen.update(risk_system=system, risk_user=user)
            return {"chained_open_world": False, "upstream_entity": "",
                    "downstream_operation": "", "reason": "one candidate set"}
        seen.update(verifier_system=system, verifier_user=user)
        return {
            "verdict": "accept",
            "checks": {
                "input_reachability": "pass",
                "guarantee_sufficiency": "pass",
                "closed_acquisition": "pass",
            },
            "closed_acquisitions": ["place lookup"],
            "reason": "closes place lookup",
        }

    out = E.retrieve_direct_primitives(
        "find a place", tmp_path, site="map", llm_fn=fake_llm,
    )
    assert out.decision == "adapt"
    assert [item["primitive_id"] for item in out.primitives] == ["map/search"]
    assert "Do not require or mention a scratch plan" in seen["system"]
    assert "scratch_plan" not in seen["user"]
    assert "contract refinement" in seen["verifier_system"]
    assert "nearest pharmacy from fully named CMU" in seen["risk_system"]
    assert out.contract_verdict["verdict"] == "accept"


def test_direct_primitive_router_skips_ambiguous_open_world_chain(tmp_path):
    root = tmp_path / "map" / "final_candidate"
    root.mkdir(parents=True)
    (root / "index.json").write_text(json.dumps({
        "site": "map", "status": "candidate", "primitives": [{
            "primitive_id": "map/search", "method_code": "def search(): pass",
            "feature": "search", "method": "search", "capability": "search places",
        }],
    }))

    def fake_llm(system, user):
        if system.startswith("Route site primitives"):
            return {
                "decision": "adapt", "primitive_ids": ["map/search"],
                "reason": "local searches are covered", "remaining_gap": ["choose hotel"],
                "task_structure": "ambiguous_open_world_chain",
            }
        if system.startswith("Classify exactly one structural property"):
            return {
                "chained_open_world": True,
                "upstream_entity": "a hotel",
                "downstream_operation": "find its nearest supermarket",
                "reason": "the downstream search depends on the selected hotel",
            }
        if system.startswith("Filter proposed primitive IDs"):
            return {"safe_primitive_ids": [], "reason": "search is unsafe"}
        return {
            "verdict": "accept",
            "checks": {
                "input_reachability": "pass",
                "guarantee_sufficiency": "pass",
                "closed_acquisition": "pass",
            },
            "closed_acquisitions": ["place lookup"],
            "reason": "closes place lookup",
        }

    out = E.retrieve_direct_primitives(
        "choose a hotel, then find its nearest supermarket",
        tmp_path, site="map", llm_fn=fake_llm,
    )
    assert out.decision == "skip"
    assert out.primitives == []
    assert out.contract_verdict == {}


def test_direct_primitive_router_does_not_fake_late_binding_in_one_shot_prompt(tmp_path):
    root = tmp_path / "map" / "final_candidate"
    root.mkdir(parents=True)
    (root / "index.json").write_text(json.dumps({
        "site": "map", "status": "candidate", "primitives": [
            {
                "primitive_id": "map/search", "method_code": "def search(): pass",
                "feature": "search", "method": "search", "capability": "search places",
            },
            {
                "primitive_id": "map/route", "method_code": "def route(): pass",
                "feature": "routing", "method": "route", "capability": "route coordinates",
                "input_contract": {
                    "type": "object", "properties": {
                        "waypoints": {"type": "array", "items": {"type": "object",
                            "properties": {"latitude": {"type": "number"},
                                           "longitude": {"type": "number"}}}},
                    },
                },
                "output_contract": {
                    "type": "object", "properties": {
                        "routes": {"type": "array", "items": {"type": "object",
                            "properties": {"duration_seconds": {"type": "number"},
                                           "distance_meters": {"type": "number"}}}},
                    },
                },
            },
        ],
    }))

    def fake_llm(system, user):
        if system.startswith("Route site primitives"):
            return {
                "decision": "adapt", "primitive_ids": ["map/search", "map/route"],
                "reason": "search then route", "remaining_gap": ["choose hotel"],
                "task_structure": "ambiguous_open_world_chain",
            }
        if system.startswith("Classify exactly one structural property"):
            return {
                "chained_open_world": True,
                "upstream_entity": "a hotel",
                "downstream_operation": "route to a selected supermarket",
                "reason": "routing consumes coordinates selected later",
            }
        if system.startswith("Filter proposed primitive IDs"):
            assert "A route lookup between already selected coordinates is safe" in system
            return {
                "safe_primitive_ids": [],
                "reason": "simulate an overly conservative model decision",
            }
        raise AssertionError("one-shot chained tasks must skip before contract verification")

    out = E.retrieve_direct_primitives(
        "choose a hotel, then route to its nearest supermarket",
        tmp_path, site="map", llm_fn=fake_llm,
    )
    assert out.decision == "skip"
    assert out.primitives == []


def test_deterministic_guard_rejects_partial_exhaustive_collection_and_missing_quantity():
    partial = {
        "primitive_id": "shopping_admin/orders/list",
        "output_contract": {"properties": {"items": {"type": "array"}}},
        "guarantees": {"completeness": "partial"},
    }
    assert "exhaustive" in E.deterministic_direct_contract_guard(
        "Get the total number of pending reviews", [partial], site="shopping_admin"
    )
    assert "quantity" in E.deterministic_direct_contract_guard(
        "Get the items sold in the most recent orders", [partial], site="shopping_admin"
    )


def test_deterministic_guard_allows_query_scoped_price_aggregation_without_global_claim():
    search = {
        "primitive_id": "shopping/catalog/search_products_paginated",
        "output_contract": {"properties": {"products": {"type": "array"},
                                                   "price": {"type": "number"}}},
        "guarantees": {"completeness": "conditional"},
    }
    assert E.deterministic_direct_contract_guard(
        "What is the price range of teeth grinding mouth guards?", [search], site="shopping"
    ) is None


def test_deterministic_guard_rejects_population_reducers_over_partial_collections():
    contributors = {
        "primitive_id": "gitlab/contributors/list_repository_contributors",
        "input_contract": {"properties": {"project_id": {"type": "integer"}}},
        "output_contract": {"properties": {"contributors": {"type": "array"}}},
        "guarantees": {"completeness": "conditional"},
    }
    reviews = {
        "primitive_id": "shopping_admin/reviews/search_product_reviews_by_product_name",
        "input_contract": {"properties": {"product_name": {"type": "string"}}},
        "output_contract": {"properties": {"records": {"type": "array"}}},
        "guarantees": {"completeness": "partial"},
    }
    products = {
        "primitive_id": "shopping/catalog/multi_search_products_graphql_dedup_by_sku",
        "input_contract": {"properties": {"queries": {"type": "array"}}},
        "output_contract": {"properties": {"products": {"type": "array"}}},
        "guarantees": {"completeness": "conditional"},
    }

    assert "exhaustive" in E.deterministic_direct_contract_guard(
        "Tell me who made the most contributions to this project", [contributors], site="gitlab"
    )
    assert "exhaustive" in E.deterministic_direct_contract_guard(
        "What key aspects do customers dislike about this product?", [reviews],
        site="shopping_admin",
    )
    assert "exhaustive" in E.deterministic_direct_contract_guard(
        "Find discounted items.", [products], site="shopping"
    )


def test_deterministic_guard_allows_population_reducer_with_explicit_all_pages_mode():
    orders = {
        "primitive_id": "shopping/orders/list_authenticated_customer_orders_graphql",
        "input_contract": {"properties": {"retrieval_mode": {
            "type": "string", "enum": ["single_page", "all_pages"],
        }}},
        "output_contract": {"properties": {"orders": {"type": "array"}}},
        "guarantees": {"completeness": "conditional"},
    }
    assert E.deterministic_direct_contract_guard(
        "What is the date when I made my first purchase on this site?", [orders], site="shopping"
    ) is None


def test_reads_valid_primitive_execution_events(tmp_path):
    (tmp_path / "primitive_execution_trace.jsonl").write_text("\n".join([
        json.dumps({"primitive_id": "gitlab/commits/list", "scratch_step_id": "S1",
                    "event": "entered"}),
        "not-json",
        json.dumps({"primitive_id": "gitlab/commits/list", "event": "completed"}),
        json.dumps({"primitive_id": "gitlab/commits/list", "event": "unknown"}),
    ]))
    assert E.read_primitive_execution_trace(tmp_path) == [
        {"primitive_id": "gitlab/commits/list", "scratch_step_id": "S1",
         "event": "entered", "line": 1},
        {"primitive_id": "gitlab/commits/list", "scratch_step_id": "",
         "event": "completed", "line": 3},
    ]


def test_summarize_reports_routed_pairs_decisions_and_site_breakdown(tmp_path):
    split = {
        "site": "shopping",
        "heldout": [{"intent_template_id": 10, "task_ids": [1, 2]}],
        "gate": {
            "go_if_win_minus_loss_at_least": 1,
            "minimum_templates_with_wins": 1,
        },
    }
    records = {
        "task1_scratch": {"mode": "scratch", "correct": False},
        "task1_routed": {
            "mode": "routed", "correct": True, "intent_template_id": 10,
            "site": "shopping", "route_decision": "adapt",
            "code_incorporated_primitives": [], "declared_used_primitives": [],
        },
        "task2_scratch": {"mode": "scratch", "correct": True},
        "task2_routed": {
            "mode": "routed", "correct": True, "intent_template_id": 10,
            "site": "shopping", "route_decision": "skip",
            "code_incorporated_primitives": [], "declared_used_primitives": [],
        },
    }
    for stem, value in records.items():
        (tmp_path / f"{stem}.json").write_text(__import__("json").dumps(value))
    summary = E.summarize(split, tmp_path, tmp_path / "library")
    assert summary["comparison_mode"] == "routed"
    assert summary["scratch_correct"] == 1 and summary["routed_correct"] == 2
    assert summary["wins"] == 1 and summary["losses"] == 0
    assert summary["route_decisions"] == {"adapt": 1, "skip": 1}
    assert summary["by_site"]["shopping"]["routed_correct"] == 2
