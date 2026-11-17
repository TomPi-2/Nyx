"""Reglas de acciones dentro de las apps (pestañas, guardar, Discord) y de escribir."""

from __future__ import annotations

import re
from collections.abc import Callable

from nyx.brain.router import comun
from nyx.brain.router.comun import (
    _RAW_EXACT,
    _RAW_POLITE,
    Route,
    _call,
    _clean_dictated,
    _original,
    rule,
)
from nyx.executor import ToolCall
from nyx.index.aliases import normalize, strip_articles
from nyx.index.model import Kind
from nyx.index.service import SystemIndex
from nyx.tools.app_catalog import profile_for


@rule(
    "new_tab",
    r"^(?:abre(?:me)?|crea(?:me)?|pon(?:me)?|haz(?:me)?)\s+(?:una\s+|otra\s+)?(?:nueva\s+(?:pestana|nota|ventana)|(?:pestana|nota)\s+nueva)"
    r"(?:\s+(?:dentro del|dentro de|en|del|de)\s+(?:el\s+|la\s+)?(?P<app>.+))?$",
)
def _new_tab(m: re.Match[str], index: SystemIndex) -> Route | None:
    if not m.group("app"):
        return _call("new_tab", "app_action", action="new_tab")
    best = index.confident(index.resolve(m.group("app"), {Kind.APP}))
    if best is None:
        return None
    name = best.entry.name
    if not comun._find_windows(name, best.entry.process):
        return _call("new_tab", "open_app", name=name)  # abrirla ya deja una nueva
    if profile_for(best.entry.process, name) is None:
        return _call("new_tab", "send_hotkey", keys="ctrl+t", app=name)
    return _call("new_tab", "app_action", app=name, action="new_tab")


def _app_named(m: re.Match[str], index: SystemIndex) -> tuple[bool, str | None]:
    """(válida, nombre de la app) para «… en Chrome»; sin app → la ventana activa."""
    raw = m.groupdict().get("app")
    if not raw:
        return True, None
    best = index.confident(index.resolve(raw, {Kind.APP}))
    return (best is not None, best.entry.name if best else None)


def _in_app(rule_name: str, action: str) -> Callable[[re.Match[str], SystemIndex], Route | None]:
    def handler(m: re.Match[str], index: SystemIndex) -> Route | None:
        ok, app = _app_named(m, index)
        return _call(rule_name, "app_action", action=action, app=app) if ok else None

    return handler


_IN = r"(?:\s+(?:en|de|del|dentro del?)\s+(?:el\s+|la\s+)?(?P<app>.+))?$"
rule("close_tab", r"^cierra(?:me)?\s+(?:la\s+|esta\s+)?pestana" + _IN)(
    _in_app("close_tab", "close_tab")
)
rule(
    "reopen_tab",
    r"^(?:reabre|recupera|vuelve a abrir)\s+(?:la\s+)?(?:ultima\s+)?pestana(?:\s+cerrada)?" + _IN,
)(_in_app("reopen_tab", "reopen_tab"))
rule("reload", r"^(?:recarga|refresca)(?:\s+(?:la\s+)?(?:pagina|web))?" + _IN)(
    _in_app("reload", "reload")
)
rule(
    "incognito",
    r"^abre(?:me)?\s+(?:una\s+)?(?:ventana\s+(?:de\s+)?)?(?:incognito|privada)" + _IN,
)(_in_app("incognito", "incognito"))
rule(
    "discord_mute",
    r"^(?:silencia|mutea|desmutea|desilencia|activa|desactiva|apaga|enciende)\s+(?:el\s+|mi\s+)?micro(?:fono)?(?:\s+(?:en|de)\s+discord)?$",
)(lambda m, index: _call("discord_mute", "app_action", app="Discord", action="toggle_mute"))
rule("discord_deafen", r"^ensordece(?:me)?(?:\s+(?:en|de)\s+discord)?$")(
    lambda m, index: _call("discord_deafen", "app_action", app="Discord", action="toggle_deafen")
)

rule(
    "save",
    r"^guarda(?:me)?(?:\s+(?:el\s+|la\s+|los\s+)?(?:documento|archivo|cambios|nota|texto))?" + _IN,
)(_in_app("save", "save"))


