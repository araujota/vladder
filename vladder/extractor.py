from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ExtractedFunction:
    name: str
    source: str
    start: int
    end: int
    signature: str
    body: str

    def renamed(self, new_name: str) -> str:
        name_match = re.search(rf"\b{re.escape(self.name)}\b\s*\(", self.source)
        if not name_match:
            raise ValueError(f"could not rename function {self.name}")
        return self.source[: name_match.start()] + new_name + self.source[name_match.end() - 1 :]


def _skip_ws_backward(text: str, idx: int) -> int:
    while idx > 0 and text[idx - 1].isspace():
        idx -= 1
    return idx


def _find_function_start(text: str, name_pos: int) -> int:
    line_start = text.rfind("\n", 0, name_pos) + 1
    while line_start > 0:
        prev_end = _skip_ws_backward(text, line_start - 1)
        prev_start = text.rfind("\n", 0, prev_end) + 1
        line = text[prev_start:prev_end].strip()
        if not line or line.startswith("#") or line.endswith((";", "}")):
            break
        line_start = prev_start
    return line_start


def _brace_match(text: str, open_idx: int) -> int:
    depth = 0
    in_string: str | None = None
    escaped = False
    i = open_idx
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == in_string:
                in_string = None
        elif ch in ('"', "'"):
            in_string = ch
        elif ch == "/" and nxt == "/":
            end = text.find("\n", i + 2)
            i = len(text) if end == -1 else end
            continue
        elif ch == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            i = len(text) if end == -1 else end + 2
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced braces in target function")


def extract_function(source: str, function: str) -> ExtractedFunction:
    match = re.search(rf"\b{re.escape(function)}\b\s*\(", source)
    if not match:
        raise ValueError(f"function {function!r} not found")

    paren_depth = 0
    close_paren = None
    for i in range(match.end() - 1, len(source)):
        if source[i] == "(":
            paren_depth += 1
        elif source[i] == ")":
            paren_depth -= 1
            if paren_depth == 0:
                close_paren = i
                break
    if close_paren is None:
        raise ValueError(f"could not parse signature for {function!r}")

    open_brace = source.find("{", close_paren)
    if open_brace == -1:
        raise ValueError(f"function {function!r} appears to be a declaration")

    start = _find_function_start(source, match.start())
    end = _brace_match(source, open_brace)
    fn_source = source[start:end]
    signature = source[start:open_brace].strip()
    body = source[open_brace + 1 : end - 1]
    return ExtractedFunction(function, fn_source, start, end, signature, body)
