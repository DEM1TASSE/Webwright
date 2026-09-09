"""Minimal adapter: SkillWeaver `skillnet` package -> a Webwright prompt hint.

Why this exists
---------------
SkillWeaver ships one flat `<site>_kb_post_code.py` per site (438 bare
`async def f(page, ...)` functions across 5 sites) and consumes it by (a) asking an
LLM which functions look relevant to the task, then (b) inlining the WHOLE file into
the module it executes.  Webwright's agent writes standalone scripts instead, so the
faithful analogue of "what the package retrieved" is: run SkillWeaver's own retrieval
prompt, then hand the agent the SOURCE of the selected functions.

Deliberately NOT done here: no primitive catalog entry, no contract, no gate.  The
package is treated as an outside library we only surface to the agent.

Deviations from upstream SkillWeaver, on purpose:
  * upstream shows signature+docstring in the prompt and injects all 438 bodies into
    the exec module; there is no exec module here, so the retrieved functions' full
    source goes in the prompt instead;
  * upstream relies on a monkeypatch that resolves relative `page.goto("/x")` against
    the current origin.  Webwright's context has no base_url, so the hint says so.
"""
from __future__ import annotations

import ast
import hashlib
import subprocess


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _library_provenance(library_root):
    """Commit plus dirty flag plus per-file hashes: a commit alone says nothing about a working
    tree with uncommitted edits, and the skillnet package has been patched locally before."""
    if not library_root:
        return None
    root = Path(library_root)
    def git(*args):
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
        return proc.stdout.strip() if proc.returncode == 0 else None
    files = sorted(str(f.relative_to(root)) for f in root.rglob("*_code.py"))
    return {"root": str(root), "git_commit": git("rev-parse", "HEAD"),
            "dirty": bool(git("status", "--porcelain") or ""),
            "files": {f: sha256_file(root / f) for f in files}}
import json
from pathlib import Path
from urllib.parse import urlsplit

# WebArena site name -> skillnet directory.  "cms" is SkillWeaver's name for shopping_admin.
SITE_DIRS = {
    "shopping": "shopping",
    "shopping_admin": "cms",
    "gitlab": "gitlab",
    "map": "map",
    "reddit": "reddit",
}

# SkillWeaver's own retrieval prompt (skillweaver/templates/predict_relevant_functions.md),
# copied verbatim except for the JSON response instruction its LM wrapper supplied via schema.
RETRIEVE_SYSTEM = (
    "You are provided a list of Python functions representing action shortcuts that can be "
    "taken on a website\n(in addition to the basic actions like click, type, hover, "
    "select_option, etc.)\nYou identify which functions could be useful for completing a given "
    "task.\nYou do this by breaking the task down into steps and seeing if any functions may be "
    "useful."
)
RETRIEVE_USER = """You are given the following list of functions/shortcuts:
<functions>
{function_space}
</functions>

Your task is {repr_task}.

For each of the listed functions, please determine (explicitly) whether they are useful for the task.
Then, provide a list of the function names that may be useful to the agent.

Reply with JSON only: {{"step_by_step_reasoning": "...", "relevant_function_names": [{{"name": "..."}}]}}
"""


def load_functions(skillnet_root, site):
    """Parse one site's `_code.py` into {name, signature, docstring, source}."""
    d = SITE_DIRS.get(site)
    if not d:
        return []
    matches = sorted(Path(skillnet_root, d).glob("*_code.py"))
    if not matches:
        return []
    src = matches[0].read_text(encoding="utf-8")
    lines = src.split("\n")
    out = []
    for node in ast.parse(src).body:
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) or node.name == "main":
            continue
        body = "\n".join(lines[node.lineno - 1: node.end_lineno])
        out.append({
            "name": node.name,
            "signature": body[: body.index(")") + 1] if ")" in body else body.split("\n")[0],
            "docstring": ast.get_docstring(node) or "",
            "source": body,
            "file": str(matches[0]),
        })
    return out


