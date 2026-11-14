"""Texto listo para decir en español: cifras, horas y símbolos en palabras.

Las voces (Pocket TTS, Piper) leen mal las cifras: «1, 2, 3» sonaba en inglés o a trozos.
Aquí «Son las 21:36» → «Son las veintiuna y treinta y seis», «50 %» → «cincuenta por ciento»,
«3,5» → «tres coma cinco», «18 °C» → «dieciocho grados». La burbuja sigue mostrando cifras.
"""

from __future__ import annotations

import re

_UNITS = [
    "cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve",
    "diez", "once", "doce", "trece", "catorce", "quince", "dieciséis", "diecisiete",
    "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidós", "veintitrés",
    "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve",
]  # fmt: skip
_TENS = {3: "treinta", 4: "cuarenta", 5: "cincuenta", 6: "sesenta", 7: "setenta", 8: "ochenta"}
_TENS[9] = "noventa"
_HUNDREDS = {
    1: "ciento",
    2: "doscientos",
    3: "trescientos",
    4: "cuatrocientos",
    5: "quinientos",
    6: "seiscientos",
    7: "setecientos",
    8: "ochocientos",
    9: "novecientos",
}
MAX_NUMBER = 999_999_999_999


def _below_thousand(n: int) -> str:
    if n < 30:
        return _UNITS[n]
    if n < 100:
        tens, unit = divmod(n, 10)
        return _TENS[tens] + (f" y {_UNITS[unit]}" if unit else "")
    if n == 100:
        return "cien"
    hundreds, rest = divmod(n, 100)
    return _HUNDREDS[hundreds] + (f" {_below_thousand(rest)}" if rest else "")


def _apocope(words: str) -> str:
    """«uno» → «un» delante de «mil» o «millones» («veintiún mil»)."""
    if words.endswith("veintiuno"):
        return words[: -len("veintiuno")] + "veintiún"
    if words.endswith("uno"):
        return words[:-1]
    return words


def number_words(n: int, *, feminine: bool = False) -> str:
    """0 ≤ n ≤ 999 999 999 999 en palabras. `feminine`: «una», «veintiuna» (horas)."""
    if n < 0:
        return "menos " + number_words(-n, feminine=feminine)
    if n > MAX_NUMBER:
        return " ".join(_UNITS[int(d)] for d in str(n))  # se dice cifra a cifra
    millions, rest = divmod(n, 1_000_000)
    thousands, units = divmod(rest, 1000)
    parts: list[str] = []
    if millions:
        if millions == 1:
            parts.append("un millón")
        else:
            parts.append(_apocope(number_words(millions)) + " millones")
    if thousands:
        parts.append("mil" if thousands == 1 else _apocope(_below_thousand(thousands)) + " mil")
    if units or not parts:
        parts.append(_below_thousand(units))
    out = " ".join(parts)
    if feminine:
        out = re.sub(r"(veinti)?uno$", lambda m: (m.group(1) or "") + "una", out)
        out = out.replace("veintiuno", "veintiuna")
    return out


def _time(m: re.Match[str]) -> str:
    hour, minute = int(m.group(1)), int(m.group(2))
    words = number_words(hour, feminine=True)
    if minute == 0:
        return words + " en punto" if m.group(3) is None else words
    if minute == 15:
        return words + " y cuarto"
    if minute == 30:
        return words + " y media"
    return f"{words} y {number_words(minute)}"


def _decimal(m: re.Match[str]) -> str:
    whole, frac = m.group(1), m.group(2)
    frac_words = (
        number_words(int(frac))
        if not frac.startswith("0")
        else " ".join(_UNITS[int(d)] for d in frac)
    )
    return f"{number_words(int(whole))} coma {frac_words}"


def _integer(m: re.Match[str]) -> str:
    digits = m.group(0).replace(".", "")
    return number_words(int(digits))


_SYMBOLS = (
    (re.compile(r"\s*%"), " por ciento"),
    (re.compile(r"\s*°\s*C\b"), " grados"),
    (re.compile(r"\s*°"), " grados"),
    (re.compile(r"\s*€"), " euros"),
    (re.compile(r"(?<=\d)\s*\$|\$\s*(?=\d)"), " dólares "),
    (re.compile(r"(?<=\d)\s*[x×*]\s*(?=\d)"), " por "),
    (re.compile(r"(?<=\d)\s*÷\s*(?=\d)"), " entre "),
    (re.compile(r"(?<=\d)\s*\+\s*(?=\d)"), " más "),
    (re.compile(r"(?<=\d)\s*=\s*(?=\d)"), " igual a "),
    (re.compile(r"(?<=\s)-(?=\d)|^-(?=\d)"), "menos "),
    (re.compile(r"(?<=\d)\s*-\s*(?=\d)"), " menos "),
)
_TIME = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)(?!\d)(\s*h\b)?")
_DECIMAL = re.compile(r"\b(\d+),(\d+)\b|\b(\d+)\.(\d{1,2}|\d{4,})\b")
_THOUSANDS = re.compile(r"\b\d{1,3}(?:\.\d{3})+\b")  # 1.000, 25.000.000
_INTEGER = re.compile(r"\b\d+\b")
# Direcciones IP: cada número por separado («ciento noventa y dos punto ciento sesenta y ocho…»).
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _ip(m: re.Match[str]) -> str:
    return " punto ".join(number_words(int(part)) for part in m.group().split("."))


def _any_decimal(m: re.Match[str]) -> str:
    if m.group(1) is not None:
        return _decimal(m)
    whole, frac = m.group(3), m.group(4)
    fake = re.match(r"(\d+),(\d+)", f"{whole},{frac}")
    assert fake is not None
    return _decimal(fake)


def to_spoken(text: str) -> str:
    """El texto con las cifras y los símbolos tal como se dicen."""
    if not re.search(r"[\d%°€$×÷=+]", text):
        return text
    out = _IPV4.sub(_ip, text)
    out = _TIME.sub(_time, out)
    for pattern, words in _SYMBOLS:
        out = pattern.sub(words, out)
    out = _THOUSANDS.sub(_integer, out)
    out = _DECIMAL.sub(_any_decimal, out)
    out = _INTEGER.sub(_integer, out)
    return re.sub(r"\s{2,}", " ", out).strip()
