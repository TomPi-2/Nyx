"""Reglas del equipo: estado, brillo, wifi y bluetooth, apagar y reiniciar."""

from __future__ import annotations

import re

from nyx.brain.router.comun import (
    _NUM,
    Route,
    _call,
    parse_number,
    rule,
)
from nyx.index.service import SystemIndex

# --- estado del PC (6.09) ---

_PC_TAIL = r"(?:\s+(?:en\s+|de\s+|del\s+)?(?:el\s+|mi\s+|la\s+)?(?:pc|ordenador|equipo|portatil|sistema))?(?:\s+ahora(?:\s+mismo)?)?"


@rule(
    "system_info",
    r"^(?:(?:dime|mirame|consulta)\s+)?"
    r"(?:"
    r"(?P<top>(?:que|cual\s+es\s+el)\s+(?:(?P<top_p>proceso|programa|aplicacion|app)\s+(?:que\s+mas\s+)?)?"
    r"(?:(?:(?:esta|va)\s+)?(?:consume|consumiendo|usa|usando|gasta|gastando|chupa|chupando)\s+mas(?:\s+(?:cpu|procesador|ram|memoria|recursos))?|"
    r"(?:cpu|procesador|ram|memoria|recursos)\s+(?:(?:esta|va)\s+)?(?:consume|consumiendo|usa|usando|gasta|gastando|chupa|chupando)))"
    r"|(?P<battery>cuanta\s+bateria\s+(?:me\s+)?(?:queda|tengo|tiene|hay)|"
    r"(?:que\s+(?:porcentaje|nivel)\s+de\s+|a\s+cuanto\s+esta\s+la\s+|como\s+(?:va|esta)\s+la\s+)bateria|"
    r"esta\s+(?:enchufado|cargando))"
    r"|(?P<cpu>cuanta\s+cpu\s+(?:uso|estoy\s+usando|usa|consume|queda)|"
    r"(?:cual\s+es\s+el\s+|que\s+)uso\s+(?:de\s+(?:la\s+)?cpu|del\s+procesador)(?:\s+tengo|\s+hay)?|"
    r"(?:a\s+cuanto\s+(?:esta|va)|como\s+(?:esta|va))\s+(?:la\s+cpu|el\s+procesador)|"
    r"que\s+porcentaje\s+de\s+(?:cpu|procesador)\s+(?:uso|estoy\s+usando|hay))"
    r"|(?P<ram>cuanta\s+(?:memoria\s+)?ram\s+(?:uso|estoy\s+usando|tengo|me\s+queda|queda|hay(?:\s+libre)?|consume)|"
    r"cuanta\s+memoria\s+(?:uso|estoy\s+usando|me\s+queda|queda\s+libre|tengo\s+libre)|"
    r"(?:a\s+cuanto\s+(?:esta|va)|como\s+(?:esta|va)|cual\s+es\s+el\s+uso\s+de)\s+la\s+(?:memoria\s+)?ram)"
    r"|(?P<disk>cuanto\s+(?:espacio|disco|almacenamiento)(?:\s+libre)?\s+(?:me\s+)?(?:queda|tengo|hay)"
    r"(?:\s+libre)?(?:\s+en\s+(?:el\s+)?(?:disco(?:\s+duro)?|c))?|"
    r"espacio\s+libre(?:\s+en\s+(?:el\s+)?disco(?:\s+duro)?)?)"
    r")"
    rf"{_PC_TAIL}$",
)
def _system_info(m: re.Match[str], __: SystemIndex) -> Route | None:
    for kind in ("top", "battery", "cpu", "ram", "disk"):
        if m.group(kind):
            if (
                kind == "top"
                and not m.group("top_p")
                and not re.search(r"\b(?:cpu|procesador|ram|memoria|recursos)\b", m.group("top"))
            ):
                return None
            return _call("system_info", "system_info", what=kind)
    return None


_DEVICE = r"(?:el\s+|mi\s+)?(?:portatil|pc|ordenador|equipo)"
_PROGRAM = r"(?:programa|proceso|aplicacion|app)"
_EATS = r"(?:gastando|consumiendo|usando|chupando|comiendo)(?:se)?"