@rule(
    "type_text_in_app",
    r"^(?:escribe|teclea|dicta)(?:me)?\s+en\s+(?P<rest>.+)$",
)
def _type_text_in_app(m: re.Match[str], index: SystemIndex) -> Route | None:
    raw_line = _RAW_POLITE.sub("", _RAW_EXACT.get().strip()).strip()
    rm = re.match(r"^(?:escribe|teclea|dicta)(?:me)?\s+en\s+(.+)$", raw_line, re.I)
    rest = rm.group(1).strip() if rm else m.group("rest")
    if dm := re.match(r"^(?P<app>[^:.,]+?)\s*[:.,]\s+(?P<text>.+)$", rest):
        cand = strip_articles(normalize(dm.group("app")))
        best = index.confident(index.resolve(cand, {Kind.APP})) if cand else None
        if best is not None or (cand and comun._find_windows(cand, None)):
            app_name = best.entry.name if best is not None else dm.group("app").strip()
            text = _clean_dictated(dm.group("text"))
            if text:
                return _call("type_text_in_app", "type_text", app=app_name, text=text)
    words = rest.split()
    for k in range(min(4, len(words) - 1), 0, -1):
        prefix = " ".join(words[:k])
        cand = strip_articles(normalize(prefix))
        if not cand:
            continue
        best = index.confident(index.resolve(cand, {Kind.APP}))
        if best is not None or comun._find_windows(cand, None):
            app_name = best.entry.name if best is not None else prefix
            text = _clean_dictated(" ".join(words[k:]))
            if text:
                return _call("type_text_in_app", "type_text", app=app_name, text=text)
    return None


@rule(
    "type_text",
    r"^(?:escribe|teclea|dicta)\s+(?!en\s+|un\s+|una\s+)(?P<text>.+)$",
)
def _type_text(m: re.Match[str], index: SystemIndex) -> Route:
    rm = re.search(r"(?:escribe|teclea|dicta)[:\s]+(.+)$", _RAW_EXACT.get().strip(), re.I)
    text = _clean_dictated(rm.group(1)) if rm else ""
    text = text or _original(m.group("text"))
    # «Escribe hola en el Bloc de notas»: la app va al final (2026-11-17 escribía «hola en el
    # Bloc de notas»). Solo si es una app conocida o una ventana abierta.
    if tail := re.match(
        r"^(?P<text>.+?)\s+en\s+(?:el\s+|la\s+)?(?P<app>[^,.:]{2,40})$", text, re.I
    ):
        cand = strip_articles(normalize(tail.group("app")))
        best = index.confident(index.resolve(cand, {Kind.APP})) if cand else None
        if best is not None or (cand and comun._find_windows(cand, None)):
            app_name = best.entry.name if best is not None else tail.group("app").strip()
            return _call("type_text", "type_text", app=app_name, text=tail.group("text"))
    return _call("type_text", "type_text", text=text)


# --- zoom y buscar en la página (6.25) ---


@rule(
    "zoom",
    r"^(?:acerca|amplia|agranda|haz\s+mas\s+grande)(?:me)?\s+(?:un\s+poco\s+)?(?:la\s+)?"
    r"(?P<in>pagina|letra|texto)(?:\s+que\s+no\s+(?:veo|leo)(?:\s+(?:la\s+letra|bien|nada))?)?$"
    r"|^(?:aleja|reduce|haz\s+mas\s+pequen[ao])(?:me)?\s+(?:un\s+poco\s+)?(?:la\s+)?"
    r"(?P<out>pagina|letra|texto)$",
)
def _zoom(m: re.Match[str], __: SystemIndex) -> Route:
    return _call("zoom", "app_action", action="zoom_in" if m.group("in") else "zoom_out")


@rule(
    "find_in_page",
    # «busca en esta página la palabra precio», «busca Madrid en la página»: abrir la búsqueda
    # de la app (Ctrl+F) y escribir lo que se busca.
    r"^busca(?:me)?\s+en\s+(?:esta|la)\s+(?:pagina|web)\s+(?:la\s+palabra\s+|el\s+texto\s+)?(?P<q>.+)$"
    r"|^busca(?:me)?\s+(?:la\s+palabra\s+|el\s+texto\s+)?(?P<q2>.+?)\s+en\s+(?:esta|la)\s+(?:pagina|web)$",
)
def _find_in_page(m: re.Match[str], __: SystemIndex) -> Route:
    text = _original(m.group("q") or m.group("q2"))
    return Route(
        [ToolCall("app_action", {"action": "find"}), ToolCall("type_text", {"text": text})],
        "find_in_page",
    )


@rule(
    "page_back",
    # 6.25: «vuelve a la página anterior» («vuelve atrás» es deshacer, regla `undo`).
    r"^(?:vuelve|ve|regresa|vete)\s+a\s+la\s+pagina\s+anterior$|^pagina\s+anterior$",
)
def _page_back(_: re.Match[str], __: SystemIndex) -> Route:
    return _call("page_back", "app_action", action="back")
