"""Router rápido, nivel 1 del cerebro (SPEC sección 6): frases frecuentes → herramienta, sin LLM.

Solo actúa si está seguro. Si el patrón encaja pero el nombre no se resuelve con claridad,
lo dice (`Miss`) para que el pipeline explique «no encuentro X»; en el bloque 3c esos casos
pasarán al LLM con los candidatos como pista."""

from __future__ import annotations

import re

from nyx.brain.base import LLMToolCall

# Cada tema registra sus reglas al importarse.
from nyx.brain.router import (  # noqa: F401
    agenda,
    alarmas,
    apps,
    archivos,
    clima,
    contexto,
    dictado,
    documentos,
    equipo,
    listas,
    modos,
    negativas,
    notas,
    nyx,
    ocultar,
    portapapeles,
    privacidad,
    recientes,
    sonido,
    teclado,
    ventanas,
)
from nyx.brain.router.comun import (
    _RAW,
    _RAW_EXACT,
    RULES_BY_NAME,
    Handler,
    Miss,
    Route,
    _clean,
    parse_number,
)
from nyx.brain.router.negativas import IN_GAME_REFUSAL, refusal
from nyx.executor import ToolCall
from nyx.index.service import SystemIndex

__all__ = [
    "IN_GAME_REFUSAL",
    "Miss",
    "Route",
    "parse_number",
    "refusal",
    "route",
    "written_command",
]

# Orden en que se prueban las reglas (gana la primera que encaje). Es el del router antes de
# partirlo en temas (6.25): el orden importa («muéstrame tus ajustes» antes que cambiar de
# ventana, «cierra la pestaña» antes que cerrar una app…).
ORDER = (
    "nyx_settings_close",
    "nyx_settings",
    "city_set",
    "city_live",
    "nyx_change",
    "nyx_where",
    "creator",
    "tepnyx_info",
    "nyx_said",
    "nyx_color",
    "nyx_panel",
    "nyx_size",
    "nyx_update",
    "nyx_restart",
    "ext_howto",
    "volume_up",
    "volume_down",
    "volume_set",
    "volume_said",
    "volume_too_much",
    "unmute",
    "mute",
    "media_pause",
    "media_play",
    "media_next",
    "media_previous",
    "media_said",
    "media_mood",
    "media_go_on",
    "new_tab",
    "close_tab",
    "reopen_tab",
    "reload",
    "incognito",
    "discord_mute",
    "discord_deafen",
    "save",
    "fullscreen",
    "shuffle",
    "repeat",
    "like",
    "two_windows",
    "screenshot",
    "timer",
    "timer_said",
    "alarm",
    "alarm_said",
    "app_reminder",
    "reminder",
    "agenda_read",
    "agenda_add",
    "agenda_move",
    "agenda_delete",
    "agenda_import",
    "list_add",
    "list_read",
    "list_clear",
    "list_remove",
    "list_done",
    "list_lists",
    "task_add",
    "task_read",
    "privacy_now",
    "privacy_recent",
    "recent_open",
    "recent_list",
    "recent_last",
    "mode",
    "undo",
    "close",
    "create_folder",
    "create_folder_named",
    "transfer",
    "transfer_named",
    "delete_folder",
    "delete_folders",
    "delete_files",
    "delete_named",
    "find_in_page",
    "web_search",
    "find",
    "list",
    "files_said",
    "hide_app",
    "show_hidden",
    "window_state",
    "window_side",
    "window_monitor",
    "window_big",
    "window_bigger",
    "window_away",
    "window_back",
    "alarms_list",
    "alarms_state",
    "alarms_cancel",
    "alarms_forget",
    "self",
    "weather",
    "system_info",
    "system_state",
    "dictation",
    "read_selection",
    "read_document",
    "clipboard_read",
    "note_save",
    "clipboard_write",
    "type_text_in_app",
    "type_text",
    "zoom",
    "page_back",
    "brightness_up",
    "brightness_down",
    "brightness_set",
    "brightness_said",
    "radio_toggle",
    "internet_off",
    "system_power",
    "now_playing",
    "now_playing_said",
    "stopwatch",
    "stopwatch_said",
    "audio_output",
    "pending",
    "pending_cancel",
    "focus",
    "focus_back",
    "open_game",
    "open_task",
    "open_with",
    "open_need",
    "settings_need",
    "open",
)

_DOMAIN_DOT = re.compile(r"(?<=\w)\.(?=(?:com|es|org|net|io|ai|tv|dev|app|gg|co|eu|me)\b)", re.I)
_VERBS = r"abre|abrir|pon|cierra|sube|baja|haz|hazme|mueve|crea|escribe|busca|silencia|pausa|cambia|maximiza|minimiza|lanza"
# «abre Spotify y maximízalo»: el verbo puede llevar pronombre pegado.
_SEVERAL_ACTIONS = re.compile(
    rf"\s(?:y|y luego|luego|despues|y despues)\s+(?:{_VERBS})(?:melo|mela|lo|la|los|las|le)?\b"
)


_BACKGROUND = re.compile(
    r"\s+(?:en segundo plano|de fondo|por detras|sin enfocar(?:lo|la)?|sin el foco|"
    r"sin ponerl[oa] delante|sin traerl[oa] al frente|sin cambiar(?:me)? de ventana|"
    r"sin quitarme (?:la ventana|el foco)|minimizad[oa])(?=\s|$)"
)
_OPENERS = {"open_app", "open_url", "open_path", "open_settings"}


