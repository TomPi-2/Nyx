"""Reglas del calendario (8.02): lo frecuente y seguro, sin pasar por el modelo.

«¿Qué tengo mañana?», «¿qué tengo esta semana?», «tengo dentista el jueves a las 5», «apunta
una reunión con Ana mañana a las 10», «tengo clase de inglés todos los martes a las 6», «mueve
la cita del dentista al viernes», «cancela la reunión con Ana», «importa el calendario de
Descargas». Lo que no encaja (fechas raras, «dentro de dos semanas») va al modelo.

Una cita «a las 5» sin decir de la mañana o de la tarde es a las 17:00: de 1 a 7, por la
tarde (nadie va al dentista a las 5 de la madrugada); las alarmas, en cambio, a las 5:00.
"""

from __future__ import annotations

import re
from typing import Any, cast

from nyx.brain.router.alarmas import _CLOCK, _clock_time
from nyx.brain.router.comun import Route, _call, _original, parse_number, rule
from nyx.index.service import SystemIndex

_WEEKDAYS = {
    "lunes": "monday",
    "martes": "tuesday",
    "miercoles": "wednesday",
    "jueves": "thursday",
    "viernes": "friday",
    "sabado": "saturday",
    "domingo": "sunday",
}
_WD = "|".join(_WEEKDAYS)
# Cuándo: «hoy», «mañana», «pasado mañana», «el (próximo) jueves», «el día 20», «todos los
# martes» / «cada martes» (cada semana).
# («de la mañana» es la hora, no el día.)
_DAY = (
    rf"(?:(?<!de la )(?P<d>hoy|manana|pasado manana)"
    rf"|(?:el\s+)?(?:proximo\s+)?(?P<wd>{_WD})(?:\s+que\s+viene)?"
    rf"|el\s+dia\s+(?P<md>\d{{1,2}}|[a-z]+)|(?:todos\s+los|cada)\s+(?P<every>{_WD})(?:es)?)"
)
# Lo que se apunta no acaba en el artículo del día («dentista el | jueves»).
_NO_ART = r"(?<!\bel)(?<!\bla)(?<!\bpara)"
_AT = rf"(?:a\s+)?las?\s+{_CLOCK}"
# Lo que se apunta: con cita o reunión, o lo que se suele tener («tengo dentista…»).
_KINDS = (
    r"cita|reunion|medico|dentista|clase|examen|entrevista|partido|cena|comida|"
    r"cumpleanos|vuelo|tren|consulta|revision|peluqueria|entreno|ensayo"
)


def _day_args(m: _Groups) -> dict[str, object] | None:
    """Los argumentos de `calendar` para el día de la frase."""
    if d := m.group("d"):
        return {"day": {"hoy": "today", "manana": "tomorrow"}.get(d, "after_tomorrow")}
    if wd := m.group("wd"):
        return {"weekday": _WEEKDAYS[wd]}
    if every := m.group("every"):
        return {"weekday": _WEEKDAYS[every], "repeat": "weekly"}
    if md := m.group("md"):
        n = parse_number(md)
        return {"month_day": n} if n and 1 <= n <= 31 else None
    return None


def _time_arg(m: _Groups) -> str | None:
    if m.group("h") is None:
        return None
    when = _clock_time(cast(Any, m))  # misma forma que un Match: solo usa `group`
    if when is None:
        return None
    hour, minute = when.split(":")
    if m.group("part") is None and 1 <= int(hour) <= 7:
        hour = str(int(hour) + 12)  # «a las 5» → 17:00
    return f"{int(hour):02d}:{minute}"


def _title(kind: str | None, what: str | None) -> str:
    text = " ".join(x for x in (kind, what) if x).strip()
    text = _original(text)
    return text[0].upper() + text[1:] if text else text


# --- ver ---------------------------------------------------------------------------------


@rule(
    "agenda_read",
    # «¿qué tengo mañana?», «¿tengo algo el jueves?», «¿qué citas tengo esta semana?»
    rf"^(?:que\s+(?:tengo|hay)|tengo\s+algo|que\s+citas\s+tengo)\s+(?:para\s+)?"
    rf"(?:{_DAY}|(?P<week>esta\s+semana|la\s+semana))"
    # «¿tengo algo el sábado por la tarde?»: se lee el día entero.
    rf"(?:\s+(?:por\s+la|a\s+la|de)\s+(?:manana|tarde|noche|mediodia))?$"
    # «¿qué tengo en el calendario?», «enséñame mi agenda de mañana»
    rf"|^(?:que\s+(?:tengo|hay)\s+en\s+(?:el\s+|mi\s+|la\s+)?(?:calendario|agenda)"
    rf"|(?:ensename|muestrame|dime|leeme|abre(?:me)?)\s+(?:mi|la|el)\s+(?:agenda|calendario))"
    rf"(?:\s+(?:de|para)\s+(?:{_DAY.replace('(?P<', '(?P<r_')}|(?P<r_week>esta\s+semana)))?$",
)
def _agenda_read(m: re.Match[str], _: SystemIndex) -> Route | None:
    groups = {k.removeprefix("r_"): v for k, v in m.groupdict().items() if v is not None}
    if groups.get("week"):
        return _call("agenda_read", "calendar", action="read", week=True)
    fake = _Groups(groups)
    args = _day_args(fake) if any(k in groups for k in ("d", "wd", "md", "every")) else {}
    if args is None:
        return None
    args.pop("repeat", None)
    return _call("agenda_read", "calendar", action="read", **args)


