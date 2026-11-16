"""Calendario local de Nyx (tarea 8.02): repeticiones, avisos e importar un `.ics`.

Las citas viven en `organizer.db` (store.py). Aquí está lo que no es guardar:

- **Repeticiones sencillas**: cada semana, cada mes (el mismo día; si el mes no lo tiene, ese
  mes no hay) o cada año. Nada de «el segundo martes»: eso, con las cuentas (1.3).
- **Avisos**: con las alarmas de Nyx, `remind` minutos antes. Las alarmas solo saben repetirse
  a diario, así que se ponen las de los próximos días (`schedule_reminders`) y se renuevan cada
  hora; cada vez se avisa una sola vez (`event_alarms`).
- **Importar**: un `.ics` que elige el usuario (Google, Outlook, Apple lo exportan), con
  `icalendar` (BSD-2). Solo lo de los últimos 30 días en adelante y lo que se repite; lo ya
  importado (mismo UID) no se repite. Sin aviso salvo que el archivo traiga uno.
"""

from __future__ import annotations

import calendar as pycal
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nyx.index.aliases import normalize
from nyx.organizer.store import Event, OrganizerStore

if TYPE_CHECKING:
    from nyx.alarms.scheduler import AlarmScheduler

log = logging.getLogger(__name__)

REPEATS = ("none", "weekly", "monthly", "yearly")
#: Cuánto por delante se ponen los avisos (se renuevan cada hora).
AHEAD = timedelta(days=7)
#: Lo que se importa de un .ics: tamaño del archivo, citas y desde cuándo.
MAX_ICS_BYTES = 5 * 1024 * 1024
MAX_IMPORT = 2000
IMPORT_SINCE = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class Occurrence:
    event: Event
    start: datetime

    @property
    def end(self) -> datetime:
        if self.event.all_day:
            return self.start + timedelta(days=1)
        return self.start + timedelta(minutes=self.event.minutes)


def _add_months(start: datetime, months: int) -> datetime | None:
    """El mismo día `months` meses después, o None si ese mes no lo tiene (31 de abril)."""
    total = start.month - 1 + months
    year, month = start.year + total // 12, total % 12 + 1
    if start.day > pycal.monthrange(year, month)[1]:
        return None
    return start.replace(year=year, month=month)


