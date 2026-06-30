"""LLM helper for the skills module — backend-agnostic, via webwright's own model abstraction.

No hardcoded gateway/endpoint/key: the caller passes a webwright Model (or a model config dict),
so this works with any backend webwright supports (openai / anthropic / openrouter / custom).
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from webwright.models import get_model

# Process-wide default model, set once via configure_llm() so retrieve/decide/update can call
# llm() without each caller threading a Model through. Falls back to env-configured openai.
_DEFAULT_MODEL: Optional[Any] = None


def configure_llm(model: Any) -> None:
    """Register the Model (or model-config dict) the skills module should use."""
    global _DEFAULT_MODEL
    _DEFAULT_MODEL = get_model(model) if isinstance(model, dict) else model


def _model() -> Any:
    if _DEFAULT_MODEL is not None:
        return _DEFAULT_MODEL
    # default: openai model from env (OPENAI_API_KEY / OPENAI_BASE_URL respected by the model class)
    return get_model({"model_class": "openai"})


def llm(system: str, user: str, *, model: Any = None, **_: Any) -> str:
    """Single-turn call. Returns raw text. `model` overrides the configured default."""
    m = model if model is not None else _model()
    messages = [
        m.format_message(role="system", content=system),
        m.format_message(role="user", content=user),
    ]
    return m(messages)


def llm_json(system: str, user: str, **kw: Any) -> dict:
    """Call + parse the first {...} JSON object out of the reply."""
    txt = llm(system, user, **kw)
    match = re.search(r"\{.*\}", txt, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except Exception:
        s = match.group(0)
        for end in range(len(s), 0, -1):
            try:
                return json.loads(s[:end])
            except Exception:
                continue
    return {}
