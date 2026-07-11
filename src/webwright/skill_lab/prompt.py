"""Prompt helper: prepend a SKILL-LIBRARY hint to a task prompt so the agent reuses the library.

Kept at the prompt level (not system_template) because webwright merges system_template by
replacement; a task-prompt hint is non-invasive and leaves default behavior unchanged when unused.
"""
from __future__ import annotations

import shlex
from pathlib import Path

_HINT = """## Skill library (reuse before solving from scratch)
A library of previously-built executable code skills may contain one that helps this task.
BEFORE planning from scratch, query it ONCE from bash:

    python -m webwright.tools.skill_use --task {task_q} --library {library_q}

It returns JSON {{verdict, skill_id, source_path, how_to_reuse}}:
- "use"   : read source_path, copy it into your final_script, fill THIS task's params.
- "adapt" : read source_path, reuse its login/navigation/extraction core, change ONLY the last step.
- "skip"  : no useful skill — solve from scratch.
Record your choice in skill_decision.json ({{skill_id, verdict, reason}}) before acting.

---
"""


def with_skill_hint(task_prompt: str, *, task: str, library: str) -> str:
    """Prepend the skill-library hint to a task prompt.

    `library` is resolved to an ABSOLUTE path: the hint's command runs in the agent's
    own workspace, so a relative path would silently point at a nonexistent (empty)
    library there and every lookup would come back "skip". Both values are shell-quoted:
    the agent executes this line in bash, where $VAR / `...` / $(...) would otherwise
    expand even inside double quotes."""
    library = str(Path(library).resolve())
    return _HINT.format(task_q=shlex.quote(task), library_q=shlex.quote(library)) + task_prompt
