#!/usr/bin/env python3
"""Evaluate a saved browser final state with the official WebArena evaluator.

This adapter deliberately does not consume HAR/network events.  It restores the recorded DOM in
a local Playwright page, wraps that page with WebArena's PseudoPage at the recorded final URL, and
passes the original WebArena task config to the official evaluator_router unchanged apart from
deployment-placeholder resolution.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml


OFFICIAL_COMMIT = "dce04686a56253aefba7b18a4fa0937cf1dc987b"


class _PseudoPage:
    def __init__(self, original_page: Any, url: str):
        self.url = url
        self.original_page = original_page

    def __getattr__(self, name: str) -> Any:
        if name == "url":
            return self.url
        return getattr(self.original_page, name)


def _identity_beartype(value=None, **_kwargs):
    if value is None:
        return lambda wrapped: wrapped
    return value


def _unsupported_helper(*_args, **_kwargs):
    raise RuntimeError(
        "this Navigate config requires a dynamic WebArena helper and cannot be evaluated from "
        "a saved final state"
    )


def _install_official_import_compatibility(llm_fuzzy=None, llm_ua=None) -> None:
    """Supply import-only dependencies not exercised by Navigate final-state configs.

    The evaluator classes themselves are always loaded from the official checkout.  Current
    Navigate configs use URL matching, static DOM JavaScript locators, or exact N/A handling; none
    calls WebArena's API/LLM helper functions or browser action constructors.
    """
    if "beartype" not in sys.modules:
        module = types.ModuleType("beartype")
        module.beartype = _identity_beartype
        sys.modules["beartype"] = module

    if "nltk.tokenize" not in sys.modules:
        nltk = types.ModuleType("nltk")
        tokenize = types.ModuleType("nltk.tokenize")
        tokenize.word_tokenize = lambda text: re.findall(r"\w+|[^\w\s]", str(text))
        nltk.tokenize = tokenize
        sys.modules["nltk"] = nltk
        sys.modules["nltk.tokenize"] = tokenize

    browser_env = sys.modules.setdefault("browser_env", types.ModuleType("browser_env"))
    browser_env.__path__ = []
    actions = types.ModuleType("browser_env.actions")
    actions.Action = dict
    utils = types.ModuleType("browser_env.utils")
    utils.StateInfo = dict
    sys.modules["browser_env.actions"] = actions
    sys.modules["browser_env.utils"] = utils

    helpers = types.ModuleType("evaluation_harness.helper_functions")
    helpers.PseudoPage = _PseudoPage
    for name in (
        "gitlab_get_project_memeber_role",
        "reddit_get_post_url",
        "shopping_get_latest_order_url",
        "shopping_get_sku_latest_review_author",
        "shopping_get_sku_latest_review_rating",
    ):
        setattr(helpers, name, _unsupported_helper)
    helpers.llm_fuzzy_match = llm_fuzzy or _unsupported_helper
    helpers.llm_ua_match = llm_ua or _unsupported_helper
    sys.modules["evaluation_harness.helper_functions"] = helpers


def make_llm_helpers(model_config: str | Path | None):
    if not model_config:
        return None, None
    config = yaml.safe_load(Path(model_config).read_text(encoding="utf-8")) or {}
    if not isinstance(config.get("model"), dict):
        raise ValueError(f"{model_config}: missing model configuration")
    from webwright.skill_factory.llm import configure_llm, llm
    configure_llm(config["model"])

    def fuzzy(pred: str, reference: str, question: str) -> float:
        prompt = (
            "Help a teacher grade a student's answer. Decide whether it is semantically "
            "equivalent to the reference answer. The string N/A means not achievable.\n"
            f"question: {question}\nreference answer: {reference}\nstudent answer: {pred}\n"
            "Conclude with exactly correct, incorrect, or partially correct."
        )
        response = llm("You are a helpful assistant.", prompt, max_tokens=128).lower()
        return 0.0 if "partially correct" in response or "incorrect" in response else float(
            "correct" in response
        )

    def unachievable(pred: str, reference: str, question: str) -> float:
        prompt = (
            f"task: {question}\nactual unachievable reason: {reference}\n"
            f"reported unachievable reason: {pred}\n"
            "Does the reported reason align with the actual reason, even implicitly? "
            "Respond with exactly same or different."
        )
        response = llm("You are a helpful assistant.", prompt, max_tokens=128).lower()
        return 0.0 if "different" in response else float("same" in response)

    return fuzzy, unachievable


def load_official_evaluator(webarena_root: str | Path, model_config=None):
    root = Path(webarena_root).resolve()
    evaluator_source = root / "evaluation_harness" / "evaluators.py"
    if not evaluator_source.is_file():
        raise ValueError(f"official WebArena evaluator missing: {evaluator_source}")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True,
    )
    if revision.returncode != 0 or revision.stdout.strip() != OFFICIAL_COMMIT:
        raise ValueError(
            f"WebArena checkout must be pinned at {OFFICIAL_COMMIT}; "
            f"found {revision.stdout.strip() or 'unknown'}"
        )
    sys.path.insert(0, str(root))
    _install_official_import_compatibility(*make_llm_helpers(model_config))
    from evaluation_harness.evaluators import evaluator_router  # type: ignore
    return evaluator_router


def load_task(tasks_path: str | Path, task_id: int) -> dict:
    rows = json.loads(Path(tasks_path).read_text(encoding="utf-8"))
    return next((row for row in rows if int(row.get("task_id", -1)) == task_id), None) or {}


def resolve_placeholders(value: Any, environments: dict) -> Any:
    if isinstance(value, str):
        result = value
        for placeholder, config in environments.items():
            urls = config.get("urls") or []
            if urls:
                deployment_url = str(urls[0]).rstrip("/")
                parsed = urlsplit(deployment_url)
                # DNS hostnames are case-insensitive.  Magento canonicalizes its redirect target
                # to lowercase, while some deployment manifests use an uppercase machine name;
                # official WebArena's URL matcher compares netloc strings case-sensitively.
                # Normalize only the authority and preserve case-sensitive path/query data.
                if parsed.netloc:
                    deployment_url = urlunsplit(parsed._replace(netloc=parsed.netloc.lower()))
                result = result.replace(placeholder, deployment_url)
        return result
    if isinstance(value, list):
        return [resolve_placeholders(item, environments) for item in value]
    if isinstance(value, dict):
        return {key: resolve_placeholders(item, environments) for key, item in value.items()}
    return value


def validate_final_state(value: dict) -> list[str]:
    errors = []
    if not isinstance(value, dict):
        return ["final state must be a JSON object"]
    if not isinstance(value.get("final_url"), str) or not value["final_url"].strip():
        errors.append("final_url must be a non-empty string")
    if not isinstance(value.get("html"), str) and not isinstance(value.get("html_path"), str):
        errors.append("html or html_path must be supplied")
    status = value.get("document_status")
    if status is not None and (not isinstance(status, int) or not 100 <= status <= 599):
        errors.append("document_status must be null or an HTTP status integer")
    if not isinstance(value.get("answer", ""), str):
        errors.append("answer must be a string")
    if "storage_state_path" in value and not isinstance(value["storage_state_path"], str):
        errors.append("storage_state_path must be a string when supplied")
    return errors


def _resolve_run_artifact(state_path: Path, relative_path: str, label: str) -> Path:
    artifact = (state_path.parent / relative_path).resolve()
    try:
        artifact.relative_to(state_path.parent.resolve())
    except ValueError as error:
        raise ValueError(f"{label} escapes the run directory") from error
    if not artifact.is_file():
        raise ValueError(f"missing {label}: {artifact}")
    return artifact


def evaluate_saved_state(
    *, task_id: int, final_state_path: str | Path, tasks_path: str | Path,
    deployment_config: str | Path, webarena_root: str | Path,
    model_config: str | Path | None = None,
) -> dict:
    state_path = Path(final_state_path)
    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    errors = validate_final_state(final_state)
    if errors:
        return {"score": None, "status": "invalid_final_state", "errors": errors}
    if "html" not in final_state:
        try:
            html_path = _resolve_run_artifact(
                state_path, final_state["html_path"], "saved DOM"
            )
        except ValueError as error:
            return {"score": None, "status": "invalid_final_state",
                    "errors": [str(error)]}
        final_state["html"] = html_path.read_text(encoding="utf-8")
    storage_state = None
    if final_state.get("storage_state_path"):
        try:
            storage_state = _resolve_run_artifact(
                state_path, final_state["storage_state_path"], "browser storage state"
            )
        except ValueError as error:
            return {"score": None, "status": "invalid_final_state",
                    "errors": [str(error)]}
    task = load_task(tasks_path, task_id)
    if not task:
        return {"score": None, "status": "missing_task", "errors": [str(task_id)]}
    environments = json.loads(Path(deployment_config).read_text(encoding="utf-8"))["environments"]
    task = resolve_placeholders(task, environments)
    evaluator_router = load_official_evaluator(webarena_root, model_config)

    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8") as handle:
        json.dump(task, handle)
        handle.flush()
        trajectory = [{}, {"action_type": "STOP", "answer": final_state.get("answer", "")}]
        eval_types = task.get("eval", {}).get("eval_types") or []
        browser = None
        playwright = None
        try:
            if "program_html" in eval_types:
                from playwright.sync_api import sync_playwright
                playwright = sync_playwright().start()
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    storage_state=str(storage_state) if storage_state else None
                )
                page = context.new_page()
                page.set_content(final_state["html"], wait_until="domcontentloaded")
            else:
                page = types.SimpleNamespace()
            pseudo_page = _PseudoPage(page, final_state["final_url"])
            score = float(evaluator_router(handle.name)(
                trajectory=trajectory, config_file=handle.name, page=pseudo_page, client=None,
            ))
        finally:
            if browser is not None:
                browser.close()
            if playwright is not None:
                playwright.stop()
    return {
        "score": score,
        "status": "scored_correct" if score == 1.0 else "scored_incorrect",
        "task_id": task_id,
        "eval_types": eval_types,
        "final_url": final_state["final_url"],
        "official_webarena_commit": OFFICIAL_COMMIT,
        "webarena_root": str(Path(webarena_root).resolve()),
        "llm_model_config": str(Path(model_config).resolve()) if model_config else None,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True, type=int)
    parser.add_argument("--final-state", required=True)
    parser.add_argument("--tasks", required=True)
    parser.add_argument("--deployment-config", required=True)
    parser.add_argument("--webarena-root", required=True)
    parser.add_argument("--model-config")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    result = evaluate_saved_state(
        task_id=args.task_id, final_state_path=args.final_state, tasks_path=args.tasks,
        deployment_config=args.deployment_config, webarena_root=args.webarena_root,
        model_config=args.model_config,
    )
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if result.get("score") is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