def _marker(fn) -> str:
    """Provenance comment matching webwright's `extract_primitive_usage` marker regex.

    Without it `code_incorporated_primitives` is structurally always empty for these arms, so
    copied code leaves no machine-checkable trace.  Nothing in the prompt asks the agent to
    keep the comment -- it is a bonus signal on top of the name-based check, not a nudge.
    """
    digest = hashlib.sha256(fn["source"].encode("utf-8")).hexdigest()
    return f"# primitive-source: {fn['name']} sha256:{digest}"


def prepared_source(fn) -> str:
    """The package's source, verbatim.

    No provenance comment: webwright puts its marker in a metadata block separate from the code,
    while one glued above `async def` rides along with any copy -- the two are not equally costly
    to preserve, so the marker channel could never be compared across arms. Reuse is measured the
    same way on both sides instead, by looking for the function's definition and a call to it in
    final_script.py, which needs no cooperation from the agent.
    """
    return fn["source"]


def _pretty(fn):
    """SkillWeaver's format_function_as_pretty_string: signature + unindented docstring."""
    doc = fn["docstring"].strip().split("\n")
    if len(doc) > 1:
        indent = len(doc[1]) - len(doc[1].lstrip())
        doc = [doc[0]] + [line[indent:] for line in doc[1:]]
    return f"# Skill: {fn['signature']}\n" + "\n".join(doc) + "\n\n"


def retrieve(task, functions, llm_json_fn=None, max_functions=0):
    """SkillWeaver's retrieval step: the LM picks names out of the whole function space.

    `max_functions=0` means no cap, which is what upstream does -- it hands the agent every
    name the LM returned, routinely 20+.  The pilot capped this at 5 to match the primitive
    arm's `max_primitives=5`, but that made the arm measure a truncated library rather than
    SkillWeaver's own retrieval; the point of this arm is the package as its authors ship it,
    noise included.
    """
    if not functions:
        return [], "<no skills available>"
    if llm_json_fn is None:
        from webwright.skill_factory.llm import llm_json as llm_json_fn
    resp = llm_json_fn(
        RETRIEVE_SYSTEM,
        RETRIEVE_USER.format(
            function_space="".join(_pretty(f) for f in functions), repr_task=repr(task),
        ),
    )
    by_name = {f["name"]: f for f in functions}
    picked, seen = [], set()
    for item in resp.get("relevant_function_names") or []:
        name = item.get("name") if isinstance(item, dict) else item
        if not isinstance(name, str):
            continue
        name = name.split("(")[0].strip()
        # same guard as upstream: a hallucinated name is dropped, not recommended
        if name in by_name and name not in seen:
            seen.add(name)
            picked.append(by_name[name])
    kept = picked[:max_functions] if max_functions else picked
    return kept, picked, str(resp.get("step_by_step_reasoning") or "")


# --- Wording lifted verbatim from SkillWeaver -------------------------------------------
# skillweaver/templates/__init__.py:37 supplies `function_usage_instructions` in one of two
# forms, and skillweaver/templates/codegen.md carries a standing mandate.  Both arms below
# reuse those strings as-is rather than inventing phrasing, so the only thing that differs
# between the arms is what upstream itself varies: whether the library is callable.
UPSTREAM_MANDATE = (
    "You love to take advantage of functions in the knowledge_base whenever possible. You use "
    "them via Python function calls.\nIt is required to use the knowledge base function "
    "corresponding to an action if it exists."
)
UPSTREAM_REFERENCE_ONLY = (
    "You have practiced the below functions. Note that they are only available for reference. "
    "You cannot 'call' them, but you should refer to them when generating code."
)
UPSTREAM_CALLABLE = (
    "You also have this library of Python functions available to you. Think carefully about "
    "whether you think these can be used in your code. If you conclude that you can use a "
    "function, then simply call it. These functions are all available as global variables."
)


