from __future__ import annotations

import importlib.util
import json
import os
import unittest.mock
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
replayer = load_module("run_official", "run_official.py")


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

    def test_agent_environment_prefers_selected_virtualenv(self):
        executable = Path(sys.executable).absolute()
        env = runner.agent_subprocess_env(executable)
        self.assertEqual(env["PATH"].split(runner.os.pathsep)[0], str(executable.parent))
        self.assertEqual(env["VIRTUAL_ENV"], str(executable.parent.parent))

    def test_agent_python_preserves_virtualenv_symlink_path(self):
        selected = runner.resolve_agent_python(str(ROOT / ".venv" / "bin" / "python"))
        self.assertEqual(selected, (ROOT / ".venv" / "bin" / "python").absolute())

    def test_complete_artifact_run_requires_parseable_contract(self):
        output_dir = self.tmp_path / "runs"
        run_dir = output_dir / "official_webarena_task7_20260819_120000"
        run_dir.mkdir(parents=True)
        before = set()
        self.assertIsNone(
            runner.complete_artifact_run(output_dir, "official_webarena_task7", before)
        )
        (run_dir / "final_state.html").write_text("<html></html>", encoding="utf-8")
        (run_dir / "final_state.json").write_text(
            json.dumps(
                {
                    "final_url": "http://example.test/result",
                    "html_path": "final_state.html",
                    "document_status": 200,
                    "answer": "result",
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "agent_response.json").write_text(
            json.dumps({"status": "SUCCESS"}), encoding="utf-8"
        )
        self.assertEqual(
            runner.complete_artifact_run(output_dir, "official_webarena_task7", before),
            run_dir,
        )


if __name__ == "__main__":
    unittest.main()


class HelperDependencyTests(unittest.TestCase):
    """The official site helpers must load for real, and when they cannot, say why.

    Two things went wrong in the skill-arm batches: the evaluator never exported the deployment's
    site URLs, so the official env_config asserted on import; and a loader failure was silently
    downgraded to a stub that reported `unsupported_saved_state`, which reads as a capability
    limit rather than the dependency error it was.
    """

    def test_site_urls_are_exported_from_deployment_config(self):
        environments = {
            "__SHOPPING__": {"urls": ["http://h:7770"]},
            "__SHOPPING_ADMIN__": {"urls": ["http://h:7780/admin"]},
            "__REDDIT__": {"urls": ["http://h:9999"]},
            "__GITLAB__": {"urls": ["http://h:8023"]},
            "__MAP__": {"urls": ["http://h:3000"]},
            "__WIKIPEDIA__": {"urls": ["http://h:8888/wikipedia"]},
            "__HOMEPAGE__": {"urls": ["http://h:4399"]},
        }
        with unittest.mock.patch.dict("os.environ", {}, clear=False):
            for name in ("SHOPPING", "SHOPPING_ADMIN", "REDDIT", "GITLAB", "MAP",
                         "WIKIPEDIA", "HOMEPAGE"):
                os.environ.pop(name, None)
            exported = evaluator.export_site_urls(environments)
            self.assertEqual(exported["SHOPPING_ADMIN"], "http://h:7780/admin")
            self.assertEqual(os.environ["REDDIT"], "http://h:9999")
            # An operator's explicit value wins over the deployment file.
            os.environ["MAP"] = "http://override:3000"
            evaluator.export_site_urls(environments)
            self.assertEqual(os.environ["MAP"], "http://override:3000")

    def test_loader_failure_is_reported_as_dependency_error_not_capability_limit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "browser_env").mkdir()
            (root / "evaluation_harness").mkdir()
            (root / "browser_env" / "env_config.py").write_text("ACCOUNTS = {}\n")
            (root / "evaluation_harness" / "helper_functions.py").write_text(
                "import openai.error  # openai>=1 removed this module\n")
            evaluator._HELPER_LOAD_ERROR = None
            loaded = evaluator._load_official_helpers(root)
            self.assertIsNone(loaded)
            self.assertIsNotNone(evaluator._HELPER_LOAD_ERROR)
            self.assertIn("openai.error", evaluator._HELPER_LOAD_ERROR)
            with self.assertRaises(evaluator.HelperDependencyError) as ctx:
                evaluator._unsupported_helper("x")
            self.assertIn("openai.error", str(ctx.exception))
            self.assertTrue(issubclass(evaluator.HelperDependencyError,
                                       evaluator.UnsupportedSavedStateError))

    def test_dependency_error_maps_to_its_own_status(self):
        result = evaluator.classify_saved_state_error(
            evaluator.HelperDependencyError("No module named 'openai.error'"), task_id=7)
        self.assertEqual(result["status"], "helper_dependency_error")
        self.assertEqual(result["task_id"], 7)
        self.assertIn("openai.error", result["errors"][0])
        plain = evaluator.classify_saved_state_error(
            evaluator.UnsupportedSavedStateError("needs live page"), task_id=7)
        self.assertEqual(plain["status"], "unsupported_saved_state")


class ReplaySkillModuleTests(unittest.TestCase):
    """Replay must carry the skill module the frozen script imports, and verify it."""

    def _run_dir(self, td, tamper=False):
        run_dir = Path(td) / "task1_package_import_20260101_000000"
        run_dir.mkdir()
        (run_dir / "final_script.py").write_text("print('hi')\n")
        module = run_dir / "skillnet_lib.py"
        module.write_text("async def f(page):\n    return 1\n")
        digest = replayer.sha256_file(module)
        manifest = {"module_file": "skillnet_lib.py", "module_sha256": digest,
                    "functions": [{"name": "f", "sha256": "abc"}]}
        (run_dir / "skillnet_lib.manifest.json").write_text(json.dumps(manifest))
        if tamper:
            module.write_text("async def f(page):\n    return 2\n")
        return run_dir

    def test_module_is_staged_into_workspace_with_matching_hash(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = self._run_dir(td)
            workspace = run_dir / "replay"
            workspace.mkdir()
            staged = replayer.stage_skill_module(run_dir, workspace)
            self.assertEqual(staged["status"], "staged")
            self.assertTrue((workspace / "skillnet_lib.py").is_file())
            self.assertTrue((workspace / "skillnet_lib.manifest.json").is_file())
            self.assertEqual(staged["module_sha256"], replayer.sha256_file(workspace / "skillnet_lib.py"))

    def test_tampered_module_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = self._run_dir(td, tamper=True)
            workspace = run_dir / "replay"
            workspace.mkdir()
            staged = replayer.stage_skill_module(run_dir, workspace)
            self.assertEqual(staged["status"], "skill_module_hash_mismatch")
            self.assertFalse((workspace / "skillnet_lib.py").exists())

    def test_runs_without_a_module_are_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "task1_scratch_20260101_000000"
            run_dir.mkdir()
            workspace = run_dir / "replay"
            workspace.mkdir()
            self.assertEqual(replayer.stage_skill_module(run_dir, workspace)["status"], "none")
