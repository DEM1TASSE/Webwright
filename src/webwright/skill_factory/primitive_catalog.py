"""Site-scoped primitive catalog used as synthesis material for new workflows.

MVP invariants:
* workflows never import this catalog at runtime; retrieved code is copied/adapted into a
  standalone workflow;
* every active primitive snippet is self-contained with respect to the catalog: it may use
  imports and private helpers in its own file, but may not call another catalog primitive;
* one active implementation exists per primitive id. Git/content hashes provide provenance,
  not runtime version resolution.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path


_SAFE_ID = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass
class Primitive:
    primitive_id: str
    site: str
    capability: str
    entrypoint: str
    code: str
    signature: dict = field(default_factory=dict)
    requires: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)
    source_templates: list[int | str] = field(default_factory=list)
    source_workflows: list[str] = field(default_factory=list)
    source_evidence: list[dict] = field(default_factory=list)
    evidence_verified: bool | None = None
    evidence_verification_reason: str = ""
    grade: str = "single_source"
    supported_patterns: list[str] = field(default_factory=list)
    status: str = "active"
    content_hash: str = ""

    def __post_init__(self) -> None:
        self.content_hash = _content_hash(self.code)

    @property
    def name(self) -> str:
        return self.primitive_id.split("/", 1)[-1]


@dataclass
class SitePrimitiveClass:
    """Object-oriented view of one site's primitive package.

    Methods remain self-contained vendorable snippets. The class is the management and retrieval
    boundary, not a runtime base class that generated workflows must import.
    """

    site: str
    methods: list[Primitive] = field(default_factory=list)

    def method_metadata(self) -> list[dict]:
        return [{
            "primitive_id": method.primitive_id,
            "method_name": method.name,
            "capability": method.capability,
            "signature": method.signature,
            "requires": method.requires,
            "provides": method.provides,
            "grade": method.grade,
            "evidence_count": len(method.source_workflows),
            "supported_patterns": method.supported_patterns,
        } for method in self.methods]

    def get_method(self, primitive_id: str) -> Primitive | None:
        return next(
            (method for method in self.methods if method.primitive_id == primitive_id),
            None,
        )


def _content_hash(code: str) -> str:
    return "sha256:" + hashlib.sha256(code.encode("utf-8")).hexdigest()


def site_class_name(site: str) -> str:
    names = {"gitlab": "GitLab", "map": "Map", "shopping": "Shopping"}
    stem = "".join(names.get(part, part.capitalize()) for part in site.split("_"))
    return stem + "Primitives"


class _ClassReferenceRewriter(ast.NodeTransformer):
    def __init__(self, class_name: str, renamed: dict[str, str], functions: set[str]):
        self.class_name = class_name
        self.renamed = renamed
        self.functions = functions

    def visit_Name(self, node: ast.Name):
        name = self.renamed.get(node.id, node.id)
        if isinstance(node.ctx, ast.Load) and node.id in self.functions:
            return ast.copy_location(
                ast.Attribute(
                    value=ast.Name(id=self.class_name, ctx=ast.Load()),
                    attr=name,
                    ctx=node.ctx,
                ),
                node,
            )
        node.id = name
        return node


def render_site_primitive_class(site: str, primitives: list[Primitive]) -> str:
    """Compile independent primitive modules into one real website-scoped Python class.

    Public primitive entrypoints become static methods. Private helpers are namespaced by their
    public method so independently generated snippets cannot overwrite each other. This file is a
    materialized package view; workflows still vendor selected code rather than importing it.
    """
    class_name = site_class_name(site)
    imports: dict[str, ast.stmt] = {}
    module_values: list[ast.stmt] = []
    methods: list[ast.stmt] = []
    for primitive in primitives:
        tree = ast.parse(primitive.code, filename=f"{primitive.primitive_id}.py")
        functions = {
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assigned = {
            target.id
            for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
            if isinstance(target, ast.Name)
        }
        prefix = f"_{primitive.entrypoint}__"
        renamed = {
            name: prefix + name.lstrip("_")
            for name in functions | assigned
            if name != primitive.entrypoint
        }
        rewriter = _ClassReferenceRewriter(class_name, renamed, functions)
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.setdefault(ast.unparse(node), node)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                node = rewriter.visit(node)
                node.name = renamed.get(node.name, node.name)
                node.decorator_list.insert(0, ast.Name(id="staticmethod", ctx=ast.Load()))
                methods.append(node)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                module_values.append(rewriter.visit(node))
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue
            else:
                raise ValueError(
                    f"{primitive.primitive_id}: unsupported top-level statement "
                    f"{type(node).__name__} for site class materialization"
                )
    class_node = ast.ClassDef(
        name=class_name,
        bases=[],
        keywords=[],
        body=methods or [ast.Pass()],
        decorator_list=[],
    )
    module = ast.Module(
        body=[*imports.values(), *module_values, class_node],
        type_ignores=[],
    )
    ast.fix_missing_locations(module)
    rendered = (
        '"""Generated site primitive class; synthesis material, not a workflow dependency."""\n\n'
        + ast.unparse(module)
        + "\n"
    )
    compile(rendered, f"{site}_primitives.py", "exec")
    return rendered


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def validate_primitive(primitive: Primitive, *, other_entrypoints: set[str] | None = None) -> None:
    """Validate static MVP invariants; this is deliberately not a behavior/execution gate."""
    if not _SAFE_ID.fullmatch(primitive.site):
        raise ValueError(f"invalid primitive site: {primitive.site!r}")
    if primitive.primitive_id != f"{primitive.site}/{primitive.name}":
        raise ValueError("primitive_id must be '<site>/<name>'")
    if not _SAFE_ID.fullmatch(primitive.name):
        raise ValueError(f"invalid primitive name: {primitive.name!r}")
    if not _SAFE_ID.fullmatch(primitive.entrypoint):
        raise ValueError(f"invalid primitive entrypoint: {primitive.entrypoint!r}")
    if primitive.status not in {"active", "archived"}:
        raise ValueError("primitive status must be active or archived")
    if primitive.grade not in {"single_source", "shared"}:
        raise ValueError("primitive grade must be single_source or shared")
    if not primitive.capability.strip():
        raise ValueError("primitive capability must be non-empty")

    try:
        tree = ast.parse(primitive.code, filename=f"{primitive.primitive_id}.py")
        compile(tree, f"{primitive.primitive_id}.py", "exec")
    except SyntaxError as e:
        raise ValueError(f"primitive code does not parse: {e}") from e

    definitions = {
        n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if primitive.entrypoint not in definitions:
        raise ValueError(f"entrypoint {primitive.entrypoint!r} is not defined at module top level")

    # Runtime imports from the catalog would reintroduce the dependency/version problem that
    # vendoring intentionally avoids.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        if any(".primitives" in name or "primitive_catalog" in name for name in names):
            raise ValueError("primitive code may not import the primitive catalog")

    forbidden = (other_entrypoints or set()) - {primitive.entrypoint}
    called = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    cross_refs = sorted(called & forbidden)
    if cross_refs:
        raise ValueError(
            "active primitive snippets may not call other catalog primitives: "
            + ", ".join(cross_refs)
        )


class PrimitiveCatalog:
    """Read/write the hidden `.primitives/<site>` catalog beneath a workflow library."""

    schema_version = 1

    def __init__(self, library_root: str | Path, site: str):
        if not _SAFE_ID.fullmatch(site):
            raise ValueError(f"invalid primitive site: {site!r}")
        self.library_root = Path(library_root)
        self.site = site
        self.root = self.library_root / ".primitives" / site
        self.catalog_path = self.root / "catalog.json"
        self.class_path = self.root / "primitives.py"
        self.code_dir = self.root / "code"
        self.archive_dir = self.root / ".archive"

    def _records(self) -> list[dict]:
        if not self.catalog_path.exists():
            return []
        raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        if raw.get("schema_version") != self.schema_version or raw.get("site") != self.site:
            raise ValueError(f"invalid primitive catalog header: {self.catalog_path}")
        return list(raw.get("primitives") or [])

    def list(self, *, status: str = "active") -> list[Primitive]:
        out = []
        for rec in self._records():
            if status and rec.get("status", "active") != status:
                continue
            code_path = self.root / rec.pop("code_path")
            out.append(Primitive(code=code_path.read_text(encoding="utf-8"), **rec))
        return out

    def get(self, primitive_id: str, *, include_archived: bool = False) -> Primitive | None:
        statuses = ("active", "archived") if include_archived else ("active",)
        for status in statuses:
            for primitive in self.list(status=status):
                if primitive.primitive_id == primitive_id:
                    return primitive
        return None

    def as_site_class(self) -> SitePrimitiveClass:
        """Return the active package as a single website-scoped primitive class."""
        return SitePrimitiveClass(site=self.site, methods=self.list())

    def materialize_site_class(self) -> Path:
        """Write the active primitives as one actual Python class and return its path."""
        code = render_site_primitive_class(self.site, self.list())
        self.root.mkdir(parents=True, exist_ok=True)
        self.class_path.write_text(code, encoding="utf-8")
        return self.class_path

    def upsert(self, primitive: Primitive) -> Primitive:
        """Add or replace the one active implementation of a primitive."""
        if primitive.site != self.site:
            raise ValueError(f"primitive site {primitive.site!r} != catalog site {self.site!r}")
        existing = self.list(status="active")
        entrypoints = {p.entrypoint for p in existing if p.primitive_id != primitive.primitive_id}
        validate_primitive(primitive, other_entrypoints=entrypoints)
        # Also ensure replacing/adding this entry does not make an existing snippet reference it.
        for current in existing:
            if current.primitive_id != primitive.primitive_id:
                validate_primitive(current, other_entrypoints=entrypoints | {primitive.entrypoint})

        self.code_dir.mkdir(parents=True, exist_ok=True)
        code_path = self.code_dir / f"{primitive.name}.py"
        code_path.write_text(primitive.code, encoding="utf-8")

        records = [
            rec for rec in self._records()
            if rec.get("primitive_id") != primitive.primitive_id
        ]
        rec = asdict(primitive)
        rec.pop("code")
        rec["code_path"] = str(code_path.relative_to(self.root))
        records.append(rec)
        records.sort(key=lambda r: r["primitive_id"])
        _atomic_json(self.catalog_path, {
            "schema_version": self.schema_version,
            "site": self.site,
            "primitives": records,
        })
        self.materialize_site_class()
        return primitive

    def archive(self, primitive_id: str) -> bool:
        primitive = self.get(primitive_id)
        if primitive is None:
            return False
        source = self.code_dir / f"{primitive.name}.py"
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        target = self.archive_dir / f"{primitive.name}-{primitive.content_hash[7:19]}.py"
        source.replace(target)

        records = []
        for rec in self._records():
            if rec.get("primitive_id") == primitive_id:
                rec = dict(rec)
                rec["status"] = "archived"
                rec["code_path"] = str(target.relative_to(self.root))
            records.append(rec)
        _atomic_json(self.catalog_path, {
            "schema_version": self.schema_version,
            "site": self.site,
            "primitives": records,
        })
        self.materialize_site_class()
        return True
