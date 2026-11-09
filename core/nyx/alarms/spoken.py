"""Cómo se muestran y se dicen las alarmas y los temporizadores."""

from __future__ import annotations

from datetime import datetime, timedelta

from nyx.alarms.store import Alarm


def short_duration(seconds: int) -> str:
    """«5 min», «1 h 30 min», «45 s» (para la burbuja)."""
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    parts = [f"{h} h" if h else "", f"{m} min" if m else "", f"{s} s" if s else ""]
    return " ".join(p for p in parts if p) or "0 s"


def spoken_duration(seconds: int) -> str:
    """«5 minutos», «1 hora y 30 minutos» (para la voz)."""

    def unit(n: int, one: str, many: str) -> str:
        return f"{n} {one if n == 1 else many}" if n else ""

    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    parts = [
        p
        for p in (
            unit(h, "hora", "horas"),
            unit(m, "minuto", "minutos"),
            unit(s, "segundo", "segundos"),
        )
        if p
    ]
    return " y ".join([", ".join(parts[:-1]), parts[-1]]) if len(parts) > 1 else parts[0]


def day_label(due: datetime, now: datetime) -> str:
    days = (due.date() - now.date()).days
    if days == 0:
        return "hoy"
    if days == 1:
        return "mañana"
    return due.strftime("%d/%m")


def next_occurrence(hour: int, minute: int, now: datetime, *, tomorrow: bool = False) -> datetime:
    """Hoy a esa hora, o mañana si ya pasó (SPEC sección 7)."""
    due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if tomorrow or due <= now:
        due += timedelta(days=1)
    return due


def fired_text(alarm: Alarm) -> tuple[str, str, str]:
    """(dato de la burbuja, línea secundaria, frase hablada) cuando suena."""
    at = datetime.fromtimestamp(alarm.due).strftime("%H:%M")
    if alarm.kind == "timer":
        length = spoken_duration(alarm.duration_s or 0)
        if alarm.label:
            return (
                alarm.label,
                f"temporizador de {short_duration(alarm.duration_s or 0)}",
                (f"Te recuerdo: {alarm.label}."),
            )
        return (
            "Tiempo",
            f"temporizador de {short_duration(alarm.duration_s or 0)}",
            (f"Se acabó el temporizador de {length}."),
        )
    if alarm.label:
        return alarm.label, f"recordatorio · {at}", f"Te recuerdo: {alarm.label}."
    return at, "alarma", f"Son las {at}."


def missed_text(alarms: tuple[Alarm, ...] | list[Alarm]) -> tuple[str, str]:
    """Aviso único al arrancar: «Mientras estaba apagado» + la primera (y cuántas más)."""
    first = alarms[0]
    at = datetime.fromtimestamp(first.due).strftime("%H:%M")
    what = {"timer": "temporizador", "alarm": "recordatorio" if first.label else "alarma"}[
        first.kind
    ]
    line = f"{what} de las {at}" + (f": {first.label}" if first.label else "")
    if len(alarms) > 1:
        line += f" (y {len(alarms) - 1} más)"
    return "Mientras estaba apagado", line
