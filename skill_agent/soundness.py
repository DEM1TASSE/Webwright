"""Will this method actually run, or does it only parse?

The shared validators check contracts, evidence, and boundary. They do not check that the code
resolves its own names, and neither does the judge — it is answering "does the evidence support
this site operation", not "does this execute". A generated GitLab batch passed every one of
those checks with six of seven methods referencing ``self.base_url``, which nothing ever
assigns. Each would have raised AttributeError on the first call.

Two failures are detectable statically and are pure crashes, not style:

* an attribute read off ``self`` that is neither a method of the class nor assigned in it —
  the primitive invented constructor state that the renderer never creates (``__init__``
  stores ``page``, and only ``page``);
* a bare name read that is not a parameter, local, import, comprehension target, module-level
  name, or builtin.

Both are checked against the composed method code, before anything is committed.

A third check is about portability rather than crashing: a literal deployment address baked
into a method. The rendered class holds only ``page``, so the site's address has to arrive from
outside — and both pipelines have shipped primitives that hard-code it instead, which quietly
ties a library to one deployment.
"""
from __future__ import annotations

import ast
import builtins
import re

_BUILTINS = frozenset(dir(builtins))
# The renderer generates `def __init__(self, page): self.page = page` and nothing else.
_RENDERED_ATTRS = frozenset({"page"})


def _bound_names(node: ast.AST) -> set[str]:
    """Names a function body binds: assignments, imports, loops, with/except, nested defs."""
    bound: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
            bound.add(child.id)
        elif isinstance(child, (ast.Import, ast.ImportFrom)):
            for alias in child.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(child.name)
        elif isinstance(child, ast.ExceptHandler) and child.name:
            bound.add(child.name)
        elif isinstance(child, ast.arg):
            bound.add(child.arg)
        elif isinstance(child, ast.alias):
            bound.add((child.asname or child.name).split(".")[0])
    return bound


def _self_attrs_assigned(node: ast.AST) -> set[str]:
    return {n.attr for n in ast.walk(node)
            if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
            and isinstance(n.value, ast.Name) and n.value.id == "self"}


def check_method_code(code: str, *, where: str, known_methods: frozenset[str] = frozenset(),
                      module_names: frozenset[str] = frozenset()) -> list[str]:
    """Report unresolvable names in one primitive's method code.

    ``code`` may hold several defs (one public method plus private helpers). Names assigned
    anywhere in it, and attributes assigned onto ``self`` anywhere in it, count as available.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"{where}: does not parse: {exc}"]

    available_attrs = _RENDERED_ATTRS | _self_attrs_assigned(tree) | set(known_methods)
    available_attrs |= {n.name for n in tree.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    module_bound = _bound_names(tree) | set(module_names) | _BUILTINS

    errors: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        scope = _bound_names(node) | module_bound
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Attribute) and isinstance(inner.ctx, ast.Load)
                    and isinstance(inner.value, ast.Name) and inner.value.id == "self"
                    and inner.attr not in available_attrs):
                errors.append(
                    f"{where}: {node.name}() reads self.{inner.attr}, which nothing assigns. "
                    f"The rendered class only stores `page`. Derive what you need inside the "
                    f"method (for example a base URL from `self.page.url`) or take it as a "
                    f"parameter — never invent constructor state.")
            elif (isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Load)
                    and inner.id not in scope and inner.id != "self"):
                errors.append(f"{where}: {node.name}() reads undefined name `{inner.id}`; "
                              f"it would raise NameError on the first call.")
    return sorted(set(errors))


def check_primitives(primitives: list[dict]) -> list[str]:
    """Check every method body in a list of primitive replacement objects."""
    known = frozenset(str(p.get("method")) for p in primitives
                      if isinstance(p, dict) and p.get("method"))
    errors: list[str] = []
    for primitive in primitives:
        if not isinstance(primitive, dict):
            continue
        code = primitive.get("method_code")
        if isinstance(code, str) and code:
            errors.extend(check_method_code(
                code, known_methods=known,
                where=str(primitive.get("primitive_id") or primitive.get("method") or "?")))
    return errors


def check_package(path) -> list[str]:
    """Check a rendered package.py, as a last line of defence after consolidation."""
    from pathlib import Path

    source = Path(path).read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"{path}: does not parse: {exc}"]
    # Module scope includes the feature classes themselves: the root site class constructs
    # them, and a class defined later in the file is still resolvable at call time.
    module_names = frozenset(
        {n.name for n in tree.body
         if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}
        | {n for stmt in tree.body if not isinstance(stmt, ast.ClassDef)
           for n in _bound_names(stmt)})
    errors: list[str] = []
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        methods = frozenset(m.name for m in cls.body
                            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)))
        assigned = _self_attrs_assigned(cls)
        for method in cls.body:
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            scope = _bound_names(method) | module_names | _BUILTINS | {cls.name}
            for inner in ast.walk(method):
                if (isinstance(inner, ast.Attribute) and isinstance(inner.ctx, ast.Load)
                        and isinstance(inner.value, ast.Name) and inner.value.id == "self"
                        and inner.attr not in (methods | assigned | _RENDERED_ATTRS)):
                    errors.append(f"{cls.name}.{method.name}() reads self.{inner.attr}, "
                                  f"which nothing assigns")
                elif (isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Load)
                        and inner.id not in scope and inner.id != "self"):
                    errors.append(f"{cls.name}.{method.name}() reads undefined name "
                                  f"`{inner.id}`")
    return sorted(set(errors))


_ABSOLUTE_URL = re.compile(r"(?P<scheme>https?)://(?P<host>[^/\s\"'{}]+)")


def hardcoded_hosts(code: str, *, where: str) -> list[str]:
    """Report deployment addresses baked into method code.

    The rendered class holds only `page`, so a site's base address has to arrive from outside:
    derived from `self.page.url` for a method that navigates, or passed as a parameter for one
    that only calls an API. A literal host is the third option, and it is the wrong one — the
    address is environment state, so a primitive that bakes it in stops working the moment the
    library is pointed at another deployment.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    literals: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            literals.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            literals.append("".join(
                part.value if isinstance(part, ast.Constant) and isinstance(part.value, str)
                else "{}" for part in node.values))
    found = {match.group("host") for literal in literals
             for match in _ABSOLUTE_URL.finditer(literal)}
    return [f"{where}: hard-codes the deployment address `{host}`. The site address is "
            f"environment state: derive it from `self.page.url` when the method navigates, or "
            f"take it as a parameter when it only calls an API." for host in sorted(found)]


