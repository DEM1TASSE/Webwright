#!/usr/bin/env python3
"""Score a saved Webwright browser state with pinned official WebArena code."""
from __future__ import annotations

import argparse
import json
import os
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


class UnsupportedSavedStateError(RuntimeError):
    """The official evaluator needs something a saved DOM cannot provide."""


class HelperDependencyError(UnsupportedSavedStateError):
    """The official site helpers could not be imported, so they were never available at all.

    Distinct from a genuine saved-state limit: nothing about the task is unsupported, the
    evaluator's own dependencies are missing. Reporting it under `unsupported_saved_state`
    hid a broken environment behind a capability label for two whole batches.
    """


_HELPER_LOAD_ERROR: str | None = None
_SITE_ENV_NAMES = {
    "__SHOPPING__": "SHOPPING", "__SHOPPING_ADMIN__": "SHOPPING_ADMIN", "__REDDIT__": "REDDIT",
    "__GITLAB__": "GITLAB", "__MAP__": "MAP", "__WIKIPEDIA__": "WIKIPEDIA",
    "__HOMEPAGE__": "HOMEPAGE",
}


def export_site_urls(environments: dict) -> dict:
    """Publish the deployment's site URLs as the env vars the official checkout asserts on.

    `browser_env/env_config.py` raises at import unless all seven are set, and the official
    helpers import it. The runner has always known these URLs from the deployment file; the
    evaluator just never handed them over, so the helper module failed to load and the stub
    path took every helper task. An operator's explicit value is left alone.
    """
    exported = {}
    for placeholder, name in _SITE_ENV_NAMES.items():
        urls = (environments.get(placeholder) or {}).get("urls") or []
        if urls and not os.environ.get(name):
            os.environ[name] = urls[0]
        if os.environ.get(name):
            exported[name] = os.environ[name]
    return exported


def classify_saved_state_error(error: Exception, task_id) -> dict:
    status = ("helper_dependency_error" if isinstance(error, HelperDependencyError)
              else "unsupported_saved_state")
    return {"score": None, "status": status, "errors": [str(error)], "task_id": task_id}
    """The official evaluator needs information absent from a saved DOM."""


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
    if _HELPER_LOAD_ERROR:
        raise HelperDependencyError(
            "official site helpers were not loaded, so the evaluator's dynamic helper is "
            f"unavailable: {_HELPER_LOAD_ERROR}")
    raise UnsupportedSavedStateError(
        "the official evaluator requested a dynamic site helper that cannot be "
        "reconstructed from a saved DOM"
    )


def _load_official_helpers(root):
    """Import the pinned checkout's helper_functions so the LLM judges are the official ones."""
    import importlib.util

    env_config_path = Path(root) / "browser_env" / "env_config.py"
    helpers_path = Path(root) / "evaluation_harness" / "helper_functions.py"
    if not env_config_path.is_file() or not helpers_path.is_file():
        return None
    # helper_functions imports `llms.providers.openai_utils`, which only resolves with the
    # checkout on sys.path.
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    browser_env = sys.modules.setdefault("browser_env", types.ModuleType("browser_env"))
    browser_env.__path__ = []
    for name, path in (("browser_env.env_config", env_config_path),
                       ("evaluation_harness.helper_functions", helpers_path)):
        if name in sys.modules and getattr(sys.modules[name], "__file__", None):
            continue
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as error:
            global _HELPER_LOAD_ERROR
            _HELPER_LOAD_ERROR = f"{type(error).__name__}: {error} (while importing {name})"
            sys.modules.pop(name, None)
            return None
    _HELPER_LOAD_ERROR = None
    return sys.modules["evaluation_harness.helper_functions"]


def _install_official_import_compatibility(llm_fuzzy=None, llm_ua=None, root=None) -> None:
    """Provide import-only dependencies while preserving official evaluator classes."""
    if "beartype" not in sys.modules:
        module = types.ModuleType("beartype")
        module.beartype = _identity_beartype
        sys.modules["beartype"] = module

    try:
        import nltk.tokenize  # noqa: F401  -- official tokeniser, keeps must_include faithful
    except Exception:
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

    official = _load_official_helpers(root) if root else None
    if official is not None:
        # Official site helpers come from the pinned checkout. The judges keep the official
        # prompt and parameters but must run on JUDGE_MODEL: the official hard-coded
        # gpt-4-1106-preview is not served by this deployment's gateway.
        if llm_fuzzy:
            official.llm_fuzzy_match = llm_fuzzy
        if llm_ua:
            official.llm_ua_match = llm_ua
        return
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


# Official judge settings at the pinned commit. gpt-4-1106-preview is not served by the
# deployment's gateway, so JUDGE_MODEL is the closest available model; everything else --
# prompt text, temperature, max_tokens, top_p and the verdict parsing -- is the official one.
OFFICIAL_JUDGE_MODEL = "gpt-4-1106-preview"
JUDGE_MODEL = os.environ.get("WEBARENA_JUDGE_MODEL", "gpt-4o")


