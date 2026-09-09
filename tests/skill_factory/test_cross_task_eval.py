import importlib.util
import json
import os
import sys
import signal
import subprocess
from pathlib import Path


_PATH = Path(__file__).parents[2] / "evals" / "webarena" / "cross_task_eval.py"
_SPEC = importlib.util.spec_from_file_location("cross_task_eval", _PATH)
E = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(E)


def test_official_prompt_contract_has_no_synthetic_task_type_or_agent_response():
    assert '"task_type":"RETRIEVE"' not in E.OFFICIAL_FINAL_STATE_SPEC
    assert "agent_response.json" not in E.OFFICIAL_FINAL_STATE_SPEC
    assert "final_state.html" in E.OFFICIAL_FINAL_STATE_SPEC
    assert "final_state.json" in E.OFFICIAL_FINAL_STATE_SPEC


def test_official_storage_state_note_matches_deployment_auth_root(tmp_path):
    auth_root = tmp_path / ".auth"
    auth_root.mkdir()
    state = auth_root / "gitlab.reddit_state.json"
    state.write_text("{}")
    task = {"task_id": 552, "storage_state": ".auth/gitlab.reddit_state.json"}
    config = {"auth_root": str(auth_root)}

    assert E.official_auth_state(task, config) == str(state.resolve())
    note = E.official_storage_state_note(task, config)
    assert f'storage_state="{state.resolve()}"' in note
    assert "Never branch" in note
    assert "never log in by hand" in note


def test_agent_subprocess_env_prepends_runner_virtualenv():
    env = E.agent_subprocess_env(
        "/workspace/eval/.venv/bin/python", {"PATH": "/usr/bin:/bin", "KEEP": "1"}
    )
    assert env["PATH"].split(":") == ["/workspace/eval/.venv/bin", "/usr/bin", "/bin"]
    assert env["VIRTUAL_ENV"] == "/workspace/eval/.venv"
    assert env["KEEP"] == "1"


def test_agent_subprocess_env_deduplicates_runner_bin():
    env = E.agent_subprocess_env(
        "/workspace/eval/.venv/bin/python",
        {"PATH": "/usr/bin:/workspace/eval/.venv/bin:/bin"},
    )
    assert env["PATH"].split(":") == ["/workspace/eval/.venv/bin", "/usr/bin", "/bin"]


def test_agent_subprocess_env_preserves_virtualenv_symlink_parent(tmp_path):
    system_python = tmp_path / "system" / "python"
    system_python.parent.mkdir()
    system_python.write_text("")
    venv_python = tmp_path / "eval" / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.symlink_to(system_python)
    env = E.agent_subprocess_env(str(venv_python), {"PATH": "/usr/bin"})
    assert env["PATH"].split(":")[0] == str(venv_python.parent)
    assert env["VIRTUAL_ENV"] == str(venv_python.parent.parent)


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


def test_not_found_status_normalizes_arbitrary_text_sentinel_to_official_na(tmp_path):
    (tmp_path / "agent_response.json").write_text(json.dumps({
        "task_type": "RETRIEVE",
        "status": "NOT_FOUND_ERROR",
        "retrieved_data": None,
        "error_details": None,
    }))
    (tmp_path / "final_state.json").write_text(json.dumps({
        "final_url": "https://example.test/results",
        "html_path": "final_state.html",
        "document_status": 200,
        "answer": "NONE",
    }))

    assert E.normalize_official_answer(tmp_path) is True
    normalized = json.loads((tmp_path / "final_state.json").read_text())
    assert normalized["answer"] == "N/A"
    assert normalized["artifact_normalizations"] == [
        "not_found_status_to_official_na_v1"
    ]


