"""Minimal adapter: an ASI-induced action library -> a Webwright prompt hint.

Why this exists
---------------
Agent Skill Induction (ASI) ships one action module per site and consumes it by injecting the
WHOLE site action space into every step's prompt -- there is no retrieval (its
`RETRIEVABLE_ACTIONS_DICT` is empty for all five sites, so the embedding/top-k scaffolding in
`custom_action_set.py` never runs).  The faithful analogue here is therefore: no selection, no
router, no contract -- hand the agent the same block ASI's own policy model sees.

That block is produced by ASI's `CustomActionSet.describe(with_long_description=True,
with_examples=True)` and is frozen ahead of time (see MANIFEST.json in the library root), because
generating it needs browsergym, which this environment does not carry.  Two tiers appear inside
it, and the asymmetry is ASI's own (`custom_action_set.py:163`, `add_code`):
  * browsergym base primitives -> signature + description + examples, NO body;
  * induced skills            -> full `inspect.getsource`, body included.

Deliberately NOT done here: no primitive catalog entry, no contract, no gate, no marker request.
skillnet_hint.py's `_marker` docstring gives the reason for the last one -- asking the agent to
record its usage presupposes usage, and usage rate is exactly what this arm measures.  Reuse is
detected by function name instead; the induced names are unique enough.

Deviations from upstream ASI, on purpose:
  * ASI's action-space section is followed by two chain-of-thought examples and
    "Only wrap the to-be-executed action in triple backticks".  Those teach ASI's own emission
    format (one action per turn, in triple backticks), which directly contradicts Webwright's
    JSON + bash contract, so they are dropped.  Everything else in the block is verbatim,
    including the trailing multiaction sentence that `describe()` appends because ASI passes
    `multiaction=True` (agent.py:88).
  * ASI's bids are live AXTree indices; nothing resolves them here.  One sentence says so.
    That sentence is the ONLY text in this hint that upstream did not write.
"""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_LIBRARY_ROOT = "/data/demiwang/results/webarena/ww_asi/library"

# The one sentence upstream did not write.  skillnet_hint.render_hint states the equivalent fact
# about relative `page.goto`; the register is copied from there deliberately.
_RUNTIME_NOTE = (
    "These functions were generated from prior successful trajectories on this website. The "
    "primitives\nthey call (`click`, `fill`, `select_option`, ...) are documented in the same "
    "listing below. They take\nelement indices (`bid`) that are assigned per page render; this "
    "runtime does not assign or resolve\nthem."
)

# Verbatim, agent.py:263 -- the quoting is unbalanced upstream and is preserved.
_UPSTREAM_MANDATE = (
    "When high-level functions such as `get_driving_time` or 'book_flights` are available, "
    "please prioritize using them."
)


def library_key(sites) -> str:
    """ASI takes `--websites` as a tuple and accumulates the modules, so a multi-site task gets a
    combined block.  The frozen files are named by the task's own site list, in dataset order."""
    return "+".join(sites)


def load_block(sites, library_root: str = DEFAULT_LIBRARY_ROOT) -> tuple[str, dict]:
    root = Path(library_root)
    manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
    name = library_key(sites) + ".txt"
    path = root / name
    if not path.is_file():
        raise FileNotFoundError(
            f"no frozen ASI library for sites {list(sites)}: {path} "
            f"(available: {sorted(manifest['files'])})"
        )
    return path.read_text(encoding="utf-8").rstrip("\n"), manifest["files"][name]


def prepare_asi_hint(sites, library_root: str = DEFAULT_LIBRARY_ROOT,
                     record_path: Path | None = None) -> dict:
    block, meta = load_block(sites, library_root)
    hint = (
        "## Site action library\n"
        + _RUNTIME_NOTE + "\n\n"
        + _UPSTREAM_MANDATE + "\n\n"
        + "```python\n" + block + "\n```\n"
    )
    out = {
        "hint": hint,
        "sites": list(sites),
        "library_file": library_key(sites) + ".txt",
        "sha256": meta["sha256"],
        "induced_functions": meta["induced_functions"],
        "asi_modules": meta["asi_modules"],
        "unsupported_sites": meta["unsupported_sites"],
        "decision": "inject",
        "reason": "ASI performs no retrieval; the whole site action space is injected verbatim.",
    }
    if record_path is not None:
        Path(record_path).parent.mkdir(parents=True, exist_ok=True)
        Path(record_path).write_text(
            json.dumps({k: v for k, v in out.items() if k != "hint"},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out