def _official_fuzzy_message(pred: str, reference: str, question: str) -> str:
    message = (
        "Help a teacher to grade the answer of a student given a question. Keep in mind that "
        "the student may use different phrasing or wording to answer the question. The goal is "
        "to evaluate whether the answer is semantically equivalent to the reference answer.\n"
    )
    message += f"question: {question}\n"
    message += f"reference answer: {reference}\n"
    message += "all the string 'N/A' that you see is a special sequence that means 'not achievable'\n"
    message += f"student answer: {pred}\n"
    message += "Conclude the judgement by correct/incorrect/partially correct."
    return message


def _official_ua_message(pred: str, reference: str, question: str) -> str:
    message = ""
    message += f"task: {question}\n"
    message += f"actual unachievable reason: {reference}\n"
    message += f"reported unachievable reason: {pred}\n"
    message += (
        "The task described above is inherently unachievable due to the reason specified under "
        "'actual unachievable reason'. An individual previously attempted this task and was "
        "unable to complete it. They provided a reason for their failure, which is listed under "
        "'reported unachievable reason'. Your role is to review both the actual and reported "
        "reasons. Determine if the reported reason aligns with the actual reason, even if "
        "implicitly. If the stated reason is in line with the actual reason, respond with "
        "'same'. Otherwise, respond with 'different'."
    )
    return message