@rule(
    "system_state",
    # 6.25: preguntas por el estado dichas de otra forma («¿tengo el portátil enchufado?»,
    # «¿me queda sitio para instalar…?», «¿por qué va tan lento el PC?»).
    rf"^(?P<battery>(?:tengo|esta)\s+{_DEVICE}\s+(?:enchufado|cargando|conectado)"
    r"(?:\s+a\s+la\s+(?:corriente|luz))?"
    r"|(?:me\s+)?queda\s+(?:mucha\s+|poca\s+|suficiente\s+)?bateria(?:\s+para\s+.+)?"
    r"|(?:que\s+tal|como)\s+(?:voy|ando|estoy|vamos)\s+de\s+bateria)$"
    r"|^(?P<ram>cuanta\s+(?:memoria|ram)\s+(?:me\s+)?queda(?:\s+libre)?)$"
    r"|^(?P<disk>(?:me\s+)?(?:queda|hay|tengo)\s+(?:sitio|espacio)(?:\s+libre)?"
    r"(?:\s+(?:en\s+(?:el\s+)?disco(?:\s+duro)?|para\s+.+))?"
    r"|cuanto\s+(?:sitio|espacio)\s+(?:libre\s+)?(?:me\s+)?(?:queda|tengo|hay)(?:\s+libre)?)$"
    rf"|^(?P<top>(?:que|cual\s+de\s+mis)\s+(?:{_PROGRAM}(?:s|es)?\s+)?(?:esta|va)\s+{_EATS}\s+"
    r"(?:mas|tanta|tanto|toda\s+la)\s+(?:memoria|ram|cpu|procesador|recursos)"
    rf"|{_DEVICE}\s+(?:va|esta)\s+(?:muy\s+)?(?:cargado|lento|lentisimo|saturado|a\s+tope)"
    rf"|por\s+que\s+(?:va|esta)\s+(?:tan\s+)?(?:lento|cargado)\s+{_DEVICE}"
    rf"|por\s+que\s+{_DEVICE}\s+va\s+tan\s+lento)$",
)
def _system_state(m: re.Match[str], __: SystemIndex) -> Route | None:
    for kind in ("battery", "ram", "disk", "top"):
        if m.group(kind):
            return _call("system_state", "system_info", what=kind)
    return None


# --- brillo, energía, Wi-Fi y Bluetooth (6.11) ---

_BRIGHTNESS_TAIL = (
    rf"(?P<much0>\s+mucho)?(?:\s+un poco)?\s+(?:el\s+)?brillo(?:\s+de\s+(?:la\s+)?pantalla)?"
    rf"(?:\s+(?:a|al|hasta(?:\s+el)?)\s+{_NUM}(?:\s*%|\s+por ciento)?)?"
    r"(?P<much>\s+mucho)?(?:\s+un poco)?$"
)


def _brightness(rule_name: str, m: re.Match[str], step: int) -> Route | None:
    if m.group("n"):
        level = parse_number(m.group("n"))
        if level is None or level > 100:
            return None
        return _call(rule_name, "set_brightness", level=level)
    much = bool(m.group("much") or m.group("much0"))
    return _call(rule_name, "set_brightness", change=step * (2 if much else 1))


@rule("brightness_up", rf"^(?:sube|subir|subeme|aumenta){_BRIGHTNESS_TAIL}")
def _brightness_up(m: re.Match[str], __: SystemIndex) -> Route | None:
    return _brightness("brightness_up", m, 20)


@rule("brightness_down", rf"^(?:baja|bajar|bajame|reduce){_BRIGHTNESS_TAIL}")
def _brightness_down(m: re.Match[str], __: SystemIndex) -> Route | None:
    return _brightness("brightness_down", m, -20)


@rule(
    "brightness_set",
    rf"^(?:(?:pon|deja|ajusta|cambia)\s+(?:el\s+)?)?brillo(?:\s+de\s+(?:la\s+)?pantalla)?\s+(?:a|al|en)?\s*(?:(?P<max>maximo|tope)|(?P<min>minimo)|{_NUM})(?:\s*%|\s+por ciento)?$",
)
def _brightness_set(m: re.Match[str], __: SystemIndex) -> Route | None:
    if m.group("max"):
        return _call("brightness_set", "set_brightness", level=100)
    if m.group("min"):
        return _call("brightness_set", "set_brightness", level=10)
    level = parse_number(m.group("n"))
    if level is None or level > 100:
        return None
    return _call("brightness_set", "set_brightness", level=level)


@rule(
    "radio_toggle",
    r"^(?:(?P<on>activa(?:r)?|enciende|encender|conecta(?:r)?|pon(?:er)?)|"
    r"(?P<off>desactiva(?:r)?|apaga(?:r)?|quita(?:r)?|desconecta(?:r)?)|"
    r"(?P<toggle>alterna(?:r)?|cambia(?:r)?))\s+(?:el\s+|la\s+)?(?P<kind>wi\s*fi|bluetooth)$",
)
def _radio_toggle(m: re.Match[str], __: SystemIndex) -> Route:
    tool = "toggle_wifi" if m.group("kind").startswith("wi") else "toggle_bluetooth"
    enabled = True if m.group("on") else (False if m.group("off") else None)
    return _call("radio_toggle", tool, enabled=enabled)


_PC_TARGET = r"(?:el\s+|mi\s+|la\s+)?(?:pc|ordenador|equipo|portatil|sistema|windows)"


@rule(
    "system_power",
    rf"^(?:(?P<lock>bloquea(?:r)?\s+(?:{_PC_TARGET}|(?:la\s+)?(?:pantalla|sesion)))"
    rf"|(?P<sleep>suspende(?:r)?\s+{_PC_TARGET}|pon(?:er)?\s+{_PC_TARGET}\s+(?:en\s+suspension|a\s+dormir))"
    rf"|(?P<restart>reinicia(?:r)?\s+{_PC_TARGET})"
    rf"|(?P<shutdown>apaga(?:r)?\s+{_PC_TARGET}))$",
)
def _system_power(m: re.Match[str], __: SystemIndex) -> Route | None:
    for action in ("lock", "sleep", "restart", "shutdown"):
        if m.group(action):
            return _call("system_power", "system_power", action=action)
    return None