def test_official_score_does_not_reuse_stale_output_after_subprocess_failure(
    tmp_path, monkeypatch
):
    (tmp_path / "agent_response.json").write_text(json.dumps({
        "task_type": "RETRIEVE", "status": "SUCCESS",
        "retrieved_data": ["answer"], "error_details": None,
    }))
    (tmp_path / "final_state.json").write_text(json.dumps({
        "final_url": "https://example.test/results",
        "html_path": "final_state.html",
        "document_status": 200,
        "answer": "answer",
    }))
    stale = tmp_path / "webarena_final_state_eval.json"
    stale.write_text('{"score": 1.0, "official_webarena_commit": "old"}')
    monkeypatch.setattr(E.subprocess, "run", lambda *args, **kwargs: E.subprocess.CompletedProcess(
        args[0], 1, stdout="", stderr="evaluator failed"
    ))

    score, provenance = E.score_navigate(
        7, tmp_path, tmp_path / "deployment.json", tmp_path / "tasks.json",
        tmp_path / "webarena", tmp_path / "model.yaml",
    )

    assert score is None
    assert provenance["error"] == "evaluator failed"
    assert not stale.exists()


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


def test_official_artifact_uses_state_not_advisory_response_type(tmp_path):
    run = tmp_path / "task45_workflow_001"
    run.mkdir()
    (run / "agent_response.json").write_text(json.dumps({
        "task_type": "RETRIEVE",
        "status": "SUCCESS",
        "retrieved_data": ["done"],
        "error_details": None,
    }))
    (run / "final_state.json").write_text(json.dumps({
        "final_url": "https://example.test/final",
        "html_path": "final_state.html",
        "answer": ["done"],
    }))
    (run / "final_state.html").write_text("<html><body>done</body></html>")

    assert E.has_complete_agent_response(tmp_path, "task45_workflow", "mutate") is False
    assert E.has_complete_official_artifact(tmp_path, "task45_workflow") is True


def test_vanilla_final_state_interface_does_not_reveal_task_type():
    assert "NAVIGATE" not in E.VANILLA_FINAL_STATE_SPEC
    assert "task_type" not in E.VANILLA_FINAL_STATE_SPEC
    assert "agent_response" not in E.VANILLA_FINAL_STATE_SPEC
    assert "final_state.json" in E.VANILLA_FINAL_STATE_SPEC
    assert "mirror live input" in E.VANILLA_FINAL_STATE_SPEC


def test_navigate_capture_preserves_live_form_control_state():
    assert "mirror each" in E.NAVIGATE_SPEC
    assert "input's current `value`/`checked`" in E.NAVIGATE_SPEC
    assert "select option's current" in E.NAVIGATE_SPEC


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
                    "primitive_calls": [{"primitive_id": "map/search", "bindings": {
                        "base_url": "runtime.base_url", "query": "task.place_query",
                    }, "closed_acquisition": "place lookup"}],
                    "reason": "useful acquisition", "remaining_gap": ["filter"],
                    "task_structure": "single_stage"}
        if system.startswith("Classify exactly two structural properties"):
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
        "find a place", tmp_path, site="map",
        runtime_context={"available_bindings": ["runtime.base_url"]}, llm_fn=fake_llm,
    )
    assert out.decision == "adapt"
    assert [item["primitive_id"] for item in out.primitives] == ["map/search"]
    assert "Do not require or mention a scratch plan" in seen["system"]
    assert "choose ADAPT" in seen["system"]
    assert "do not invent a comparison" in seen["system"]
    assert "lacks that qualification field" in seen["system"]
    assert "scratch_plan" not in seen["user"]
    assert "contract refinement" in seen["verifier_system"]
    assert "narrower closed acquisition" in seen["verifier_system"]
    assert "complete but unqualified collection" in seen["verifier_system"]
    assert "runtime.base_url" in seen["user"]
    assert "runtime.base_url" in seen["verifier_user"]
    assert "nearest pharmacy from fully named CMU" in seen["risk_system"]
    assert "unclosed_qualified_population" in seen["risk_system"]
    assert "last order conditioner" in seen["risk_system"]
    assert "order_number and site-local order_id" in seen["risk_system"]
    assert "API-internal authentication" in seen["risk_system"]
    assert "candidate_capability_reachability" in seen["risk_system"]
    assert "candidate_capability_reachability" in seen["risk_user"]
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
        if system.startswith("Classify exactly two structural properties"):
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


