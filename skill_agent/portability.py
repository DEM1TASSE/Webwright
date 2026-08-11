"""Reject generated method code that only parses on the build machine's interpreter.

PEP 701 (Python 3.12) allows reusing a quote character inside an f-string expression:
``f'{stop['longitude']}'``. On 3.11 and earlier that is a SyntaxError. The pipeline's
validators call ``ast.parse``, which runs on whatever interpreter drives the build, so a
3.12 build happily emits a package that a 3.10 consumer cannot import — and the agent gets
no signal to fix it, because nothing it can run says no.

Prompt guidance alone does not hold here: an agent told the rule still wrote the nesting,
because every command it ran exited 0. So this is enforced as a check.

The rule is about how the code is written, not about what a primitive owns, so it does not
change library semantics — every existing scripted package passes it.
"""
from __future__ import annotations

import io
import tokenize

MIN_VERSION = (3, 10)


def fstring_quote_reuse(code: str) -> list[str]:
    """Return an error per f-string that reuses its own delimiter inside an expression.

    Only 3.12+ tokenizers split f-strings into FSTRING_START/MIDDLE/END, which is exactly
    when the offending source is silently accepted. On an older interpreter the surrounding
    ``ast.parse`` already rejects it, so there is nothing left to detect.
    """
    if not hasattr(tokenize, "FSTRING_START"):
        return []
    errors: list[str] = []
    delimiters: list[str] = []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []  # the shared validator's ast.parse reports malformed code
    for token in tokens:
        if token.type == tokenize.FSTRING_START:
            delimiters.append(token.string.lstrip("fFrRbB")[:1])
        elif token.type == tokenize.FSTRING_END:
            if delimiters:
                delimiters.pop()
        elif token.type == tokenize.STRING and delimiters:
            inner = token.string.lstrip("fFrRbB")[:1]
            if inner and inner == delimiters[-1]:
                errors.append(
                    f"line {token.start[0]}: f-string expression reuses its own {inner} quote "
                    f"({token.string}); this is a SyntaxError before Python 3.12. Use the other "
                    f"quote character for the outer f-string, or assign to a local variable first."
                )
    return errors


def check_method_code(code: str, *, where: str) -> list[str]:
    return [f"{where}: {error}" for error in fstring_quote_reuse(code)]


def check_primitives(primitives: list[dict]) -> list[str]:
    """Lint every method body in a list of primitive replacement objects."""
    errors: list[str] = []
    for primitive in primitives:
        if not isinstance(primitive, dict):
            continue
        code = primitive.get("method_code")
        if isinstance(code, str) and code:
            errors.extend(check_method_code(
                code, where=str(primitive.get("primitive_id") or primitive.get("method") or "?")))
    return errors