REPORTING_PARITY = (
    "Write primitive_usage.json with used ids and a coverage_assessment."
)
REPORTING_PARITY_IMPORT = (
    "Write primitive_usage.json with the ids of the functions you imported and actually called, "
    "plus a coverage_assessment."
)


def render_hint(picked, origin):
    """`package` arm: source in the prompt, for reference.  SkillWeaver's `as_reference_only`.

    Contents are upstream's and nothing else: codegen.md's standing mandate, the
    reference-only form of templates/__init__.py:37, and the <functions> block it wraps.
    The one addition is the note about relative goto, which upstream does not need because
    its own runtime patches Page.goto; here the agent is copying source into a script that
    has no such patch, so without the note it would be copying code that cannot run.
    """
    if not picked:
        return ""
    return "\n\n".join([
        UPSTREAM_MANDATE,
        UPSTREAM_REFERENCE_ONLY,
        # Not upstream: lifted from webwright's render_audited_primitive_hint so both arms are
        # measured by the same instrument. These ask only for provenance, not for how to solve
        # the task or whether to use a skill, so the substantive instruction stays upstream's.
        REPORTING_PARITY,
        f"Note: `page.goto(\"/path\")` inside these functions is relative to the site root "
        f"({origin}); this runtime does not resolve that for you.",
        "<functions>\n" + "\n\n".join(prepared_source(f) for f in picked) + "\n</functions>",
    ]).replace("\n\n\n", "\n\n")


# Verbatim port of SkillWeaver's `_apply_relative_goto` (skillweaver/environment/patches.py:46).
# Upstream applies it process-wide before the agent runs, which is why every skillnet function
# can say `page.goto("/admin/...")`.  Shipping it inside the module keeps the library source
# byte-identical to upstream instead of rewriting 338 of its 352 goto calls.
GOTO_PATCH = '''from playwright.async_api import Page as _Page
from urllib.parse import urlparse as _urlparse

_SKILLNET_ORIGIN = {origin!r}
_original_goto = _Page.goto


async def _relative_goto(self, url, **kwargs):
    if url.startswith("/"):
        parsed = _urlparse(self.url)
        # Upstream resolves against the current page's origin; fall back to the run's origin
        # when there is no current page yet (upstream never starts from about:blank).
        base = f"{{parsed.scheme}}://{{parsed.netloc}}" if parsed.netloc else _SKILLNET_ORIGIN
        url = base + url
    return await _original_goto(self, url, **kwargs)


_Page.goto = _relative_goto
'''

MODULE_DOC = '''"""Retrieved SkillWeaver `skillnet` helpers, importable by the generated script.

Written by skillnet_hint.py for one task.  Function bodies are byte-identical to the
published package; the only additions are SkillWeaver's own relative-goto patch and a
provenance comment per function.  UNVERIFIED -- untested against this live site.
"""
import asyncio  # noqa: F401
import json  # noqa: F401
import re  # noqa: F401

'''


def write_skill_module(picked, origin, module_path, *, manifest_path=None, library_root=None):
    """Materialize the retrieved functions as an importable module.  Returns its path.

    When `manifest_path` is given, also record what was written: the module's hash, each
    function's source hash, and where the library came from. Replay verifies the module
    against this before importing it, and the run record carries it for provenance.
    """
    module_path = Path(module_path)
    module_path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n\n".join(prepared_source(f) for f in picked)
    module_path.write_text(
        MODULE_DOC + GOTO_PATCH.format(origin=origin) + "\n\n" + body + "\n", encoding="utf-8")
    if manifest_path is not None:
        manifest = {
            "module_file": module_path.name,
            "module_sha256": sha256_file(module_path),
            "functions": [{"name": f["name"], "sha256": sha256_text(f["source"])} for f in picked],
            "library": _library_provenance(library_root),
        }
        Path(manifest_path).write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    return module_path