def test_direct_navigate_use_rejects_api_only_data_acquisition(tmp_path):
    root = tmp_path / "shopping" / "final_candidate"
    root.mkdir(parents=True)
    (root / "index.json").write_text(json.dumps({
        "site": "shopping", "status": "candidate", "primitives": [{
            "primitive_id": "shopping/catalog/search_products_graphql",
            "method_code": (
                "async def search_products_graphql(self, query):\n"
                "    return await self.page.request.get('/graphql')\n"
            ),
            "feature": "catalog", "method": "search_products_graphql",
            "capability": "return typed product search records",
            "owns": ["Issue a GraphQL product search request"],
            "browser_effects": {"navigates_live_page": False},
            "output_contract": {"properties": {"products": {"type": "array"}}},
        }],
    }))

    def fake_llm(system, user):
        if system.startswith("Classify exactly two structural properties"):
            return {"chained_open_world": False, "upstream_entity": "",
                    "downstream_operation": "", "reason": "single search"}
        if system.startswith("Route site primitives"):
            assert '"task_type": "navigate"' in user
            return {
                "decision": "use",
                "primitive_ids": ["shopping/catalog/search_products_graphql"],
                "primitive_calls": [{
                    "primitive_id": "shopping/catalog/search_products_graphql",
                    "bindings": {"query": "task.query"},
                    "closed_acquisition": "product search",
                }],
                "reason": "search data is available", "remaining_gap": [],
            }
        raise AssertionError("deterministic navigation guard must reject before verifier")

    out = E.retrieve_direct_primitives(
        'Search for "switch accessories"', tmp_path, site="shopping",
        runtime_context={"task_type": "navigate", "available_bindings": [
            "runtime.base_url", "runtime.browser_page",
        ]},
        llm_fn=fake_llm,
    )

    assert out.decision == "skip"
    assert out.primitives == []
    assert "live browser state" in out.reason
    assert out.proposal["primitive_calls"] == []


def test_direct_navigate_use_accepts_metadata_projected_live_browser_effect(tmp_path):
    root = tmp_path / "map" / "final_candidate"
    root.mkdir(parents=True)
    (root / "index.json").write_text(json.dumps({
        "site": "map", "status": "candidate", "primitives": [{
            "primitive_id": "map/routes/get_route_summary",
            "method_code": (
                "async def get_route_summary(self, origin, destination):\n"
                "    await self.page.goto('/directions')\n"
                "    await self.page.locator('#route_from').fill(origin)\n"
                "    return {'final_url': self.page.url}\n"
            ),
            "feature": "routes", "method": "get_route_summary",
            "capability": "navigate the live directions UI",
            "owns": ["Navigate to and submit the site's directions page"],
            "output_contract": {"properties": {"final_url": {"type": "string"}}},
        }],
    }))

    def fake_llm(system, user):
        if system.startswith("Classify exactly two structural properties"):
            return {"chained_open_world": False, "upstream_entity": "",
                    "downstream_operation": "", "reason": "named endpoints"}
        if system.startswith("Route site primitives"):
            assert '"navigates_live_page": true' in user
            assert "method_code" not in user
            return {
                "decision": "use", "primitive_ids": ["map/routes/get_route_summary"],
                "primitive_calls": [{
                    "primitive_id": "map/routes/get_route_summary",
                    "bindings": {"origin": "task.origin", "destination": "task.destination"},
                    "closed_acquisition": "live directions page",
                }],
                "reason": "establishes final route page", "remaining_gap": [],
            }
        return {
            "verdict": "accept",
            "checks": {"input_reachability": "pass", "guarantee_sufficiency": "pass",
                       "closed_acquisition": "pass"},
            "closed_acquisitions": ["live directions page"],
            "reason": "navigation is closed",
        }

    out = E.retrieve_direct_primitives(
        "Get directions from A to B", tmp_path, site="map",
        runtime_context={"task_type": "navigate", "available_bindings": [
            "runtime.base_url", "runtime.browser_page",
        ]}, llm_fn=fake_llm,
    )

    assert out.decision == "use"
    assert [item["primitive_id"] for item in out.primitives] == [
        "map/routes/get_route_summary"
    ]


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
        if system.startswith("Classify exactly two structural properties"):
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


