"""Llamadas a herramientas que el modelo escribe como texto en vez de usar el canal de
herramientas (le pasa a qwen2.5 de vez en cuando):

    close_app({"name": "Spotify"})
    openapp(name="Bloc de notas")
    {"name": "close_app", "arguments": {"name": "Spotify"}}
    <tool_call>{"name": "set_volume", "arguments": {"level": 20}}</tool_call>

Sin esto, Nyx leería en voz alta «close_app…». El texto se retiene mientras pueda ser una
llamada (`could_be_call`) y, al terminar, se convierte en plan (`parse_text_calls`).
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterable
from typing import Any

from nyx.brain.base import LLMToolCall

_TAGS = re.compile(r"</?tool_call>")
_CALL_START = re.compile(r"^\s*(?:<tool_call>|\{|`*\s*([A-Za-z_]+)\s*[({])")
_SPACED = re.compile(r"^([A-Za-z_]+)\s+(\{.*\})$")  # «mediacontrol {"action": …}»
_FENCE_LANGS = {"", "json", "python", "tool_code"}


def _key(name: str) -> str:
    return name.replace("_", "").lower()


def could_be_call(head: str, tool_names: Iterable[str]) -> bool:
    """¿El principio de la respuesta parece una llamada escrita? (`head` sin «[» de cabecera)."""
    m = _CALL_START.match(head)
    if m is None:
        return False
    name = m.group(1)
    return name is None or _key(name) in {_key(n) for n in tool_names}


def _from_json(obj: Any, names: dict[str, str]) -> LLMToolCall | None:
    if not isinstance(obj, dict):
        return None
    fn = obj.get("function", obj)
    name, args = fn.get("name"), fn.get("arguments", fn.get("parameters", {}))
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            return None
    if not isinstance(name, str) or _key(name) not in names or not isinstance(args, dict):
        return None
    return LLMToolCall(names[_key(name)], args)


def _literal(node: ast.expr) -> Any:
    # JSON dentro de una llamada de Python: null/true/false llegan como nombres.
    if isinstance(node, ast.Name) and node.id in ("null", "true", "false", "None"):
        return {"null": None, "true": True, "false": False, "None": None}[node.id]
    return ast.literal_eval(node)


def _from_python(line: str, names: dict[str, str]) -> LLMToolCall | None:
    try:
        tree = ast.parse(line.strip(), mode="eval")
    except SyntaxError:
        return None
    call = tree.body
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
        return None
    name = names.get(_key(call.func.id))
    if name is None:
        return None
    try:
        if len(call.args) == 1 and not call.keywords:  # close_app({"name": "Spotify"})
            source = ast.get_source_segment(line.strip(), call.args[0]) or ""
            try:
                args = json.loads(source)  # JSON: null, true, false
            except ValueError:
                args = _literal(call.args[0])
            return LLMToolCall(name, args) if isinstance(args, dict) else None
        if call.args:
            return None
        return LLMToolCall(name, {k.arg: _literal(k.value) for k in call.keywords if k.arg})
    except (ValueError, TypeError, SyntaxError):
        return None


def parse_text_calls(text: str, tool_names: Iterable[str]) -> list[LLMToolCall]:
    """Las llamadas escritas en `text`, en orden; [] si alguna línea no lo es."""
    names = {_key(n): n for n in tool_names}
    body = _TAGS.sub("\n", text).strip()
    if not body:
        return []
    # Un único JSON (puede ser una lista de llamadas).
    try:
        obj = json.loads(body)
    except ValueError:
        obj = None
    if obj is not None:
        items = obj if isinstance(obj, list) else [obj]
        parsed = [_from_json(item, names) for item in items]
        whole = [c for c in parsed if c is not None]
        return whole if len(whole) == len(parsed) else []
    calls: list[LLMToolCall] = []
    for raw in body.splitlines():
        line = raw.strip().strip("`").strip().rstrip(";")
        if line in _FENCE_LANGS:  # ``` o ```python
            continue
        found: LLMToolCall | None
        spaced = _SPACED.match(line)
        if line.startswith("{"):
            try:
                found = _from_json(json.loads(line), names)
            except ValueError:
                found = None
        elif spaced and _key(spaced.group(1)) in names:  # «mediacontrol {"action": …}»
            try:
                args = json.loads(spaced.group(2))
            except ValueError:
                args = None
            name = names[_key(spaced.group(1))]
            found = LLMToolCall(name, args) if isinstance(args, dict) else None
        else:
            found = _from_python(line, names)
        if found is None:
            return []
        calls.append(found)
    return calls
