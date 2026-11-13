"""Reglas de alarmas, temporizadores, recordatorios y cronómetro."""

from __future__ import annotations

import re

from nyx.brain.router.comun import (
    _N,
    Route,
    _call,
    _original,
    parse_number,
    rule,
)
from nyx.index.service import SystemIndex

# --- alarmas y temporizadores (bloque 3c; los recordatorios con texto van por el LLM) ---

_AMOUNT = rf"(?:(?P<n>{_N})\s+(?P<unit>segundos?|minutos?|horas?)(?P<half>\s+y\s+medi[oa])?|(?P<special>media hora|un cuarto de hora|tres cuartos de hora|hora y media))"
_UNIT_S = {"segundo": 1, "minuto": 60, "hora": 3600}
_SPECIAL_S = {
    "media hora": 1800,
    "un cuarto de hora": 900,
    "tres cuartos de hora": 2700,
    "hora y media": 5400,
}


def _seconds(m: re.Match[str]) -> int | None:
    if m.group("special"):
        return _SPECIAL_S[m.group("special")]
    n = parse_number(m.group("n"))
    if n is None:
        return None
    unit = _UNIT_S[m.group("unit").rstrip("s")]
    return n * unit + (unit // 2 if m.group("half") else 0)


@rule(
    "timer",
    rf"^(?:(?:(?:pon(?:me)?|crea|activa)\s+)?(?:un\s+)?temporizador\s+(?:de\s+)?"
    rf"|(?:avisame|despiertame|llamame|cuenta)\s+(?:en\s+)?"
    # «pon una alarma que suene en 10 segundos» es un temporizador (el LLM la ponía a las 00:10)
    rf"|(?:(?:pon(?:me)?|crea|activa)\s+)?(?:una\s+)?alarma\s+(?:que\s+suene\s+)?"
    rf"(?:en|dentro\s+de)\s+){_AMOUNT}$",
)
def _timer(m: re.Match[str], _: SystemIndex) -> Route | None:
    total = _seconds(m)
    if total is None or not 0 < total <= 24 * 3600:
        return None
    h, rest = divmod(total, 3600)
    mins, s = divmod(rest, 60)
    return _call("timer", "set_timer", hours=h or None, minutes=mins or None, seconds=s or None)


# «a las 7», «a las 7 30» (los dos puntos se quitan al normalizar), «a las 7 y media»,
# «a las 8 menos cuarto», «a las 5 de la tarde».
_CLOCK = rf"(?P<h>{_N})(?:\s+(?P<m>\d{{2}}))?(?:\s+y\s+(?P<frac>media|cuarto)|\s+(?P<minus>menos cuarto))?(?:\s+en punto)?(?:\s+(?:de la\s+|del\s+)?(?P<part>manana|tarde|noche|madrugada|mediodia))?"


def _clock_time(m: re.Match[str] | _Renamed) -> str | None:
    raw_h = m.group("h")
    h = parse_number(raw_h) if raw_h else None
    if h is None or h > 23:
        return None
    minute = int(m.group("m") or 0)
    if m.group("frac"):
        minute = 30 if m.group("frac") == "media" else 15
    if m.group("minus"):
        h, minute = (h - 1) % 24, 45
    part = m.group("part")
    if part in ("tarde", "noche") and h < 12:
        h += 12
    if part == "mediodia" and h < 5:  # «a la una del mediodía»
        h += 12
    if minute > 59:
        return None
    return f"{h:02d}:{minute:02d}"


_REPEAT_BODY = (
    r"(?:todos\s+los\s+)?(?:dias\s+)?laborables|"
    r"(?:de\s+)?lunes\s+a\s+viernes|"
    r"entre\s+semana|"
    r"(?:todos\s+)?los\s+fines\s+de\s+semana|"
    r"fines\s+de\s+semana|"
    r"todos\s+los\s+dias|"
    r"cada\s+dia|"
    r"a\s+diario|"
    r"diariamente"
)


def _parse_repeat(raw: str | None) -> str | None:
    if not raw:
        return None
    if "laborable" in raw or "lunes" in raw or "entre semana" in raw:
        return "weekdays"
    if "fin" in raw:
        return "weekends"
    return "daily"


@rule(
    "alarm",
    rf"^(?:(?:(?:pon(?:me)?|crea|activa)\s+)?(?:una\s+)?alarma\s+(?:para\s+)?|despiertame\s+)"
    rf"(?:(?P<rep1>{_REPEAT_BODY})\s+)?(?:(?P<day>manana|hoy)\s+)?(?:a\s+)?las?\s+{_CLOCK}"
    rf"(?:\s+(?P<rep2>{_REPEAT_BODY}))?$"
    rf"|^(?P<rep3>{_REPEAT_BODY})\s+(?:a\s+)?las?\s+{_CLOCK.replace('(?P<', '(?P<a_')}$",
)
def _alarm(m: re.Match[str], _: SystemIndex) -> Route | None:
    when = _clock_time(m) if m.group("h") is not None else _clock_time(_Renamed(m, "a_"))
    if when is None:
        return None
    tomorrow = m.group("day") == "manana"
    repeat = _parse_repeat(m.group("rep1") or m.group("rep2") or m.group("rep3"))
    return _call(
        "alarm", "set_alarm", time=when, day="tomorrow" if tomorrow else None, repeat=repeat
    )


_REMIND = r"(?:recuerdame|recordarme|avisame(?:\s+(?:para|de))?)"


@rule(
    "reminder",
    rf"^{_REMIND}\s+(?:(?P<rep1>{_REPEAT_BODY})\s+)?(?:(?P<day>manana|hoy)\s+)?(?:a\s+)?las?\s+{_CLOCK}\s+"
    rf"(?:(?P<rep2>{_REPEAT_BODY})\s+)?(?:que\s+|de\s+|para\s+)?(?P<label>.+)$"
    rf"|^{_REMIND}\s+(?:que\s+|de\s+)?(?P<label2>.+?)(?:\s+(?P<rep3>{_REPEAT_BODY}))?\s+"
    rf"(?:(?P<day2>manana|hoy)\s+)?a\s+las?\s+"
    + _CLOCK.replace("(?P<", "(?P<r_")
    + rf"(?:\s+(?P<rep4>{_REPEAT_BODY}))?$",
)
def _reminder(m: re.Match[str], _: SystemIndex) -> Route | None:
    """«Recuérdame a las 6 de la tarde llamar a mamá» y «recuérdame llamar a mamá a las 6».

    Con muchas herramientas, el 7B a veces escribía la orden como texto en vez de hacerla
    (tarea 6.03): lo frecuente y claro va por reglas."""
    first = m.group("label") is not None
    when = _clock_time(m) if first else _clock_time(_Renamed(m))
    if when is None:
        return None
    label = _original(m.group("label") if first else m.group("label2"))
    day = m.group("day") if first else m.group("day2")
    repeat = _parse_repeat(
        (m.group("rep1") or m.group("rep2")) if first else (m.group("rep3") or m.group("rep4"))
    )
    return _call(
        "reminder",
        "set_alarm",
        time=when,
        day="tomorrow" if day == "manana" else None,
        label=label,
        repeat=repeat,
    )


class _Renamed:
    """Los grupos del reloj con prefijo (`r_h`, `a_h`…) con los nombres de `_clock_time`."""

    def __init__(self, m: re.Match[str], prefix: str = "r_") -> None:
        self._m = m
        self._prefix = prefix

    def group(self, name: str) -> str | None:
        return self._m.group(f"{self._prefix}{name}")


# --- alarmas: ver cuáles hay (6.03; antes el LLM decía «no tienes» sin mirar) ---


@rule(
    "alarms_list",
    r"^(?:que|cuales|cuantas) (?:alarmas|temporizadores|recordatorios) (?:tengo|hay)(?: puest[oa]s)?$"
    r"|^tengo (?:alguna |algun )?(?:alarmas?|temporizador(?:es)?|recordatorios?)(?: puest[oa]s?)?"
    r"(?: (?:para )?(?:hoy|manana|esta (?:tarde|noche)))?$"
    r"|^cuanto (?:le )?queda (?:al|a la|para la|para el) (?:temporizador|alarma|recordatorio)$",
)
def _alarms_list(_: re.Match[str], __: SystemIndex) -> Route:
    return _call("alarms_list", "list_alarms")


_TELL_ME = r"(?:(?:me\s+)?(?:puedes|podrias)\s+decir(?:me)?\s+|dime\s+)?"


@rule(
    "alarms_state",
    # 6.25: «¿a qué hora sonaba la alarma de mañana?», «¿cuánto falta para que suene el
    # temporizador?», «¿tengo algo programado?» (antes el 7B contestaba sin mirar).
    rf"^{_TELL_ME}a\s+que\s+hora\s+(?:sonaba|suena|sonara|era|es|tengo|tenia|puse)\s+"
    r"(?:la|mi)\s+alarma(?:\s+(?:de|para)\s+(?:hoy|manana|esta\s+(?:tarde|noche)))?$"
    rf"|^{_TELL_ME}cuanto\s+(?:le\s+)?(?:falta|queda)\s+(?:para\s+(?:que\s+suene\s+)?)?"
    r"(?:el|la|mi|al|a\s+la)\s+(?:temporizador|alarma|recordatorio)(?:\s+de\s+[a-z ]+)?$"
    r"|^tengo\s+algo\s+(?:programado|puesto)(?:\s+(?:para\s+)?(?:hoy|manana))?$",
)
def _alarms_state(_: re.Match[str], __: SystemIndex) -> Route:
    return _call("alarms_state", "list_alarms")


@rule(
    "alarms_cancel",
    r"^(?:cancela|quita|quitame|borra|elimina|anula)\s+(?:el|la|los|las|mi|mis)\s+"
    r"(?P<what>(?:temporizador|alarma|recordatorio)(?:es|s)?(?:\s+.+)?)$",
)
def _alarms_cancel(m: re.Match[str], __: SystemIndex) -> Route:
    """«Cancela el temporizador», «quita la alarma de las 7», «borra todas las alarmas»."""
    what = m.group("what")
    plural = re.match(r"(?:temporizador|alarma|recordatorio)(?:es|s)\b", what)
    which = "todas" if plural and not re.search(r"\bde\b", what) else what
    which = re.sub(r"^(?:alarma|recordatorio)\s+(?:de\s+)?(?:las\s+)?", "", which)
    return _call("alarms_cancel", "cancel_alarm", which=which)


_CRONO = r"(?:el\s+|un\s+|mi\s+)?(?:cronometro|crono)"


@rule(
    "stopwatch",
    rf"^(?P<start>(?:pon(?:me)?|empieza|empecemos|inicia|iniciemos|arranca|arranquemos|comienza|comencemos|activa|abre(?:me)?|dale\s+al?)\s+{_CRONO}|cronometro)$"
    rf"|^(?P<stop>(?:para|parame|deten|pausa|termina|corta)\s+{_CRONO})$"
    rf"|^(?P<status>(?:dime\s+)?(?:cuanto(?:s\s+(?:segundos|minutos|horas))?(?:\s+tiempo)?\s+lleva(?:\s+{_CRONO})?"
    rf"|(?:como\s+va|que\s+(?:tiempo\s+)?marca|estado\s+de(?:l)?)\s+(?:el\s+|mi\s+)?(?:cronometro|crono)))$",
)
def _stopwatch(m: re.Match[str], __: SystemIndex) -> Route | None:
    for action in ("start", "stop", "status"):
        if m.group(action):
            return _call("stopwatch", "stopwatch", action=action)
    return None


@rule(
    "stopwatch_said",
    # 6.25: «cronometra cuánto tardo», «empieza a contar el tiempo», «para de contar»,
    # «¿cuánto marca el crono?». «Deja de contar chistes» no: solo «contar» a secas o el tiempo.
    r"^(?P<start>cronometra(?:me)?(?:\s+(?:cuanto|lo\s+que)\s+.+)?"
    r"|(?:empieza|ponte|comienza)\s+a\s+contar(?:\s+el\s+tiempo)?)$"
    r"|^(?P<stop>(?:ya\s+(?:he\s+terminado|he\s+acabado|esta)\s+)?"
    r"(?:para|deja|termina)\s+de\s+(?:contar(?:\s+el\s+tiempo)?|cronometrar))$"
    rf"|^(?P<status>cuanto\s+(?:marca|lleva|va)\s+{_CRONO})$",
)
def _stopwatch_said(m: re.Match[str], __: SystemIndex) -> Route | None:
    for action in ("start", "stop", "status"):
        if m.group(action):
            return _call("stopwatch_said", "stopwatch", action=action)
    return None