def occurrences(event: Event, since: datetime, until: datetime) -> list[datetime]:
    """Cuándo empieza cada vez de la cita que toca [since, until)."""
    first = datetime.fromtimestamp(event.start)
    length = timedelta(days=1) if event.all_day else timedelta(minutes=event.minutes)
    out: list[datetime] = []
    if event.repeat == "weekly":
        # Directo a la primera semana que puede tocar el intervalo.
        skip = max(0, (since - length - first).days // 7)
        current = first + timedelta(weeks=skip)
        while current < until and len(out) < 400:
            if current + length > since:
                out.append(current)
            current += timedelta(weeks=1)
        return out
    if event.repeat in ("monthly", "yearly"):
        step = 1 if event.repeat == "monthly" else 12
        months_away = (since.year - first.year) * 12 + since.month - first.month
        n = max(0, (months_away - 1) // step)
        while len(out) < 400:
            moved = _add_months(first, n * step)
            n += 1
            if moved is None:
                if n > 2400:  # un 31 de febrero cada año: nunca llega
                    break
                continue
            if moved >= until:
                break
            if moved + length > since:
                out.append(moved)
        return out
    return [first] if first < until and first + length > since else []


def agenda(store: OrganizerStore, since: datetime, until: datetime) -> list[Occurrence]:
    """Las citas de [since, until), por orden (las de todo el día primero)."""
    found = [
        Occurrence(event, start)
        for event in store.events()
        for start in occurrences(event, since, until)
    ]
    return sorted(found, key=lambda o: (o.start.date(), not o.event.all_day, o.start))


def schedule_reminders(
    store: OrganizerStore, alarms: AlarmScheduler, now: datetime | None = None
) -> int:
    """Pone los avisos de los próximos días que aún no estén puestos. Devuelve cuántos."""
    now = now or datetime.fromtimestamp(alarms.clock())
    added = 0
    for event in store.events():
        if event.remind is None:
            continue
        done = store.event_alarms(event.id)
        for start in occurrences(event, now, now + AHEAD):
            when = start - timedelta(minutes=event.remind)
            if event.all_day:
                when = datetime.combine(start.date(), time(9, 0))  # las de todo el día, a las 9
            if when <= now or start.timestamp() in done:
                continue
            label = event.title if event.all_day else f"{event.title} a las {start:%H:%M}"
            alarm = alarms.add("alarm", when.timestamp(), label=label)
            store.set_event_alarm(event.id, start.timestamp(), alarm.id)
            added += 1
    return added


def cancel_reminders(store: OrganizerStore, alarms: AlarmScheduler | None, event_id: int) -> None:
    """Quita los avisos de una cita (al moverla o borrarla)."""
    for alarm_id in store.clear_event_alarms(event_id):
        if alarms is not None:
            alarms.cancel(alarm_id)


# --- Importar un .ics --------------------------------------------------------------------------


def find_ics(name: str, folders: dict[str, Path]) -> Path | None:
    """El .ics que dice el usuario: una ruta, o por su nombre en Descargas, Documentos y el
    Escritorio; sin nombre, el más reciente de Descargas."""
    if name:
        direct = Path(name)
        if direct.is_absolute() and direct.suffix.lower() == ".ics" and direct.is_file():
            return direct
    wanted = normalize(name.removesuffix(".ics")) if name else ""
    where = ["Descargas"] if not wanted else ["Descargas", "Documentos", "Escritorio"]
    candidates: list[Path] = []
    for folder in where:
        base = folders.get(folder)
        if base is None:
            continue
        try:
            files = [p for p in base.iterdir() if p.suffix.lower() == ".ics" and p.is_file()]
        except OSError:
            continue
        candidates += [p for p in files if not wanted or wanted in normalize(p.stem)]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _local(value: Any) -> tuple[datetime, bool]:
    """(inicio en hora local del PC, ¿todo el día?) de un DTSTART."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone().replace(tzinfo=None)
        return value, False
    if isinstance(value, date):
        return datetime.combine(value, time()), True
    raise ValueError("fecha no válida")


def _repeat(component: Any) -> str | None:
    """La repetición que sabe Nyx, o None si es otra (se importa solo la primera vez)."""
    rule = component.get("RRULE")
    if rule is None:
        return "none"
    freq = (rule.get("FREQ") or [""])[0]
    interval = int((rule.get("INTERVAL") or [1])[0])
    extra = set(rule) - {"FREQ", "INTERVAL", "UNTIL", "COUNT", "WKST"}
    mapped = {"WEEKLY": "weekly", "MONTHLY": "monthly", "YEARLY": "yearly"}.get(freq)
    if mapped is None or interval != 1 or extra:
        return None
    return mapped


def _remind(component: Any) -> int | None:
    """Minutos antes del primer aviso del archivo (VALARM con TRIGGER relativo), si trae."""
    for alarm in component.walk("VALARM"):
        trigger = alarm.get("TRIGGER")
        delta = getattr(trigger, "dt", None)
        if isinstance(delta, timedelta) and delta <= timedelta(0):
            return min(int(-delta.total_seconds() // 60), 7 * 24 * 60)
    return None


def import_ics(path: Path, store: OrganizerStore, now: datetime) -> tuple[list[int], int]:
    """Importa las citas de `path`. Devuelve (ids nuevos, cuántas se han saltado)."""
    from icalendar import Calendar

    if path.stat().st_size > MAX_ICS_BYTES:
        raise ValueError("el archivo es demasiado grande (más de 5 MB)")
    try:
        cal = Calendar.from_ical(path.read_bytes())
    except ValueError as e:
        raise ValueError("no es un calendario .ics válido") from e
    added: list[int] = []
    skipped = 0
    for component in cal.walk("VEVENT"):
        if len(added) >= MAX_IMPORT:
            skipped += 1
            continue
        try:
            title = str(component.get("SUMMARY") or "").strip() or "Cita"
            start, all_day = _local(component.decoded("DTSTART"))
            repeat = _repeat(component) or "none"
            if "DTEND" in component:
                end, _ = _local(component.decoded("DTEND"))
                minutes = max(0, int((end - start).total_seconds() // 60))
            elif "DURATION" in component:
                minutes = int(component.decoded("DURATION").total_seconds() // 60)
            else:
                minutes = 24 * 60 if all_day else 60
        except (KeyError, ValueError, TypeError) as e:
            log.info("Cita del .ics sin fecha válida: %s", e)
            skipped += 1
            continue
        uid = str(component.get("UID") or "") or None
        old = start < now - IMPORT_SINCE and repeat == "none"
        if old or (uid is not None and store.has_uid(uid)):
            skipped += 1
            continue
        event = store.add_event(
            title,
            start.timestamp(),
            minutes=min(minutes, 14 * 24 * 60),
            all_day=all_day,
            remind=_remind(component),
            repeat=repeat,
            uid=uid,
        )
        added.append(event.id)
    return added, skipped
