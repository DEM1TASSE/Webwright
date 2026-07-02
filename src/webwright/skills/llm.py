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
    # default: build an openai-style model from env so a bare CLI invocation
    # (e.g. `python -m webwright.tools.skill_use`) uses the SAME backend as the running agent.
    # Honors SKILL_MODEL_NAME / SKILL_MODEL_ENDPOINT (or OPENAI_* fallbacks); no hardcoded gateway.
    import os
    # long request timeout: refine emits a large skill (~16k tokens) which is slow on a busy
    # gateway; the model default (120s) truncates/ReadTimeouts. Overridable via SKILL_MODEL_TIMEOUT.
    cfg = {"model_class": os.environ.get("SKILL_MODEL_CLASS", "openai"),
           "request_timeout_seconds": int(os.environ.get("SKILL_MODEL_TIMEOUT", "600"))}
    name = os.environ.get("SKILL_MODEL_NAME") or os.environ.get("OPENAI_MODEL")
    endpoint = os.environ.get("SKILL_MODEL_ENDPOINT") or os.environ.get("OPENAI_ENDPOINT")
    if name:
        cfg["model_name"] = name
    if endpoint:
        cfg["openai_endpoint"] = endpoint
    return get_model(cfg)


def llm(system: str, user: str, *, model: Any = None, max_tokens: int | None = None, **_: Any) -> str:
    """Single-turn call. Returns raw text. `model` overrides the configured default.
    max_tokens caps the reply length (the model default is small ~4000, which truncates a
    refined skill); pass it through to the model so large code outputs aren't cut off."""
    m = model if model is not None else _model()
    messages = [
        m.format_message(role="system", content=system),
        m.format_message(role="user", content=user),
    ]
    if max_tokens is not None:
        return m(messages, max_output_tokens=max_tokens)
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
