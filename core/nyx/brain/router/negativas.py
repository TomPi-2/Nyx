"""Lo que Nyx nunca hace (SPEC secciones 1 y 8): negativas fijas, antes de todo."""

from __future__ import annotations

import re

from nyx.brain.router.comun import (
    _clean,
)
from nyx.index.aliases import normalize
from nyx.index.model import Kind
from nyx.index.service import SystemIndex

# --- lo que Nyx nunca hace (SPEC secciones 1 y 8) ---

_EMPTY_BIN = re.compile(r"\b(?:vacia|vaciar|limpia|limpiar|borra|borrar)\w*\s+(?:la\s+)?papelera\b")
_FOREVER = re.compile(
    r"\b(?:borra|elimina|borrar|eliminar)\w*\b.*\b(?:para siempre|permanentemente|definitivamente)\b"
)
# Nada de dinero (ACCIONES.md, reglas que no cambian): no puede depender del modelo, que a
# veces abría la tienda para «comprar unas zapatillas en Amazon».
_MONEY = re.compile(
    r"^(?:(?:puedes|podrias)\s+)?(?:compra\w*|paga|pagame|pagar|pagarme|"
    r"haz(?:me)? (?:un|el) pedido|pide(?:me)? (?:un|una|unos|unas)\b.*\b(?:en|a)\s+\w+|"
    r"transfiere|transferir|envia(?:le)? dinero|manda(?:le)? dinero)\b"
)
_IN_GAME = re.compile(
    r"\b(?:escribe|pulsa|teclea|dispara|apunta|juega|mueve|compra|vende|chat|chatea|"
    r"manda un mensaje)\b"
)


# Con una partida en marcha no hace falta nombrar el juego: «salta», «acelera», «dispara»…
# piden actuar dentro de él. «mueve» o «escribe» solos no cuentan («mueve Discord al otro
# monitor» se deja para después de la partida).
_PLAYING = re.compile(
    r"\b(?:salt[aeo]\w*|avanz\w*|aceler\w*|fren[aeo]\w*|gir[aeo]s?|girar|conduc\w*|"
    r"dispar\w*|apunt[aeo]s?|apuntar|recarg\w*|agach\w*|esquiv\w*|ataca\w*|defiend\w*|"
    r"constru\w*|juega|juegues|jugar por mi|tir[aeo]s?\s+(?:hacia|para)|"
    r"chatea\w*|manda un mensaje en el chat)\b"
    r"|\b(?:el coche|la pelota|el balon|el personaje|el muneco|mi jugador)\b"
)
IN_GAME_REFUSAL = ("Dentro de los juegos no toco nada", "puedo abrirlos, la música y el volumen")


def refusal(text: str, index: SystemIndex, *, playing: bool = False) -> tuple[str, str] | None:
    """(burbuja, línea secundaria) si es algo que Nyx no hace nunca; si no, None.

    `playing`: hay una partida en marcha (modo partida activo).
    """
    clean = _clean(text)
    if _EMPTY_BIN.search(clean) or _FOREVER.search(clean):
        return "Eso no lo hago", "borraría para siempre: lo que borro va a la papelera"
    if _MONEY.search(clean):
        return "Eso no lo hago", "no compro ni pago nada: puedo abrirte la web"
    if playing and _PLAYING.search(clean):
        return IN_GAME_REFUSAL
    if _IN_GAME.search(clean):
        games = {a for e in index.entries({Kind.GAME}) for a in (*e.aliases, normalize(e.name))}
        words = f" {clean} "
        if any(f" {alias} " in words for alias in games if len(alias) > 2):
            return IN_GAME_REFUSAL
    return None
