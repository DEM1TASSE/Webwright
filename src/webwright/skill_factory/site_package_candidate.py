"""Proposal-only generation for website-scoped primitive packages.

The generated package is an immutable review artifact.  This module never writes to a
``PrimitiveCatalog`` and never repairs model output; promotion is a separate, human-approved
operation that is intentionally outside this MVP pipeline.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_FORBIDDEN_OUTPUT_TERMS = {
    "locator", "elementhandle", "raw_dom", "raw_html", "html_blob", "dom_blob",
    "untyped_text", "page_text",
}
_GENERIC_CAPABILITY_TERMS = {
    "generic regex", "arbitrary text", "generic http", "browser setup", "format answer",
}


_GENERATION_SYS = r"""You design a CANDIDATE primitive package for one WebArena website from
gold-admitted standalone workflow scripts. Return exactly one JSON object; do not add prose:
{
  "site": "<site>",
  "class_name": "<PascalCaseSite>",
  "package_code": "<one complete Python file defining exactly this class>",
  "methods": [{
    "primitive_id": "<site>/<feature>/<method>",
    "feature": "<short snake_case retrieval label>",
    "method": "<public method name>",
    "capability": "<site-specific operation>",
    "owns": ["<site-specific acquisition/parsing responsibility>"],
    "does_not_own": ["<task-level responsibility left to workflows>"],
    "input_contract": {"<name>": "<type and meaning>"},
    "output_contract": {"type": "<typed value>", "fields": {}},
    "requires": ["<environment-state token>"],
    "provides": ["<environment-state or typed-data token>"],
    "source_evidence": [{
      "workflow_id": "<exact supplied id>",
      "template_id": "<exact supplied template_id>",
      "code_quote": "<contiguous verbatim code substring>",
      "explanation": "<how the quote supports this method>"
    }]
  }]
}

BOUNDARY (mandatory):
- A public method is a reusable website operation. It owns selectors/endpoints, authentication
  mechanics, pagination mechanics, and parsing of stable site-specific output conventions.
- It returns typed objective facts. For example, a map duration displayed as H:MM must be parsed
  by the site method into seconds; never return a Locator, ElementHandle, raw DOM/HTML, arbitrary
  page text, or an untyped blob for a workflow to reinterpret.
- The workflow owns the task intent: requested-category filtering, subjective classification,
  aggregation, ranking/comparison, stopping policy specific to the question, and final answer
  formatting. Do not put these in public methods.
- Do not create generic regex/text/HTTP/browser helpers as public methods. Private helpers whose
  names start with '_' are allowed inside the class.
- Every public method must be independently useful to at least one future task, and every claimed
  behavior must be directly supported by an exact source quote. Prefer NO method over speculation.
- Keep one class and one file. Methods may share private helpers, but public methods must not call
  other public methods. This package is synthesis material: workflows will vendor/adapt selected
  code and will not import it at runtime.
- requires/provides describe environment state, not Python imports or code dependencies.

