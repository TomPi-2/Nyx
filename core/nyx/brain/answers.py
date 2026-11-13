"""Respuestas habladas con variantes según el tono (0.6, tarea 6.26).

Lo que resuelve el router y se contesta sin el LLM (6.20a: batería, qué suena, cronómetro…)
se decía siempre con la misma frase de la herramienta, y sonaba a máquina. Aquí cada respuesta
tiene 3–4 variantes por tono (cercano, neutro, divertido), hechas con los datos que ya devuelve
la herramienta (`ToolResult.data`). Al elegir, nunca se repite la última de esa respuesta.

Si una respuesta no está aquí (o le faltan datos), se dice el mensaje de la herramienta, como
antes. Los paneles no cambian: siguen siendo los de la herramienta.

Todas las variantes empiezan en mayúscula, acaban en punto y llevan sus tildes: lo comprueba
`tests/test_answers.py` con datos de ejemplo.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping
from typing import Any

from nyx.alarms.spoken import spoken_duration
from nyx.settings.model import ResponseTone
from nyx.tools.base import ToolResult

Data = Mapping[str, Any]
Variant = Callable[[Data], str]
Variants = dict[ResponseTone, tuple[Variant, ...]]


def _plugged(d: Data) -> bool:
    return bool(d.get("plugged"))


def _rem(d: Data, before: str = ". ", word: str = "Aguanta") -> str:
    """«. Aguanta unas 2 horas y 5 minutos» si se sabe cuánto queda (solo sin enchufar)."""
    minutes = int(d.get("remaining_min") or 0)
    if minutes <= 0 or _plugged(d):
        return ""
    about = "unas" if minutes >= 60 else "unos"
    return f"{before}{word} {about} {spoken_duration(minutes * 60)}"


def _time(d: Data) -> str:
    seconds = int(d.get("elapsed_s") or 0)
    return "0 segundos" if seconds == 0 else spoken_duration(seconds)


def _by(d: Data) -> str:
    return f" de {d['artist']}" if d.get("artist") else ""


ANSWERS: dict[str, Variants] = {
    "battery": {
        "cercano": (
            lambda d: (
                f"Te queda un {d['percent']} % de batería"
                + (" y está cargando" if _plugged(d) else "")
                + _rem(d)
                + "."
            ),
            lambda d: (
                f"Vas al {d['percent']} %"
                + (", y enchufado" if _plugged(d) else ", sin enchufar")
                + _rem(d)
                + "."
            ),
            lambda d: (
                f"Tienes la batería al {d['percent']} %"
                + (" y cargando" if _plugged(d) else "")
                + _rem(d)
                + "."
            ),
        ),
        "neutro": (
            lambda d: (
                f"Batería al {d['percent']} %"
                + (", cargando" if _plugged(d) else ", sin cargar")
                + _rem(d, before=", ", word="quedan")
                + "."
            ),
            lambda d: (
                f"{d['percent']} % de batería"
                + (", enchufado" if _plugged(d) else "")
                + _rem(d, before=", ", word="quedan")
                + "."
            ),
        ),
        "divertido": (
            lambda d: (
                f"{d['percent']} % y "
                + ("chupando corriente, vamos bien" if _plugged(d) else "tirando de reservas")
                + _rem(d, word="Aguanto")
                + "."
            ),
            lambda d: (
                f"Me queda un {d['percent']} % de energía"
                + (", y comiendo enchufe" if _plugged(d) else "")
                + _rem(d, word="Aguanto")
                + "."
            ),
            lambda d: (
                f"Batería al {d['percent']} %"
                + (", enchufada y feliz" if _plugged(d) else ", sin cable a la vista")
                + _rem(d)
                + "."
            ),
        ),
    },
    "no_battery": {
        "cercano": (
            lambda d: "Este equipo no tiene batería, va siempre enchufado.",
            lambda d: "Aquí no hay batería: funciona directamente con la corriente.",
            lambda d: "No tiene batería, así que tira siempre del enchufe.",
        ),
        "neutro": (
            lambda d: "Sin batería: conectado a la corriente.",
            lambda d: "Este equipo no tiene batería.",
        ),
        "divertido": (
            lambda d: "¿Batería? Este vive pegado al enchufe.",
            lambda d: "Nada de batería: aquí se vive del enchufe.",
            lambda d: "Sin batería, pero con enchufe infinito.",
        ),
    },
    "cpu": {
        "cercano": (
            lambda d: f"El procesador va al {d['percent']} %.",
            lambda d: f"Ahora mismo el procesador está al {d['percent']} %.",
            lambda d: f"La CPU está al {d['percent']} % de uso.",
        ),
        "neutro": (
            lambda d: f"CPU al {d['percent']} %.",
            lambda d: f"Uso del procesador: {d['percent']} %.",
        ),
        "divertido": (
            lambda d: (
                f"El procesador va al {d['percent']} %"
                + (", sudando un poco." if int(d["percent"]) >= 70 else ", sin despeinarse.")
            ),
            lambda d: (
                f"CPU al {d['percent']} %"
                + (": a tope." if int(d["percent"]) >= 70 else ": ni se despeina.")
            ),
            lambda d: f"El procesador está al {d['percent']} %, todo bajo control.",
        ),
    },
    "ram": {
        "cercano": (
            lambda d: f"Estás usando {d['used_gb']} GB de {d['total_gb']} GB de RAM.",
            lambda d: f"La RAM va al {d['percent']} %: {d['used_gb']} de {d['total_gb']} GB.",
            lambda d: f"Tienes ocupados {d['used_gb']} GB de los {d['total_gb']} GB de RAM.",
        ),
        "neutro": (
            lambda d: f"RAM: {d['used_gb']} de {d['total_gb']} GB ({d['percent']} %).",
            lambda d: f"Memoria en uso: {d['used_gb']} GB de {d['total_gb']} GB.",
        ),
        "divertido": (
            lambda d: (
                f"{d['used_gb']} GB de {d['total_gb']} ocupados en la RAM"
                + (", esto va lleno." if int(d["percent"]) >= 80 else ", hay sitio de sobra.")
            ),
            lambda d: f"La RAM está al {d['percent']} %, {d['used_gb']} de {d['total_gb']} GB.",
            lambda d: f"Memoria al {d['percent']} %: {d['used_gb']} GB de {d['total_gb']}.",
        ),
    },
    "disk": {
        "cercano": (
            lambda d: f"Te quedan {d['free_gb']} GB libres en {d['unit']}.",
            lambda d: f"En {d['unit']} tienes {d['free_gb']} GB libres de {d['total_gb']}.",
            lambda d: f"Hay {d['free_gb']} GB libres en {d['unit']}.",
        ),
        "neutro": (
            lambda d: f"{d['free_gb']} GB libres en {d['unit']}.",
            lambda d: f"Espacio libre en {d['unit']}: {d['free_gb']} GB de {d['total_gb']}.",
        ),
        "divertido": (
            lambda d: (
                f"Quedan {d['free_gb']} GB libres en {d['unit']}"
                + (
                    ", hay sitio para rato."
                    if int(d["free_gb"]) >= 100
                    else ", toca hacer limpieza."
                )
            ),
            lambda d: f"{d['free_gb']} GB libres en {d['unit']}. Aún cabe algo.",
            lambda d: f"En {d['unit']} te quedan {d['free_gb']} GB libres.",
        ),
    },
    "top_same": {
        "cercano": (
            lambda d: (
                f"El que más consume es {d['cpu_name']}: {d['cpu_pct']} % de CPU y "
                f"{d['ram']} de RAM."
            ),
            lambda d: (
                f"{d['cpu_name']} es lo que más gasta: {d['cpu_pct']} % de CPU y {d['ram']} de RAM."
            ),
            lambda d: f"Ahora mismo lo que más tira del equipo es {d['cpu_name']}.",
        ),
        "neutro": (
            lambda d: f"Más consumo: {d['cpu_name']}, {d['cpu_pct']} % de CPU y {d['ram']}.",
            lambda d: f"{d['cpu_name']}: {d['cpu_pct']} % de CPU y {d['ram']} de RAM.",
        ),
        "divertido": (
            lambda d: f"El glotón es {d['cpu_name']}: {d['cpu_pct']} % de CPU y {d['ram']}.",
            lambda d: f"{d['cpu_name']} se está comiendo el equipo: {d['cpu_pct']} % de CPU.",
            lambda d: f"El culpable es {d['cpu_name']}, con {d['ram']} de RAM.",
        ),
    },
    "top_split": {
        "cercano": (
            lambda d: f"El que más CPU usa es {d['cpu_name']} y el que más RAM, {d['ram_name']}.",
            lambda d: (
                f"{d['cpu_name']} es el que más tira de la CPU, y {d['ram_name']} el que "
                "más memoria ocupa."
            ),
            lambda d: (
                f"En CPU gana {d['cpu_name']} ({d['cpu_pct']} %), y en RAM "
                f"{d['ram_name']} ({d['ram']})."
            ),
        ),
        "neutro": (
            lambda d: (
                f"CPU: {d['cpu_name']} ({d['cpu_pct']} %). RAM: {d['ram_name']} ({d['ram']})."
            ),
            lambda d: f"Más CPU, {d['cpu_name']}; más RAM, {d['ram_name']}.",
        ),
        "divertido": (
            lambda d: f"Hay dos glotones: {d['cpu_name']} en CPU y {d['ram_name']} en RAM.",
            lambda d: f"{d['cpu_name']} se come la CPU y {d['ram_name']}, la memoria.",
            lambda d: f"En CPU manda {d['cpu_name']} y en RAM, {d['ram_name']}.",
        ),
    },
    "playing": {
        "cercano": (
            lambda d: f"Está sonando «{d['title']}»{_by(d)}.",
            lambda d: f"Suena «{d['title']}»{_by(d)}, en {d['app']}.",
            lambda d: f"Es «{d['title']}»{_by(d)}.",
        ),
        "neutro": (
            lambda d: f"Suena «{d['title']}»{_by(d)} en {d['app']}.",
            lambda d: f"«{d['title']}»{_by(d)}.",
        ),
        "divertido": (
            lambda d: f"Esto es «{d['title']}»{_by(d)}. Buena elección.",
            lambda d: f"Suena «{d['title']}»{_by(d)}, y suena bien.",
            lambda d: f"Ahora mismo, «{d['title']}»{_by(d)}.",
        ),
    },
    "paused": {
        "cercano": (
            lambda d: f"Tienes en pausa «{d['title']}»{_by(d)}.",
            lambda d: f"Está en pausa «{d['title']}»{_by(d)}, en {d['app']}.",
        ),
        "neutro": (lambda d: f"En pausa: «{d['title']}»{_by(d)}.",),
        "divertido": (
            lambda d: f"«{d['title']}»{_by(d)} está esperando a que le des al play.",
            lambda d: f"En pausa: «{d['title']}»{_by(d)}. Cuando quieras, seguimos.",
        ),
    },
    "silence": {
        "cercano": (
            lambda d: "Ahora mismo no suena nada.",
            lambda d: "No está sonando nada.",
            lambda d: "No suena nada ahora.",
        ),
        "neutro": (lambda d: "No suena nada.", lambda d: "Nada en reproducción."),
        "divertido": (
            lambda d: "Silencio total. Ni una nota.",
            lambda d: "Aquí no suena nada, ni un grillo.",
            lambda d: "Nada sonando. ¿Ponemos algo?",
        ),
    },
    "stopwatch_running": {
        "cercano": (
            lambda d: f"El cronómetro lleva {_time(d)}.",
            lambda d: f"Llevas {_time(d)}.",
            lambda d: f"Van {_time(d)}.",
        ),
        "neutro": (lambda d: f"Cronómetro: {_time(d)}.", lambda d: f"{_time(d)}.".capitalize()),
        "divertido": (
            lambda d: f"Llevas {_time(d)}, y sigo contando.",
            lambda d: f"{_time(d)} y subiendo.".capitalize(),
            lambda d: f"El crono marca {_time(d)}.",
        ),
    },
    "stopwatch_stopped": {
        "cercano": (
            lambda d: f"El cronómetro está parado en {_time(d)}.",
            lambda d: f"Se quedó en {_time(d)}.",
            lambda d: f"Lo paraste en {_time(d)}.",
        ),
        "neutro": (lambda d: f"Parado en {_time(d)}.", lambda d: f"Cronómetro: {_time(d)}."),
        "divertido": (
            lambda d: f"Congelado en {_time(d)}.",
            lambda d: f"Se quedó en {_time(d)}, ni un segundo más.",
            lambda d: f"El crono descansa en {_time(d)}.",
        ),
    },
    "stopwatch_stop": {
        "cercano": (
            lambda d: f"Parado en {_time(d)}.",
            lambda d: f"Listo: {_time(d)}.",
            lambda d: f"Has tardado {_time(d)}.",
        ),
        "neutro": (
            lambda d: f"Cronómetro parado en {_time(d)}.",
            lambda d: f"{_time(d)}.".capitalize(),
        ),
        "divertido": (
            lambda d: f"¡Tiempo! {_time(d)}.",
            lambda d: f"Parado. Marca final: {_time(d)}.",
            lambda d: f"Crono detenido en {_time(d)}. ¿Récord?",
        ),
    },
    "stopwatch_none": {
        "cercano": (
            lambda d: "No hay ningún cronómetro en marcha.",
            lambda d: "Ahora mismo no está contando ningún cronómetro.",
        ),
        "neutro": (lambda d: "No hay cronómetro en marcha.",),
        "divertido": (
            lambda d: "No estoy cronometrando nada. ¿Empezamos?",
            lambda d: "Cero cronómetros en marcha.",
        ),
    },
    "no_alarms": {
        "cercano": (
            lambda d: "No tienes alarmas ni temporizadores.",
            lambda d: "No hay ninguna alarma ni temporizador puesto.",
            lambda d: "No tienes nada programado.",
        ),
        "neutro": (lambda d: "Sin alarmas ni temporizadores.", lambda d: "No hay alarmas."),
        "divertido": (
            lambda d: "Agenda vacía: ni alarmas ni temporizadores.",
            lambda d: "Nada programado. Día libre.",
            lambda d: "Cero alarmas. Hoy no suena nada.",
        ),
    },
}


def answer_key(tool: str, args: Data, result: ToolResult) -> tuple[str, dict[str, Any]] | None:
    """Qué respuesta toca y con qué datos, o None si no hay variantes para este resultado."""
    d = result.data
    if tool == "system_info":
        what = d.get("what")
        if what == "battery":
            return ("battery", dict(d)) if d.get("has_battery") else ("no_battery", {})
        if what in ("cpu", "ram"):
            return str(what), dict(d)
        if what == "disk" and len(d.get("disks") or []) == 1:
            return "disk", dict(d["disks"][0])
        if what == "top":
            cpu, ram = d.get("top_cpu") or {}, d.get("top_ram") or {}
            fields = {
                "cpu_name": cpu.get("name"),
                "cpu_pct": cpu.get("percent"),
                "ram_name": ram.get("name"),
                "ram": ram.get("formatted"),
            }
            return ("top_same" if fields["cpu_name"] == fields["ram_name"] else "top_split"), fields
        return None
    if tool == "now_playing":
        if not d.get("title"):
            return "silence", {}
        return ("playing" if d.get("playing") else "paused"), dict(d)
    if tool == "stopwatch":
        action = args.get("action")
        if action == "stop":
            return "stopwatch_stop", dict(d)
        if action == "status":
            if d.get("running"):
                return "stopwatch_running", dict(d)
            return ("stopwatch_stopped", dict(d)) if d.get("elapsed_s") else ("stopwatch_none", {})
        return None
    if tool == "list_alarms" and not d.get("ids"):
        return "no_alarms", {}
    return None


class Answers:
    """Elige la variante del tono elegido sin repetir la última de cada respuesta."""

    def __init__(self, tone: ResponseTone = "cercano", rng: random.Random | None = None) -> None:
        self.tone: ResponseTone = tone
        self._rng = rng or random.Random()
        self._last: dict[str, int] = {}

    def say(self, tool: str, args: Data, result: ToolResult) -> str | None:
        """La frase para decir, o None si no hay variantes (se dice el mensaje de siempre)."""
        found = answer_key(tool, args, result)
        if found is None:
            return None
        key, data = found
        options = ANSWERS[key][self.tone]
        choices = [i for i in range(len(options)) if i != self._last.get(key)] or [0]
        index = self._rng.choice(choices)
        try:
            text = options[index](data)
        except (KeyError, TypeError, ValueError):
            return None  # faltan datos: mejor el mensaje de la herramienta
        self._last[key] = index
        return text