def render_import_hint(picked, origin, module_path=None, *, module_name=None):
    """`package_import` arm: the helpers are callable.  SkillWeaver's default mode.

    Upstream's prompt is `function_usage_instructions` followed by the <functions> block,
    with codegen.md carrying the mandate; that is all this reproduces. The sole addition is
    the import line: upstream says "available as global variables" because its agent executes
    inside a module that already holds the library, while webwright's agent writes a
    standalone script, so without naming the import there is no way to reach them.
    """
    if not picked:
        return ""
    names = ", ".join(f["name"] for f in picked)
    return "\n\n".join([
        UPSTREAM_MANDATE,
        UPSTREAM_CALLABLE,
        # Same parity as the paste arm, minus the source comment: an imported function is never
        # copied, so there is no copy to leave a marker in.
        REPORTING_PARITY_IMPORT,
        "In this runtime they are not globals but a module on disk inside your workspace; make "
        "them available with:\n"
        "```python\n"
        "import os, sys; sys.path.insert(0, os.environ[\"WORKSPACE_DIR\"])\n"
        f"from {module_name or Path(module_path).stem} import {names}\n"
        "```",
        "<functions>\n" + "".join(_pretty(f) for f in picked) + "</functions>",
    ]).replace("\n\n\n", "\n\n")


def prepare_package_hint(task, site, skillnet_root, url, record_path=None, max_functions=0,
                         delivery="hint", module_path=None, manifest_path=None,
                         module_name=None):
    """Retrieve from the package and render the hint.  Fail-open: never block a solve.

    `delivery` selects how the selected functions reach the agent:
      "hint"   -- their source goes in the prompt for the agent to copy (original arm);
      "import" -- their source is written to `module_path` and the prompt tells the agent to
                  import it.  This is the analogue of SkillWeaver's own delivery, where the
                  library is already in scope at execution time.
    """
    origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    written_module = None
    try:
        functions = load_functions(skillnet_root, site)
        picked, all_picked, reasoning = retrieve(task, functions, max_functions=max_functions)
        if delivery == "import" and picked:
            if module_path is None:
                raise ValueError("delivery='import' requires module_path")
            written_module = write_skill_module(
                picked, origin, module_path, manifest_path=manifest_path,
                library_root=skillnet_root)
            hint = render_import_hint(picked, origin, written_module,
                                      module_name=module_name or Path(written_module).stem)
        else:
            hint = render_hint(picked, origin)
        error = ""
    except Exception as exc:                      # retrieval must never break the run
        functions, picked, all_picked, reasoning = [], [], [], ""
        hint, error = "", f"{type(exc).__name__}: {exc}"
    rec = {
        "task": task,
        "site": site,
        "skillnet_root": str(skillnet_root),
        "library_size": len(functions),
        "module": str(written_module) if written_module else None,
        "manifest": str(manifest_path) if (written_module and manifest_path) else None,
        "delivery": delivery,
        "skill_module": str(written_module) if written_module else None,
        "decision": "adapt" if picked else "skip",
        "skill_ids": [f["name"] for f in picked],
        "skill_ids_uncapped": [f["name"] for f in all_picked],
        "max_functions": max_functions,
        "reason": reasoning or error,
        "error": error,
        "hint": hint,
    }
    if record_path:
        Path(record_path).parent.mkdir(parents=True, exist_ok=True)
        Path(record_path).write_text(
            json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rec


if __name__ == "__main__":                        # dry run: python skillnet_hint.py <site> <task>
    import sys
    fns = load_functions(sys.argv[3] if len(sys.argv) > 3 else "skillnet", sys.argv[1])
    print(f"library: {len(fns)} functions")
    picked, all_picked, reasoning = retrieve(sys.argv[2], fns)
    print("picked:", [f["name"] for f in picked], "of", len(all_picked), "returned")
    print("reasoning:", reasoning[:500])
