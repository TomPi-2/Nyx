"""Reglas de sonido: volumen, reproducción, Spotify, qué suena y salida de audio."""

from __future__ import annotations

import re

from nyx.brain.router.comun import (
    _NUM,
    Route,
    _call,
    _original,
    parse_number,
    rule,
)
from nyx.index.model import Kind
from nyx.index.service import SystemIndex
from nyx.tools.app_catalog import profile_for

# --- volumen (antes que «pon …» y «abre …») ---


# «sube el volumen de Spotify», «baja el sonido en Discord al 20», «sube el volumen al 50 en Spotify»
_APP_AT = r"(?:\s+(?:de|en|del)\s+(?P<app>[a-z0-9 ]+?))?"
_APP_AFTER = r"(?:\s+(?:de|en|del|para)\s+(?P<app2>[a-z0-9 ]+?))?"
_VOLUME_TAIL = (
    rf"(?P<much0>\s+mucho)?(?:\s+un poco)?\s+(?:el\s+)?(?:volumen|sonido){_APP_AT}(?:\s+(?:a|al|hasta(?:\s+el)?)\s+{_NUM})?"
    rf"{_APP_AFTER}(?P<much>\s+mucho)?(?:\s+un poco)?$"
)


def _volume(rule_name: str, m: re.Match[str], index: SystemIndex, step: int) -> Route | None:
    app_name = m.group("app") or m.group("app2")
    much = bool(m.group("much") or m.group("much0"))  # «sube mucho el volumen»
    app: str | None = None
    best = None
    if app_name:
        best = index.confident(index.resolve(app_name, {Kind.APP, Kind.GAME}))
        if best is None:
            return None  # que lo intente el LLM
        app = best.entry.name
    if m.group("n"):
        level = parse_number(m.group("n"))
        if level is None or level > 100:
            return None
        return _call(rule_name, "set_volume", level=level, app=app)
    action = "volume_up" if step > 0 else "volume_down"
    profile = profile_for(best.entry.process, app) if app_name and best else None
    if profile is not None and action in profile.actions:
        # Spotify tiene su propio volumen: se mueve su control (el del mezclador no se ve).
        return _call(rule_name, "app_action", app=app, action=action, times=2 if much else 1)
    return _call(rule_name, "set_volume", change=step * (2 if much else 1), app=app)


@rule("volume_up", rf"^(?:sube|subir|subeme|aumenta){_VOLUME_TAIL}")
def _volume_up(m: re.Match[str], index: SystemIndex) -> Route | None:
    return _volume("volume_up", m, index, 10)


@rule("volume_down", rf"^(?:baja|bajar|bajame|reduce){_VOLUME_TAIL}")
def _volume_down(m: re.Match[str], index: SystemIndex) -> Route | None:
    return _volume("volume_down", m, index, -10)


@rule(
    "volume_set",
    rf"^(?:(?:pon|deja|ajusta|cambia)\s+(?:el\s+)?)?volumen\s+(?:a|al|en)?\s*{_NUM}(?:\s*%|\s+por ciento)?$",
)
def _volume_set(m: re.Match[str], _: SystemIndex) -> Route | None:
    level = parse_number(m.group("n"))
    if level is None or level > 100:
        return None
    return _call("volume_set", "set_volume", level=level)


@rule(
    "unmute",
    r"^(?:quita(?:r)? el silencio|activa(?:r)? el sonido|desilencia|desmutea|devuelve el sonido|pon(?: el)? sonido)$",
)
def _unmute(m: re.Match[str], _: SystemIndex) -> Route:
    return _call("unmute", "set_volume", mute=False)


@rule(
    "mute",
    r"^(?:silencia(?:lo|r)?|mutea|silencio|quita(?:r)? el sonido|calla el (?:pc|ordenador))(?:\s+(?P<app>.+))?$",
)
def _mute(m: re.Match[str], index: SystemIndex) -> Route | None:
    app = m.group("app")
    if app in (None, "todo", "el pc", "el ordenador", "el sonido"):
        return _call("mute", "set_volume", mute=True)
    best = index.confident(index.resolve(app, {Kind.APP, Kind.GAME}))
    return _call("mute", "set_volume", mute=True, app=best.entry.name) if best else None


# --- multimedia ---


@rule(
    "media_pause",
    r"^(?:(?:quiero\s+que|puedes|podrias)\s+)?"
    r"(?:"
    r"(?:pausa|pausar|pauses|para|parar|pares|deten|detengas)(?:\s+(?:la\s+|el\s+|a\s+la\s+|al\s+)?(?:musica|cancion|video|reproduccion|(?P<app>spotify|youtube)))?"
    r"|pana\s+(?:la\s+|el\s+)?(?:musica|cancion|video|reproduccion|(?P<app2>spotify|youtube))"
    r")(?:\s+(?:de|en|del)\s+(?P<src>[a-z0-9 ]+))?$"
    r"|^sigue\s+sonando\s+(?:la\s+musica|la\s+cancion|el\s+video)(?:\s+en\s+(?P<src2>[a-z0-9 ]+?))?\s+para(?:\s+la)?$",
)
def _pause(m: re.Match[str], _: SystemIndex) -> Route:
    source = m.group("src") or m.group("app") or m.group("app2") or m.group("src2")
    return _call("media_pause", "media_control", action="pause", source=source)