def _judge_auth_headers(base):
    """Azure authenticates with an `api-key` header; OpenAI-compatible bases use a bearer token.

    The judge otherwise speaks the same chat/completions shape on both, so the host decides.
    WEBARENA_JUDGE_API_KEY lets the judge live on a different Azure resource than the agent;
    Azure keys are per-resource, so a judge on another resource needs its own. When judge and
    agent share a resource it is unset and OPENAI_API_KEY covers both.
    """
    key = os.environ.get("WEBARENA_JUDGE_API_KEY") or os.environ["OPENAI_API_KEY"]
    if "azure.com" in base:
        return {"api-key": key, "Content-Type": "application/json"}
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _judge_call(message: str) -> str:
    """Official generate_from_openai_chat_completion parameters, over an OpenAI-compatible API."""
    import urllib.request

    base = (os.environ.get("WEBARENA_JUDGE_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1").rstrip("/")
    payload = {
        "model": JUDGE_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": message},
        ],
        "temperature": 0,
        "top_p": 1.0,
    }
    # The gpt-5.x family rejects max_tokens and wants max_completion_tokens; gpt-4o and the
    # OpenAI-compatible judges only understand the original name. Key off the model, not the
    # host: the judge may be gpt-4o on Azure while the model under test is gpt-5.4.
    payload["max_completion_tokens" if JUDGE_MODEL.startswith("gpt-5") else "max_tokens"] = 768
    body = json.dumps(payload).encode("utf-8")
    # Azure needs an api-version query on the deployment's chat/completions route; the
    # OpenAI-compatible path takes none. WEBARENA_JUDGE_API_VERSION overrides the default.
    url = f"{base}/chat/completions"
    if "azure.com" in base:
        url += "?api-version=" + os.environ.get(
            "WEBARENA_JUDGE_API_VERSION", "2025-01-01-preview")
    request = urllib.request.Request(
        url, data=body,
        headers=_judge_auth_headers(base),
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"].lower()


JUDGE_ATTEMPTS = 3


def _judged(message, read_verdict):
    """Official verdict parsing, asked again when the reply carries neither verdict.

    The official helper asserts the reply contains one of the two words and raises when it does
    not, which loses the whole task instead of the one call. At temperature 0 the reply is a
    fixed phrase, so one that parses as neither is a transport hiccup rather than a judgement,
    and asking again is not a second opinion. A reply that does parse is scored exactly as
    official does; one that never parses raises with its text, so the case stays visible rather
    than being silently resolved either way.
    """
    reply = None
    for _ in range(JUDGE_ATTEMPTS):
        reply = _judge_call(message)
        verdict = read_verdict(reply)
        if verdict is not None:
            return verdict
    raise ValueError(f"judge gave no verdict in {JUDGE_ATTEMPTS} attempts: {reply!r}")


def make_llm_helpers(model_config: str | Path | None):
    """Official llm_fuzzy_match / llm_ua_match, verbatim except for the judge model id."""

    def read_fuzzy(response):
        if "partially correct" in response or "incorrect" in response:
            return 0.0
        return 1.0 if "correct" in response else None

    def read_ua(response):
        if "different" in response:
            return 0.0
        return 1.0 if "same" in response else None

    def fuzzy(pred: str, reference: str, question: str) -> float:
        return _judged(_official_fuzzy_message(pred, reference, question), read_fuzzy)

    def unachievable(pred: str, reference: str, question: str) -> float:
        return _judged(_official_ua_message(pred, reference, question), read_ua)

    return fuzzy, unachievable


def load_official_evaluator(webarena_root: str | Path, model_config=None):
    root = Path(webarena_root).resolve()
    source = root / "evaluation_harness" / "evaluators.py"
    if not source.is_file():
        raise ValueError(f"official WebArena evaluator missing: {source}")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
    )
    found = revision.stdout.strip() if revision.returncode == 0 else "unknown"
    if found != OFFICIAL_COMMIT:
        raise ValueError(
            f"WebArena checkout must be pinned at {OFFICIAL_COMMIT}; found {found}"
        )
    sys.path.insert(0, str(root))
    _install_official_import_compatibility(*make_llm_helpers(model_config), root=root)
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
            if not urls:
                continue
            deployment_url = str(urls[0]).rstrip("/")
            parsed = urlsplit(deployment_url)
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
    if not isinstance(value, dict):
        return ["final state must be a JSON object"]
    errors = []
    if not isinstance(value.get("final_url"), str) or not value["final_url"].strip():
        errors.append("final_url must be a non-empty string")
    if not isinstance(value.get("html"), str) and not isinstance(value.get("html_path"), str):
        errors.append("html or html_path must be supplied")
    # document_status is recorded, not consumed: no official evaluator reads it, since they
    # score the answer, the URL and the DOM. Rejecting a run over it threw away three tasks
    # whose artifacts were otherwise complete -- one agent wrote document.readyState, one
    # wrote "ok", one wrote 1. A field nothing depends on must not be able to fail a task.
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
    *,
    task_id: int,
    final_state_path: str | Path,
    tasks_path: str | Path,
    deployment_config: str | Path,
    webarena_root: str | Path,
    model_config: str | Path | None = None,
    auth_state_path: str | Path | None = None,
) -> dict:
    state_path = Path(final_state_path)
    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    errors = validate_final_state(final_state)
    if errors:
        return {"score": None, "status": "invalid_final_state", "errors": errors}
    if "html" not in final_state:
        try:
            html_path = _resolve_run_artifact(state_path, final_state["html_path"], "saved DOM")
        except ValueError as error:
            return {"score": None, "status": "invalid_final_state", "errors": [str(error)]}
        final_state["html"] = html_path.read_text(encoding="utf-8")

    storage_state = Path(auth_state_path) if auth_state_path else None
    if final_state.get("storage_state_path"):
        try:
            storage_state = _resolve_run_artifact(
                state_path, final_state["storage_state_path"], "browser storage state"
            )
        except ValueError as error:
            return {"score": None, "status": "invalid_final_state", "errors": [str(error)]}

    task = load_task(tasks_path, task_id)
    if not task:
        return {"score": None, "status": "missing_task", "errors": [str(task_id)]}
    deployment = json.loads(Path(deployment_config).read_text(encoding="utf-8"))
    environments = deployment.get("environments")
    if not isinstance(environments, dict):
        return {
            "score": None,
            "status": "invalid_deployment_config",
            "errors": ["missing environments object"],
        }
    task = resolve_placeholders(task, environments)
    export_site_urls(environments)

    try:
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
                score = float(
                    evaluator_router(handle.name)(
                        trajectory=trajectory,
                        config_file=handle.name,
                        page=pseudo_page,
                        client=None,
                    )
                )
            finally:
                if browser is not None:
                    browser.close()
                if playwright is not None:
                    playwright.stop()
    except UnsupportedSavedStateError as error:
        return classify_saved_state_error(error, task_id)

    return {
        "score": score,
        "status": "scored_correct" if score == 1.0 else "scored_incorrect",
        "task_id": task_id,
        "task_source": "official_webarena",
        "eval_types": eval_types,
        "final_url": final_state["final_url"],
        "official_webarena_commit": OFFICIAL_COMMIT,
        "judge_model": JUDGE_MODEL,
        "helpers_source": "official" if _HELPER_LOAD_ERROR is None else "stub",
        "eval_python": sys.executable,
        "official_judge_model": OFFICIAL_JUDGE_MODEL,
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
    parser.add_argument("--auth-state",
                        help="storage_state for the evaluator's own navigation. program_html "
                             "targets whose url is not 'last' are fetched live, and on a site "
                             "behind login a logged-out fetch returns the sign-in page, so the "
                             "content check fails no matter what the agent did.")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    result = evaluate_saved_state(
        task_id=args.task_id,
        final_state_path=args.final_state,
        tasks_path=args.tasks,
        deployment_config=args.deployment_config,
        webarena_root=args.webarena_root,
        model_config=args.model_config,
        auth_state_path=args.auth_state,
    )
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if result.get("score") is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