# --- apuntar -----------------------------------------------------------------------------


@rule(
    "agenda_add",
    # «tengo dentista el jueves a las 5», «tengo una reunión con Ana mañana a las 10»
    rf"^tengo\s+(?:una?\s+|la\s+|el\s+)?(?P<kind>{_KINDS})(?:\s+(?P<what>.+?){_NO_ART})?"
    rf"\s+(?:para\s+)?{_DAY}(?:\s+{_AT})?$"
    # «apunta una cita con el dentista el jueves a las 5»
    rf"|^(?:apunta|anota|pon|anade|mete|guarda)(?:me)?\s+(?:en\s+(?:el\s+|mi\s+)?(?:calendario|agenda)\s+)?"
    rf"(?:una?\s+|la\s+|el\s+)?(?P<kind2>{_KINDS})(?:\s+(?P<what2>.+?){_NO_ART})?\s+(?:para\s+)?"
    + _DAY.replace("(?P<", "(?P<b_")
    + r"(?:\s+"
    + _AT.replace("(?P<", "(?P<b_")
    + r")?$"
    # «apunta en el calendario la boda de Luis el sábado»
    + r"|^(?:apunta|anota|pon|anade|mete|guarda)(?:me)?\s+en\s+(?:el\s+|mi\s+)?(?:calendario|agenda)\s+"
    r"(?P<what3>.+?)"
    + _NO_ART
    + r"\s+"
    + _DAY.replace("(?P<", "(?P<c_")
    + r"(?:\s+"
    + _AT.replace("(?P<", "(?P<c_")
    + r")?$",
)
def _agenda_add(m: re.Match[str], _: SystemIndex) -> Route | None:
    for prefix, kind, what in (
        ("", "kind", "what"),
        ("b_", "kind2", "what2"),
        ("c_", None, "what3"),
    ):
        if m.group(what) is None and (kind is None or m.group(kind) is None):
            continue
        groups = _Groups(
            {
                k.removeprefix(prefix): v
                for k, v in m.groupdict().items()
                if v is not None and (k.startswith(prefix) if prefix else "_" not in k)
            }
        )
        args = _day_args(groups)
        if args is None:
            return None
        title = _title(m.group(kind) if kind else None, m.group(what))
        if not title or re.search(r"\b(?:que|alarma|temporizador|lista)\b", title.lower()):
            return None
        return _call(
            "agenda_add", "calendar", action="add", title=title, time=_time_arg(groups), **args
        )
    return None


# --- mover y borrar ------------------------------------------------------------------------


@rule(
    "agenda_move",
    rf"^(?:mueve|mueveme|cambia|cambiame|pasa|pasame|aplaza|retrasa|adelanta)\s+"
    rf"(?:la\s+|el\s+|mi\s+)?(?:(?P<kind>cita|reunion)\s+(?:del?|con|de\s+la)\s+)?(?P<what>.+?)\s+"
    rf"(?:al|a\s+el|para\s+el|a|para)\s+(?:{_DAY}(?:\s+{_AT})?|{_AT.replace('(?P<', '(?P<t_')})$",
)
def _agenda_move(m: re.Match[str], _: SystemIndex) -> Route | None:
    what = m.group("what")
    # «cambia el volumen a 30», «pasa la canción»: solo citas (cita/reunión o lo que se tiene).
    if m.group("kind") is None and not re.match(rf"(?:{_KINDS})\b", what):
        return None
    groups = {k: v for k, v in m.groupdict().items() if v is not None}
    time_groups = _Groups(
        {k.removeprefix("t_"): v for k, v in groups.items() if k.startswith("t_")}
    )
    args = _day_args(_Groups(groups)) if any(k in groups for k in ("d", "wd", "md")) else {}
    if args is None:
        return None
    args.pop("repeat", None)
    when = _time_arg(time_groups) if "t_h" in groups else _time_arg(_Groups(groups))
    return _call("agenda_move", "calendar", action="move", title=_original(what), time=when, **args)


@rule(
    "agenda_delete",
    r"^(?:cancela|cancelame|borra|borrame|quita|quitame|elimina|anula)\s+(?:la|mi)\s+"
    r"(?:cita|reunion)\s+(?:del?|con|de\s+la|de\s+los)\s+(?P<what>.+?)$",
)
def _agenda_delete(m: re.Match[str], _: SystemIndex) -> Route:
    what = re.sub(rf"\s+(?:del|de este|de)\s+(?:{_WD}|manana|hoy)$", "", m.group("what"))
    return _call("agenda_delete", "calendar", action="delete", title=_original(what))


@rule(
    "agenda_import",
    r"^importa(?:me)?\s+(?:el\s+|mi\s+|un\s+)?(?:calendario|archivo\s+ics|ics)"
    r"(?:\s+(?:de|que\s+hay\s+en|que\s+tengo\s+en)\s+(?:la\s+carpeta\s+de\s+)?descargas)?$",
)
def _agenda_import(_: re.Match[str], __: SystemIndex) -> Route:
    return _call("agenda_import", "calendar", action="import")


class _Groups:
    """Grupos ya elegidos (sin prefijo) con la forma de `re.Match.group`."""

    def __init__(self, groups: dict[str, str]) -> None:
        self._g = groups

    def group(self, name: str) -> str | None:
        return self._g.get(name)