def test_deterministic_guard_requires_topology_for_street_side_place_selection():
    coordinate_search = {
        "primitive_id": "map/places/search_places",
        "output_contract": {"properties": {
            "results": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "latitude": {"type": "number"},
                "longitude": {"type": "number"},
            }}},
        }},
        "guarantees": {"completeness": "partial"},
    }

    reason = E.deterministic_direct_contract_guard(
        "Find the bus stop on the museum side of the street near CMU",
        [coordinate_search], site="map",
    )

    assert "topology" in reason
    # Ordinary proximity remains eligible; it does not require a street-side relation.
    assert E.deterministic_direct_contract_guard(
        "Find an Apple Store near Pitt", [coordinate_search], site="map",
    ) is None


def test_downstream_only_open_candidate_operator_is_marked_late_bound():
    route = {
        "primitive_id": "travel/objective/measure",
        "does_not_own": [
            "Choosing which destination to query",
            "Ranking or deduplicating multiple destinations",
        ],
        "output_contract": {"properties": {
            "duration_seconds": {"type": "number"},
        }},
    }
    proposal = {
        "decision": "adapt",
        "primitive_ids": [route["primitive_id"]],
        "primitive_calls": [{
            "primitive_id": route["primitive_id"],
            "bindings": {"destination": "task.category"},
        }],
    }

    out = E.annotate_direct_late_binding(
        "Find the closest provider and measure travel time", proposal, [route],
    )

    assert out["late_bind_required"] is True
    assert out["late_bind_policy"] == {
        "input_source": "validated_upstream_candidate_record",
        "forbid_unresolved_category_binding": True,
    }


def test_candidate_acquisition_and_named_inputs_do_not_get_false_late_binding():
    search = {
        "primitive_id": "catalog/candidates/search",
        "does_not_own": ["Ranking candidates"],
        "output_contract": {"properties": {"results": {"type": "array"}}},
    }
    selected = {"decision": "use", "primitive_ids": [search["primitive_id"]]}
    assert "late_bind_required" not in E.annotate_direct_late_binding(
        "Find the nearest matching item", selected, [search],
    )

    detail = {
        "primitive_id": "catalog/detail/read",
        "does_not_own": ["Choosing which item"],
        "output_contract": {"properties": {"price": {"type": "number"}}},
    }
    selected = {"decision": "use", "primitive_ids": [detail["primitive_id"]]}
    assert "late_bind_required" not in E.annotate_direct_late_binding(
        "Read the price of the fully named item", selected, [detail],
    )


def test_deterministic_guard_requires_actual_all_pages_binding_not_schema_support():
    orders = {
        "primitive_id": "shopping/orders/list_authenticated_customer_orders_graphql",
        "input_contract": {"properties": {"retrieval_mode": {
            "type": "string", "enum": ["single_page", "all_pages"],
        }}},
        "output_contract": {"properties": {"orders": {"type": "array"}}},
        "guarantees": {"completeness": "conditional"},
    }
    task = "What is the date when I made my first purchase on this site?"
    assert "exhaustive" in E.deterministic_direct_contract_guard(
        task, [orders], site="shopping",
        proposal={"primitive_calls": [{"primitive_id": orders["primitive_id"],
                                        "bindings": {"retrieval_mode": "single_page",
                                                     "page_number": 1}}]},
    )
    assert E.deterministic_direct_contract_guard(
        task, [orders], site="shopping",
        proposal={"primitive_calls": [{"primitive_id": orders["primitive_id"],
                                        "bindings": {"retrieval_mode": "all_pages",
                                                     "page_number": 1}}]},
    ) is None


def test_deterministic_guard_rejects_unclosed_qualified_population_exposure():
    reason = E.deterministic_direct_contract_guard(
        "Tell me when I last ordered my conditioner?",
        [],
        site="shopping",
        exposure_risk={
            "chained_open_world": False,
            "unclosed_qualified_population": True,
        },
    )
    assert "qualification field absent" in reason