def check_hardcoded_hosts(primitives: list[dict]) -> list[str]:
    errors: list[str] = []
    for primitive in primitives:
        if not isinstance(primitive, dict):
            continue
        code = primitive.get("method_code")
        if isinstance(code, str) and code:
            errors.extend(hardcoded_hosts(
                code, where=str(primitive.get("primitive_id") or primitive.get("method") or "?")))
    return errors


def _stem(token: str) -> str:
    """Crude singular form: enough to match `commits` against `commit` in a source."""
    for suffix in ("ies", "es", "s"):
        if len(token) > 3 and token.endswith(suffix):
            return token[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return token


def ungrounded_features(primitives: list[dict], sources: str) -> list[str]:
    """Report feature names that do not appear in the site's own source workflows.

    A feature is meant to name something the website has. The generic examples once given in
    the rules included `reviews`, and a GitLab consolidation duly filed its issue primitives
    under a `reviews` feature — a word that appears zero times in GitLab's seven sources, while
    `issue` appears nineteen. Grounding the name in the sources catches exactly that.
    """
    haystack = sources.lower()
    errors = []
    for feature in sorted({str(p.get("feature")) for p in primitives if p.get("feature")}):
        tokens = feature.split("_")
        # One grounded token is enough: a compound like `catalog_search` is fine when the site
        # says "search", and requiring every token would reject reasonable qualifiers.
        if not any(_stem(token) in haystack or token in haystack for token in tokens):
            errors.append(
                f"feature `{feature}`: no part of this name appears anywhere in the site's "
                f"source workflows. Name a feature with the site's own vocabulary — the words "
                f"it uses in its URLs, headings and controls — not a generic category.")
    return errors


def undeclared_imports(code: str, *, where: str, allowed: frozenset[str]) -> list[str]:
    """Report imports of modules that are neither stdlib nor a declared dependency.

    A generated method imported `requests`, which this project does not depend on and does not
    have installed: ModuleNotFoundError on the first call, invisible to every other check,
    while a sibling method did the same job with urllib.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return [f"{where}: imports `{module}`, which is not in the standard library and not a "
            f"dependency of this project. It raises ModuleNotFoundError on the first call — "
            f"use the standard library (urllib for HTTP) or the browser page instead."
            for module in sorted(modules - allowed)]


def project_modules(pyproject: "Path | None" = None) -> frozenset[str]:
    """Stdlib plus whatever the project declares as a dependency."""
    import re as _re
    import sys
    from pathlib import Path

    allowed = set(getattr(sys, "stdlib_module_names", ())) | set(_BUILTINS)
    path = Path(pyproject) if pyproject else Path(__file__).resolve().parent.parent / "pyproject.toml"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            match = _re.match(r"\s*[\"']([A-Za-z0-9_.\-]+)", line)
            if match:
                allowed.add(match.group(1).replace("-", "_").split(".")[0])
    return frozenset(allowed)


def check_imports(primitives: list[dict], *, allowed: frozenset[str] | None = None) -> list[str]:
    allowed = allowed if allowed is not None else project_modules()
    errors: list[str] = []
    for primitive in primitives:
        if not isinstance(primitive, dict):
            continue
        code = primitive.get("method_code")
        if isinstance(code, str) and code:
            errors.extend(undeclared_imports(
                code, allowed=allowed,
                where=str(primitive.get("primitive_id") or primitive.get("method") or "?")))
    return errors