@rule(
    "media_play",
    r"^(?:(?:reanuda|reanudar|continua|play|dale al play|dale a play|reproduce|quita la pausa)(?:\s+(?:la\s+|el\s+|a la\s+|al\s+)?(?:musica|cancion|video))?"
    r"|(?:pon|ponme|quiero)\s+(?:algo de\s+|un poco de\s+|la\s+)?musica)"
    r"(?:\s+(?:de|en|del)\s+(?P<src>[a-z0-9 ]+))?$",
)
def _play(m: re.Match[str], _: SystemIndex) -> Route:
    # «Pon música» (sin decir dónde) es poner música, no reanudar lo último que sonó.
    music = bool(re.match(r"(?:pon|ponme|quiero)\b", m.group(0))) and not m.group("src")
    return _call(
        "media_play", "media_control", action="play", source=m.group("src"), music=music or None
    )


@rule(
    "media_next",
    r"^(?:(?:pon\s+)?(?:la\s+)?siguiente|pasa(?:\s+de|\s+a)?(?:\s+la\s+siguiente)?|salta|skip)(?:\s+(?:cancion|tema|pista|video))?"
    r"(?:\s+(?:en|de|del)\s+[a-z0-9 ]+)?$",
)
def _next(m: re.Match[str], _: SystemIndex) -> Route:
    return _call("media_next", "media_control", action="next")


@rule(
    "media_previous",
    r"^(?:(?:pon\s+)?(?:la\s+)?anterior|(?:cancion|tema|pista) anterior|vuelve a la anterior)(?:\s+(?:cancion|tema|pista))?"
    r"(?:\s+(?:en|de|del)\s+[a-z0-9 ]+)?$",
)
def _previous(m: re.Match[str], _: SystemIndex) -> Route:
    return _call("media_previous", "media_control", action="previous")


_SPOTIFY = r"(?:\s+(?:en|de)\s+spotify)?$"
rule(
    "shuffle",
    r"^(?:pon|activa|quita|desactiva)\s+(?:el\s+)?(?:modo\s+)?(?:aleatorio|shuffle)" + _SPOTIFY,
)(lambda m, index: _call("shuffle", "app_action", app="Spotify", action="shuffle"))
rule(
    "repeat",
    r"^(?:pon|activa|quita|desactiva)\s+(?:el\s+)?(?:modo\s+)?(?:repetir|bucle|repeticion)"
    + _SPOTIFY,
)(lambda m, index: _call("repeat", "app_action", app="Spotify", action="repeat"))
rule(
    "like",
    r"^(?:dale\s+(?:a\s+)?(?:un\s+)?me gusta|me gusta esta cancion|guarda esta cancion)"
    r"(?:\s+a\s+esta\s+cancion)?" + _SPOTIFY,
)(lambda m, index: _call("like", "app_action", app="Spotify", action="like"))


# --- música actual, cronómetro y salida de audio (6.12) ---


@rule(
    "now_playing",
    r"^(?:(?:dime|sabes)\s+)?"
    r"(?:"
    r"que\s+(?:(?:cancion|tema|musica|pista|video)\s+)?(?:esta\s+sonando|suena)"
    r"(?:\s+ahora(?:\s+mismo)?)?(?:\s+en\s+[a-z0-9 ]+)?"
    r"|que\s+(?:cancion|tema|musica|pista)\s+es(?:\s+(?:esta|este))?"
    r"|como\s+se\s+llama\s+(?:esta\s+)?(?:cancion|tema|pista)(?:\s+que\s+(?:suena|esta\s+sonando))?"
    r"|(?:quien|de\s+quien)\s+(?:canta|es)\s+(?:esto|esta\s+(?:cancion|tema)|la\s+cancion(?:\s+que\s+suena)?)"
    r"|quien\s+canta"
    r")$",
)
def _now_playing(_: re.Match[str], __: SystemIndex) -> Route:
    return _call("now_playing", "now_playing")


_AUDIO_DEV = r"(?:auriculares|cascos|altavoces|bluetooth|hdmi|barra\s+de\s+sonido|monitor|tele(?:vision)?|tv|usb)"


@rule(
    "audio_output",
    r"^(?:(?:cambia|cambiame|selecciona|elige|pon|ponme|ponen|saca|pasa|manda)\s+)?"
    r"(?:"
    r"(?:la\s+)?salida\s+(?:de\s+|del\s+)?(?:audio|sonido)"
    r"(?:\s+(?:a|al|en|por|de|del)\s+(?:los\s+|las\s+|el\s+|la\s+)?(?P<d1>.+))?"
    r"|(?:el\s+)?dispositivo\s+(?:de\s+)?(?:salida|reproduccion|audio)"
    r"(?:\s+(?:a|al|en|por|de|del)\s+(?:los\s+|las\s+|el\s+|la\s+)?(?P<d2>.+))?"
    rf"|(?:el\s+)?(?:audio|sonido)\s+(?:a|al|en|por|de|del)\s+(?:los\s+|las\s+|el\s+|la\s+)?(?P<d3>{_AUDIO_DEV}.*)"
    r"|(?:el\s+)?(?:audio|sonido)\s+(?:sigue\s+saliendo|sale)\s+por\s+.+?\s+en\s+vez\s+de(?:\s+por)?\s+(?:los\s+|las\s+|el\s+|la\s+)?(?P<d4>.+)"
    r")$",
)
def _audio_output(m: re.Match[str], __: SystemIndex) -> Route:
    raw = m.group("d1") or m.group("d2") or m.group("d3") or m.group("d4")
    device = _original(raw) if raw else None
    return _call("audio_output", "audio_output", device=device)
