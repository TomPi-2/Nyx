"""Reglas de ventanas: pantalla completa, colocar, cambiar de ventana y capturas."""

from __future__ import annotations

import re

from nyx.brain.router import comun
from nyx.brain.router.comun import (
    Route,
    _call,
    _window_name,
    rule,
)
from nyx.executor import ToolCall
from nyx.index.model import Kind
from nyx.index.service import SystemIndex
from nyx.tools.app_catalog import profile_for


@rule(
    "fullscreen",
    r"^(?:(?:pon(?:me)?|haz|deja)\s+(?:el\s+|la\s+)?(?P<x>.+?)\s+(?:en\s+)?|)pantalla completa$",
)
def _fullscreen(m: re.Match[str], index: SystemIndex) -> Route | None:
    raw = m.group("x")
    if raw in (None, "esto", "la ventana", "esta ventana"):
        return _call("fullscreen", "app_action", action="fullscreen")
    best = index.confident(index.resolve(raw, {Kind.APP}))
    named = profile_for(best.entry.process if best else None, raw)
    app = best.entry.name if best else None
    if named is not None and "fullscreen" in named.actions:
        return _call("fullscreen", "app_action", action="fullscreen", app=app or raw)
    if app is None:
        return None
    return _call("fullscreen", "window_layout", action="maximize", name=app)


@rule(
    "two_windows",
    r"^(?:pon|mueve|coloca)\s+(?P<a>.+?)\s+a la (?P<s1>izquierda|derecha)\s+y\s+"
    r"(?:a\s+)?(?P<b>.+?)\s+a la (?P<s2>izquierda|derecha)$",
)
def _two_windows(m: re.Match[str], _: SystemIndex) -> Route:
    side = {"izquierda": "left", "derecha": "right"}
    return Route(
        [
            ToolCall("window_layout", {"action": side[m.group("s1")], "name": m.group("a")}),
            ToolCall("window_layout", {"action": side[m.group("s2")], "name": m.group("b")}),
        ],
        "two_windows",
    )


# --- capturas ---


@rule(
    "screenshot",
    r"^(?:(?:haz(?:me)?|saca(?:me)?|toma)\s+(?:una?\s+)?)?(?:captura|screenshot|pantallazo)(?:\s+de\s+pantalla)?(?P<rest>.*)$",
)
def _screenshot(m: re.Match[str], _: SystemIndex) -> Route:
    rest = m.group("rest")
    if re.search(r"principal", rest):
        target = "primary"
    elif re.search(r"tod[oa]s?|los dos|ambos|las dos", rest):
        target = "all"
    elif re.search(r"ventana", rest):
        target = "window"
    else:
        target = "current"
    return _call("screenshot", "screenshot", target=target)


@rule(
    "window_state",
    r"^(?:(?:quiero\s+que|puedes|podrias)\s+)?"
    r"(?P<verb>maximiza(?:r)?|maximices|minimiza(?:r)?|minimices|minimize|"
    r"oculta(?:r)?|ocultes|esconde(?:r)?|escondas|restaura(?:r)?|restaures)"
    r"(?:\s+(?P<x>.+?))?(?:\s+para\s+no\s+verl[oa](?:\s+(?:en\s+(?:la\s+)?pantalla|mas))?)?$",
)
def _window_state(m: re.Match[str], _: SystemIndex) -> Route:
    v = m.group("verb")
    if v.startswith("maxi"):
        action = "maximize"
    elif v.startswith("rest"):
        action = "restore"
    else:
        action = "minimize"
    return _call("window_state", "window_layout", action=action, name=_window_name(m.group("x")))


@rule("window_side", r"^(?:pon|mueve|coloca|pasa)\s+(?P<x>.+?)\s+a la (?P<side>izquierda|derecha)$")
def _window_side(m: re.Match[str], _: SystemIndex) -> Route | None:
    if " y " in m.group("x"):
        return None  # dos ventanas: plan de varios pasos (LLM)
    action = "left" if m.group("side") == "izquierda" else "right"
    return _call("window_side", "window_layout", action=action, name=_window_name(m.group("x")))


@rule(
    "window_monitor",
    r"^(?:pon|mueve|pasa|lleva)\s+(?P<x>.+?)\s+al?\s+(?:otro|siguiente|segundo)\s+(?:monitor|pantalla)$",
)
def _window_monitor(m: re.Match[str], _: SystemIndex) -> Route:
    return _call(
        "window_monitor", "window_layout", action="next_monitor", name=_window_name(m.group("x"))
    )


@rule(
    "focus",
    r"^(?:cambia a|ve a|vete a|pasa a|muestrame|ensename|trae)\s+(?:la ventana de\s+)?(?P<x>.+)$",
)
def _focus(m: re.Match[str], index: SystemIndex) -> Route | None:
    # Solo si lo que se pide es una app o una ventana que existe: «muéstrame los FPS en el
    # Rocket League» no es «trae al frente la ventana "los fps…"» (ERRORES.md, 2026-11-11).
    name = m.group("x")
    if index.confident(index.resolve(name, {Kind.APP, Kind.GAME})) or comun._find_windows(
        name, None
    ):
        return _call("focus", "focus_window", name=name)
    return None
