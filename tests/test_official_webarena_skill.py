from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "official-webarena" / "scripts"


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


evaluator = load_module("webarena_final_state_eval", "webarena_final_state_eval.py")
runner = load_module("official_webarena", "official_webarena.py")


def write_fixture(tmp_path: Path):
    webarena = tmp_path / "webarena"
    tasks = webarena / "config_files" / "test.raw.json"
    tasks.parent.mkdir(parents=True)
    tasks.write_text(
        json.dumps(
            [
                {
                    "task_id": 7,
                    "intent": "Find the project owner",
                    "sites": ["gitlab"],
                    "start_url": "__GITLAB__/explore",
                    "eval": {"eval_types": ["string_match"]},
                }
            ]
        ),
        encoding="utf-8",
    )
    deployment = tmp_path / "deployment.json"
    deployment.write_text(
        json.dumps(
            {
                "environments": {
                    "__GITLAB__": {
                        "urls": ["http://HOST.Example:8023"],
                        "credentials": {"username": "alice", "password": "secret"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return webarena, tasks, deployment


def args_for(webarena: Path, deployment: Path):
    return SimpleNamespace(
        task_id=7,
        webarena_root=str(webarena),
        tasks=None,
        deployment_config=str(deployment),
    )


class OfficialWebArenaSkillTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_inspect_uses_original_task_and_redacts_credentials(self):
        webarena, _, deployment = write_fixture(self.tmp_path)
        result = runner.inspect_task(args_for(webarena, deployment))
        self.assertEqual(result["task_source"], "official_webarena")
        self.assertEqual(result["intent"], "Find the project owner")
        self.assertEqual(result["start_url"], "http://host.example:8023/explore")
        self.assertEqual(result["task_interface"], "RETRIEVE")
        self.assertTrue(result["credentials_available"])
        self.assertNotIn("secret", json.dumps(result))

    def test_prompt_contains_artifact_contract_and_runtime_credentials(self):
        _, tasks, deployment_path = write_fixture(self.tmp_path)
        task = evaluator.load_task(tasks, 7)
        deployment = runner.load_deployment(deployment_path)
        prompt = runner.build_prompt(task, deployment, "http://host.example:8023/explore")
        self.assertIn("Find the project owner", prompt)
        self.assertIn("username `alice`", prompt)
        self.assertIn("password `secret`", prompt)
        self.assertIn("final_state.html", prompt)
        self.assertIn("agent_response.json", prompt)

    def test_unresolved_placeholder_fails_before_agent_run(self):
        webarena, _, deployment = write_fixture(self.tmp_path)
        value = json.loads(deployment.read_text(encoding="utf-8"))
        value["environments"] = {}
        deployment.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unresolved deployment placeholders"):
            runner.task_context(args_for(webarena, deployment))

    def test_recursive_placeholder_resolution_preserves_path_case(self):
        resolved = evaluator.resolve_placeholders(
            {"start_url": "__SHOPPING__/CaseSensitive?Q=A"},
            {"__SHOPPING__": {"urls": ["HTTP://HOST.Example:7770"]}},
        )
        self.assertEqual(
            resolved["start_url"], "http://host.example:7770/CaseSensitive?Q=A"
        )

    def test_multi_start_task_opens_first_and_prompts_all_tabs(self):
        task = {
            "intent": "Compare two sites",
            "sites": ["gitlab", "reddit"],
            "start_url": "__GITLAB__/explore |AND| __REDDIT__/",
            "eval": {"eval_types": ["string_match"]},
        }
        deployment = {
            "environments": {
                "__GITLAB__": {"urls": ["http://host:8023"]},
                "__REDDIT__": {"urls": ["http://host:9999"]},
            }
        }
        resolved = evaluator.resolve_placeholders(task, deployment["environments"])
        self.assertEqual(runner.task_start_url(resolved), "http://host:8023/explore")
        prompt = runner.build_prompt(task, deployment, "http://host:8023/explore")
        self.assertIn("http://host:8023/explore", prompt)
        self.assertIn("http://host:9999/", prompt)
        self.assertIn("separate tab", prompt)

    def test_final_state_validation_and_path_confinement(self):
        state_path = self.tmp_path / "run" / "final_state.json"
        state_path.parent.mkdir()
        outside = self.tmp_path / "outside.html"
        outside.write_text("outside", encoding="utf-8")
        errors = evaluator.validate_final_state(
            {"final_url": "", "html_path": "final_state.html", "document_status": "200"}
        )
        self.assertIn("final_url must be a non-empty string", errors)
        self.assertIn("document_status must be null or an HTTP status integer", errors)
        with self.assertRaisesRegex(ValueError, "escapes the run directory"):
            evaluator._resolve_run_artifact(state_path, "../outside.html", "saved DOM")

    def test_not_found_is_normalized_to_official_na(self):
        run_dir = self.tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "final_state.json").write_text(
            json.dumps(
                {
                    "final_url": "http://example.test",
                    "html_path": "final_state.html",
                    "document_status": 200,
                    "answer": "No result",
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "agent_response.json").write_text(
            json.dumps({"status": "NOT_FOUND_ERROR"}), encoding="utf-8"
        )
        runner.normalize_not_found(run_dir)
        state = json.loads((run_dir / "final_state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["answer"], "N/A")
        self.assertTrue((run_dir / "final_state.agent.json").is_file())


if __name__ == "__main__":
    unittest.main()