_RAW_LEAD = re.compile(
    r"^(?:\s*(?:vale|venga|bueno|pues|a ver|ok|okey|oye|oiga|eh+|ehm|em|mm+|hmm|hey|ey)"
    r"[\s,.…!¡]+)+(?=\w|[¿¡])",
    re.IGNORECASE,
)
_RAW_TRAIL = re.compile(r"(?:[\s,]+(?:por favor|porfa|gracias))+[\s.!]*$", re.IGNORECASE)


def route(text: str, index: SystemIndex) -> Route | Miss | None:
    """Ruta para `text`, `Miss` si el patrón encaja sin destino claro, o None (→ LLM)."""
    # Muletillas y cortesías fuera antes de partir en órdenes y de guardar el texto tal cual:
    # «A ver, abre Spotify y pon el volumen al 30, por favor» (batería de voz, 2026-11-15).
    text = _RAW_TRAIL.sub("", _RAW_LEAD.sub("", text)) or text
    _RAW_EXACT.set(text.strip())
    _RAW.set(text.strip().rstrip(".!¡?¿ "))
    # «marca.com» → «marca punto com»: la limpieza quita los puntos; open_url los recupera.
    clean = _clean(_DOMAIN_DOT.sub(" punto ", text))
    clauses = _clauses(text)
    if len(clauses) > 1:
        return _route_several(clauses, index)
    if _SEVERAL_ACTIONS.search(clean):
        return None  # «abre el bloc de notas y abre una pestaña»: plan de varios pasos (LLM)
    # «abre Discord en segundo plano»: se abre sin quitarle el foco a la ventana actual.
    background = bool(_BACKGROUND.search(clean))
    clean = _BACKGROUND.sub("", clean).strip()
    for _, pattern, handler in _ordered():
        if m := pattern.match(clean):
            result = handler(m, index)
            if result is None:
                continue
            if background and isinstance(result, Route):
                for call in result.calls:
                    if call.name in _OPENERS:
                        call.arguments["focus"] = False
            return result
    return None


# Una orden nueva empieza por un verbo tras una coma o tras «y», «luego», «después».
_CLAUSE_VERBS = rf"(?:{_VERBS}|muestrame|ensename|quita|para|reanuda|ve a|vete a|cambia a|bloquea|apaga|enciende|activa|desactiva)"
_CLAUSE_SPLIT = re.compile(
    rf"\s+(?:y luego|y despues|luego|despues|y)\s+(?=(?:{_CLAUSE_VERBS})"
    r"(?:melo|mela|lo|la|los|las|le)?\b)"
)
_STARTS_WITH_VERB = re.compile(rf"^(?:{_CLAUSE_VERBS})(?:melo|mela|lo|la|los|las|le)?\b")
# Lo que depende del paso anterior (escribir en la app recién abierta…): mejor el LLM, que
# añade las esperas.
_DEPENDENT = {"app_action", "send_hotkey"}


def _clauses(text: str) -> list[str]:
    """«Abre Discord, abre tus ajustes y pon música» → tres órdenes; [texto] si es una sola.

    Solo se parte cuando cada trozo empieza por un verbo, así «Chrome a la izquierda y
    Discord a la derecha» o «Dime, Nyx, ¿qué hora es?» siguen siendo una sola petición.
    """
    parts: list[str] = []
    for piece in re.split(r"[,;]", text):
        cleaned = _clean(piece)
        if cleaned:
            parts += [p for p in _CLAUSE_SPLIT.split(cleaned) if p]
    if len(parts) < 2 or not all(_STARTS_WITH_VERB.match(p) for p in parts):
        return [text]
    return parts


def _route_several(clauses: list[str], index: SystemIndex) -> Route | None:
    """Todas por reglas → un plan; si alguna no, el LLM se encarga de la frase entera."""
    calls: list[ToolCall] = []
    for clause in clauses:
        routed = route(clause, index)
        if not isinstance(routed, Route) or any(c.name in _DEPENDENT for c in routed.calls):
            return None
        calls += routed.calls
    return Route(calls, "several")


def written_command(
    text: str, index: SystemIndex, *, playing: bool = False
) -> list[LLMToolCall] | None:
    """Una orden que el LLM escribió como texto en vez de llamar a la herramienta («pon el
    volumen al 100», tarea 6.21): las llamadas que haría el router, o None si no la entiende.
    Lo que Nyx no hace nunca (negativas fijas) no se convierte en llamada."""
    if refusal(text, index, playing=playing) is not None:
        return None
    routed = route(text, index)
    if not isinstance(routed, Route):
        return None
    return [LLMToolCall(c.name, c.arguments) for c in routed.calls]


def _ordered() -> list[tuple[str, re.Pattern[str], Handler]]:
    """Las reglas en ORDER; las que no estén ahí (las de extensiones, en la 0.7) van al final."""
    known = [(n, *RULES_BY_NAME[n]) for n in ORDER]
    extra = [(n, *v) for n, v in RULES_BY_NAME.items() if n not in ORDER]
    return known + extra