Do not include source-task answers, task-specific constants, evaluator logic, workflows, or a
main program. Do not repair or invent missing source behavior."""


@dataclass
class CandidateValidation:
    accepted: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def expected_class_name(site: str) -> str:
    special = {"gitlab": "GitLab", "shopping_admin": "ShoppingAdmin"}
    stem = special.get(site) or "".join(part.capitalize() for part in site.split("_"))
    return stem + "Site"


def generate_site_package_candidate(
    site: str,
    workflows: list[dict],
    *,
    prior_candidate: dict | None = None,
    validation_feedback: list[str] | None = None,
    llm_fn: Callable[[str, str], dict] | None = None,
) -> dict:
    """Generate one raw candidate. No catalog mutation or output repair occurs here."""
    if llm_fn is None:
        from .llm import llm_json

        llm_fn = lambda system, user: llm_json(system, user, max_tokens=24000)
    payload = {
        "site": site,
        "required_class_name": expected_class_name(site),
        "workflows": workflows,
    }
    if validation_feedback:
        payload["previous_rejected_candidate"] = prior_candidate
        payload["validation_feedback"] = validation_feedback
        payload["retry_instruction"] = (
            "Regenerate the entire JSON candidate and package_code. Correct every validation "
            "error using only supplied source evidence. Do not merely patch or omit metadata, "
            "and do not claim behavior unsupported by an exact source quote."
        )
    raw = llm_fn(_GENERATION_SYS, json.dumps(payload, ensure_ascii=False)) or {}
    if not isinstance(raw, dict):
        return {}
    return raw


def _normalized(text: object) -> str:
    return " ".join(str(text or "").split())


def _public_methods(class_node: ast.ClassDef) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }


def validate_site_package_candidate(
    candidate: dict, *, site: str, workflows: list[dict]
) -> CandidateValidation:
    """Validate structure, explicit boundaries, and verbatim provenance without fixing output."""
    errors: list[str] = []
    warnings: list[str] = []
    class_name = expected_class_name(site)
    if candidate.get("site") != site:
        errors.append(f"site must be {site!r}")
    if candidate.get("class_name") != class_name:
        errors.append(f"class_name must be {class_name!r}")
    code = candidate.get("package_code")
    if not isinstance(code, str) or not code.strip():
        return CandidateValidation(False, [*errors, "package_code must be non-empty"])
    try:
        tree = ast.parse(code, filename=f"{site}/package.py")
        compile(tree, f"{site}/package.py", "exec")
    except SyntaxError as exc:
        return CandidateValidation(False, [*errors, f"package_code does not compile: {exc}"])

    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    expected = [node for node in classes if node.name == class_name]
    if len(classes) != 1 or len(expected) != 1:
        errors.append(f"package_code must define exactly one class named {class_name}")
        class_node = expected[0] if expected else None
    else:
        class_node = expected[0]
    public = _public_methods(class_node) if class_node else {}
    methods = candidate.get("methods")
    if not isinstance(methods, list):
        errors.append("methods must be a list")
        methods = []
    indexed_names: list[str] = []
    known = {str(row.get("id")): row for row in workflows}

    for i, method in enumerate(methods):
        label = f"methods[{i}]"
        if not isinstance(method, dict):
            errors.append(f"{label} must be an object")
            continue
        name = method.get("method")
        feature = method.get("feature")
        pid = method.get("primitive_id")
        if not isinstance(name, str) or not _SAFE_NAME.fullmatch(name):
            errors.append(f"{label}.method must be safe snake_case")
            continue
        indexed_names.append(name)
        if not isinstance(feature, str) or not _SAFE_NAME.fullmatch(feature):
            errors.append(f"{label}.feature must be safe snake_case")
        if pid != f"{site}/{feature}/{name}":
            errors.append(f"{label}.primitive_id must be <site>/<feature>/<method>")
        for field_name in ("capability", "owns", "does_not_own", "input_contract",
                           "output_contract", "source_evidence"):
            if not method.get(field_name):
                errors.append(f"{label}.{field_name} must be non-empty")
        output_text = _normalized(method.get("output_contract")).lower()
        forbidden = sorted(term for term in _FORBIDDEN_OUTPUT_TERMS if term in output_text)
        if forbidden:
            errors.append(f"{label} exposes untyped site output: {', '.join(forbidden)}")
        boundary_text = _normalized({
            "capability": method.get("capability"), "owns": method.get("owns")
        }).lower()
        generic = sorted(term for term in _GENERIC_CAPABILITY_TERMS if term in boundary_text)
        if generic:
            warnings.append(f"{label} may be generic rather than site-specific: {', '.join(generic)}")

        evidence = method.get("source_evidence") or []
        if not isinstance(evidence, list):
            errors.append(f"{label}.source_evidence must be a list")
            continue
        for j, row in enumerate(evidence):
            elabel = f"{label}.source_evidence[{j}]"
            if not isinstance(row, dict):
                errors.append(f"{elabel} must be an object")
                continue
            workflow = known.get(str(row.get("workflow_id")))
            if workflow is None:
                errors.append(f"{elabel} cites an unknown workflow")
                continue
            if str(row.get("template_id")) != str(workflow.get("template_id")):
                errors.append(f"{elabel} template_id does not match its workflow")
            quote = _normalized(row.get("code_quote"))
            if len(quote) < 80:
                errors.append(f"{elabel}.code_quote is too short")
            elif quote not in _normalized(workflow.get("code")):
                errors.append(f"{elabel}.code_quote is not a verbatim source substring")
            if len(str(row.get("explanation") or "").strip()) < 20:
                errors.append(f"{elabel}.explanation is too short")

    if len(indexed_names) != len(set(indexed_names)):
        errors.append("method names must be unique")
    if set(indexed_names) != set(public):
        errors.append(
            "index public methods do not match package public methods: "
            f"index={sorted(set(indexed_names))}, package={sorted(public)}"
        )
    if not methods:
        warnings.append("candidate contains no reusable primitive methods")

    # Public-to-public calls create hidden primitive dependency edges. Private helpers are fine.
    for name, node in public.items():
        calls = {
            child.func.attr
            for child in ast.walk(node)
            if isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr in public
        }
        calls.discard(name)
        if calls:
            errors.append(f"public method {name} calls public method(s): {', '.join(sorted(calls))}")
    return CandidateValidation(not errors, errors, warnings)


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_candidate_bundle(
    root: str | Path,
    candidate: dict,
    validation: CandidateValidation,
    *,
    site: str,
    workflows: list[dict],
) -> Path:
    """Write review artifacts only. The exact generated package text is preserved."""
    target = Path(root) / site
    target.mkdir(parents=True, exist_ok=True)
    raw_text = json.dumps(candidate, ensure_ascii=False, indent=2) + "\n"
    code = candidate.get("package_code") if isinstance(candidate.get("package_code"), str) else ""
    index = {
        "schema_version": 1,
        "status": "candidate",
        "approved": False,
        "site": site,
        "class_name": candidate.get("class_name"),
        "package_sha256": _sha256(code),
        "methods": candidate.get("methods") if isinstance(candidate.get("methods"), list) else [],
        "source_workflows": [
            {key: row.get(key) for key in ("id", "task_id", "template_id")}
            for row in workflows
        ],
    }
    validation_json = {
        "accepted_by_static_checks": validation.accepted,
        "errors": validation.errors,
        "warnings": validation.warnings,
        "note": "Static acceptance is not promotion; human approval is required.",
    }
    (target / "raw_generation.json").write_text(raw_text, encoding="utf-8")
    (target / "package.py").write_text(code, encoding="utf-8")
    (target / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (target / "validation.json").write_text(
        json.dumps(validation_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        f"# {site} primitive package candidate", "",
        f"- Status: **candidate — not promoted**",
        f"- Static checks: **{'PASS' if validation.accepted else 'FAIL'}**",
        f"- Package hash: `{index['package_sha256']}`", "",
        "## Boundary review", "",
    ]
    for method in index["methods"]:
        lines.extend([
            f"### `{method.get('primitive_id', '<missing>')}`", "",
            f"Capability: {method.get('capability', '')}", "",
            f"Owns: {', '.join(method.get('owns') or [])}", "",
            f"Does not own: {', '.join(method.get('does_not_own') or [])}", "",
            f"Input: `{json.dumps(method.get('input_contract'), ensure_ascii=False)}`", "",
            f"Output: `{json.dumps(method.get('output_contract'), ensure_ascii=False)}`", "",
            f"Evidence: {len(method.get('source_evidence') or [])} workflow(s)", "",
        ])
    lines.extend(["## Validation", ""])
    lines.extend([f"- ERROR: {x}" for x in validation.errors] or ["- No static errors."])
    lines.extend([f"- WARNING: {x}" for x in validation.warnings])
    lines.extend(["", "Approval must happen outside this generator; editing package.py invalidates its hash.", ""])
    (target / "review.md").write_text("\n".join(lines), encoding="utf-8")
    return target