def test_candidate_capability_reachability_marks_only_exact_unmet_ids():
    summary = E._candidate_capability_reachability([
        {
            "primitive_id": "shopping/orders/list",
            "requires": [],
            "provides": ["shopping.orders"],
        },
        {
            "primitive_id": "shopping/orders/detail",
            "requires": ["shopping.authenticated_customer_session",
                         "caller supplies an order id"],
            "provides": ["shopping.order_detail"],
        },
    ], {"available_states": []})
    assert summary == [
        {"primitive_id": "shopping/orders/list", "unmet_capability_requires": []},
        {"primitive_id": "shopping/orders/detail", "unmet_capability_requires": [
            "shopping.authenticated_customer_session"
        ]},
    ]


def test_minimal_proposal_prunes_partial_fallbacks_and_unused_auth():
    complete = {
        "primitive_id": "shopping/orders/graphql", "feature": "orders",
        "requires": [], "provides": ["orders.graphql"],
        "guarantees": {"completeness": "conditional", "collection_scope": "query"},
    }
    partial = {
        "primitive_id": "shopping/orders/html", "feature": "orders",
        "requires": ["customer.authenticated"], "provides": ["orders.page"],
        "guarantees": {"completeness": "partial", "collection_scope": "page"},
    }
    auth = {
        "primitive_id": "shopping/auth/login", "feature": "auth",
        "requires": [], "provides": ["customer.authenticated"],
        "guarantees": {"completeness": "conditional", "collection_scope": "single"},
    }
    proposal = {
        "decision": "adapt",
        "primitive_ids": [complete["primitive_id"], partial["primitive_id"], auth["primitive_id"]],
        "primitive_calls": [
            {"primitive_id": complete["primitive_id"],
             "bindings": {"retrieval_mode": "all_pages", "page_number": 1}},
            {"primitive_id": partial["primitive_id"], "bindings": {}},
            {"primitive_id": auth["primitive_id"], "bindings": {}},
        ],
    }
    out = E.minimize_direct_primitive_proposal(
        "What is the date of my first order?", proposal, [complete, partial, auth],
    )
    assert out["primitive_ids"] == [complete["primitive_id"]]
    assert [call["primitive_id"] for call in out["primitive_calls"]] == [
        complete["primitive_id"]
    ]


