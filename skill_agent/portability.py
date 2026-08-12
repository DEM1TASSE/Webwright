"""Keep generated code parsable by interpreters older than the one that built it.

PEP 701 (Python 3.12) allows reusing a quote character inside an f-string expression:
``f'{stop['longitude']}'``. On 3.11 and earlier that is a SyntaxError.

Only one way this actually reaches a package, and it is not the agent:

**the renderer produces it from portable input.** ``render_site_package`` round-trips
   method code through ``ast.unparse``, which normalizes every string literal to single
   quotes. Given the agent's portable ``f"{point['longitude']}"`` it emits
   ``f'{point['longitude']}'``. Nothing the agent does can prevent this, and the scripted
   pipeline has the same defect — two rejected scripted Map runs carry it.

``make_portable`` repairs case 2 after rendering by swapping the outer quotes back, and only
accepts the rewrite when the result parses to an identical AST.

This is about how code is spelled, not about what a primitive owns, so it does not change
library semantics — every final scripted package is already clean and round-trips unchanged.
"""
from __future__ import annotations

import ast
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


def _flagged_fstring_spans(code: str) -> list[tuple[tuple[int, int], tuple[int, int], str]]:
    """Return (start, end, quote) for each f-string whose expression reuses its delimiter.

    ``start``/``end`` are (row, col) of the FSTRING_START and FSTRING_END tokens. An f-string
    whose body also contains the *other* quote character is skipped: swapping delimiters
    would not be a safe mechanical fix there.
    """
    if not hasattr(tokenize, "FSTRING_START"):
        return []
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []
    spans, stack = [], []
    for token in tokens:
        if token.type == tokenize.FSTRING_START:
            stack.append({"start": token.start, "quote": token.string.lstrip("fFrRbB")[:1],
                          "reused": False, "other": False})
        elif token.type == tokenize.FSTRING_END:
            if not stack:
                continue
            frame = stack.pop()
            if frame["reused"] and not frame["other"]:
                spans.append((frame["start"], token.start, frame["quote"]))
        elif token.type == tokenize.STRING and stack:
            inner = token.string.lstrip("fFrRbB")[:1]
            if inner == stack[-1]["quote"]:
                stack[-1]["reused"] = True
            elif inner in {"'", '"'}:
                stack[-1]["other"] = True
    return spans


def make_portable(code: str) -> tuple[str, list[str]]:
    """Swap the outer quotes of f-strings that reuse their delimiter.

    Returns ``(code, notes)``. The rewrite is applied only if the result parses to an AST
    identical to the original and no longer trips the check; otherwise the code is returned
    unchanged so the caller can fail loudly rather than ship a silently altered package.
    """
    spans = _flagged_fstring_spans(code)
    if not spans:
        return code, []

    lines = code.splitlines(keepends=True)
    swap = {"'": '"', '"': "'"}
    # Rewrite from the end so earlier positions stay valid.
    for (start_row, start_col), (end_row, end_col), quote in sorted(spans, reverse=True):
        for row, col in ((end_row, end_col), (start_row, start_col)):
            line = lines[row - 1]
            index = line.find(quote, col)
            if index == -1:
                return code, ["could not locate f-string delimiter to repair"]
            lines[row - 1] = line[:index] + swap[quote] + line[index + 1:]
    rewritten = "".join(lines)

    try:
        same = ast.dump(ast.parse(rewritten)) == ast.dump(ast.parse(code))
    except SyntaxError as exc:
        return code, [f"portability rewrite produced invalid code: {exc}"]
    if not same:
        return code, ["portability rewrite changed the AST; refusing to apply it"]
    if fstring_quote_reuse(rewritten):
        return code, ["portability rewrite did not remove every quote reuse"]
    return rewritten, [f"rewrote {len(spans)} f-string(s) emitted by ast.unparse "
                       f"so the package parses before Python 3.12"]