def test_reads_valid_primitive_execution_events(tmp_path):
    (tmp_path / "primitive_execution_trace.jsonl").write_text("\n".join([
        json.dumps({"primitive_id": "gitlab/commits/list", "scratch_step_id": "S1",
                    "event": "candidate_set_ready"}),
        json.dumps({"primitive_id": "gitlab/commits/list", "scratch_step_id": "S1",
                    "event": "entered"}),
        json.dumps({"primitive_id": "gitlab/commits/list", "event": "fallback_completed",
                    "source_independent": True,
                    "acquisition_complete_for_scope": False}),
        "not-json",
        json.dumps({"primitive_id": "gitlab/commits/list", "event": "completed"}),
        json.dumps({"primitive_id": "gitlab/commits/list", "event": "unknown"}),
    ]))
    assert E.read_primitive_execution_trace(tmp_path) == [
        {"primitive_id": "gitlab/commits/list", "scratch_step_id": "S1",
         "event": "candidate_set_ready", "line": 1},
        {"primitive_id": "gitlab/commits/list", "scratch_step_id": "S1",
         "event": "entered", "line": 2},
        {"primitive_id": "gitlab/commits/list", "scratch_step_id": "",
         "event": "fallback_completed", "line": 3,
         "source_independent": True, "acquisition_complete_for_scope": False},
        {"primitive_id": "gitlab/commits/list", "scratch_step_id": "",
         "event": "completed", "line": 5},
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


# --- Common base prompt, skill-module provenance, and diagnostic statuses -------------------

_HINT_PATH = Path(__file__).parents[2] / "evals" / "webarena" / "skillnet_hint.py"
_HINT_SPEC = importlib.util.spec_from_file_location("skillnet_hint", _HINT_PATH)
H = importlib.util.module_from_spec(_HINT_SPEC)
_HINT_SPEC.loader.exec_module(H)


def _official_task():
    return {"task_id": 1, "intent": "Find the project owner", "sites": ["gitlab"],
            "intent_template_id": 1, "start_url": "__GITLAB__/explore",
            "storage_state": "./.auth/gitlab_state.json", "eval": {"eval_types": ["url_match"]}}


def test_base_prompt_is_identical_across_modes_for_official_tasks():
    """Every arm must receive the same base prompt; only the prepended skill material differs."""
    task = _official_task()
    prompts = {mode: E.build_base_prompt(task, "official_webarena", "http://h:8023/explore",
                                         login="\nYou are already signed in.", schema_note="",
                                         task_type="navigate", vanilla_task_interface=False)
               for mode in ("scratch", "primitive", "package_import")}
    assert len(set(prompts.values())) == 1
    base = prompts["scratch"]
    assert base.startswith("Complete this web task.")
    assert "## Required output artifacts" in base
    assert "## Abstraction boundary" not in base
    assert "If login is required" not in base


def test_skill_module_manifest_records_hashes_and_imports_from_workspace(tmp_path):
    picked = [{"name": "get_route", "signature": "async def get_route(page)",
               "docstring": "Return the route.", "source": "async def get_route(page):\n    return 1\n"}]
    seed = tmp_path / "seed"
    module = H.write_skill_module(picked, "http://h:3000", seed / "skillnet_lib.py",
                                  manifest_path=seed / "skillnet_lib.manifest.json",
                                  library_root=None)
    manifest = json.loads((seed / "skillnet_lib.manifest.json").read_text())
    assert manifest["module_file"] == "skillnet_lib.py"
    assert manifest["module_sha256"] == H.sha256_file(module)
    assert manifest["functions"] == [{"name": "get_route",
                                      "sha256": H.sha256_text(picked[0]["source"])}]
    hint = H.render_import_hint(picked, "http://h:3000", module_name="skillnet_lib")
    assert 'os.environ["WORKSPACE_DIR"]' in hint
    assert "from skillnet_lib import get_route" in hint
    assert str(seed) not in hint  # no absolute path leaks into the prompt
    # The module must import from a clean directory that is not the one it was written in.
    clean = tmp_path / "clean_workspace"
    clean.mkdir()
    (clean / "skillnet_lib.py").write_bytes(module.read_bytes())
    out = subprocess.run([sys.executable, "-c",
                          "import os,sys; sys.path.insert(0, os.environ['WORKSPACE_DIR']); "
                          "from skillnet_lib import get_route; print('ok')"],
                         env={**os.environ, "WORKSPACE_DIR": str(clean)},
                         capture_output=True, text=True, cwd=tmp_path)
    assert out.stdout.strip() == "ok", out.stderr


def test_agent_command_seeds_skill_module_into_run_dir(tmp_path):
    cmd = E.agent_command("prompt", "task1_package_import", "http://h", tmp_path,
                          "model.yaml", seed_files=[tmp_path / "a.py", tmp_path / "b.json"])
    assert cmd[cmd.index("--seed-file") + 1] == str(tmp_path / "a.py")
    assert cmd.count("--seed-file") == 2
    assert "--seed-file" not in E.agent_command("prompt", "task1_scratch", "http://h",
                                                tmp_path, "model.yaml")


def test_execution_and_evaluation_status_are_separate_dimensions():
    assert E.execution_status(timed_out=True, returncode=None, has_state=False) == "timeout"
    assert E.execution_status(timed_out=False, returncode=1, has_state=False) == "process_error"
    assert E.execution_status(timed_out=False, returncode=0, has_state=False) == "missing_final_state"
    assert E.execution_status(timed_out=False, returncode=-15, has_state=True) == "completed"
    assert E.evaluation_status(None) == "not_evaluated"
    assert E.evaluation_status({"status": "scored_correct"}) == "scored"
    assert E.evaluation_status({"status": "helper_dependency_error"}) == "dependency_error"
    assert E.evaluation_status({"status": "unsupported_saved_state"}) == "unsupported"
    assert E.evaluation_status({"status": "invalid_final_state"}) == "evaluation_failed"
