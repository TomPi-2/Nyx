"""Criterio común de los paneles (6.23, opción A: punto solo en las frases)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from nyx.brain.panel import capitalize, is_sentence, tidy, unrelated


@pytest.mark.parametrize(
    ("display", "secondary", "spoken", "want"),
    [
        # Etiquetas de las herramientas: mayúscula, sin punto.
        ("40 %", "batería · desenchufado", "", ("40 %", "Batería · desenchufado")),
        ("Bohemian Rhapsody", "Queen · Spotify", "", ("Bohemian Rhapsody", "Queen · Spotify")),
        (
            "Sin batería",
            "conectado a la corriente",
            "",
            ("Sin batería", "Conectado a la corriente"),
        ),
        ("CPU al 12 %", "uso del procesador", "", ("CPU al 12 %", "Uso del procesador")),
        # Cabeceras del LLM: el contexto en minúsculas pasa a mayúscula.
        ("Hallo", "hola · alemán", "", ("Hallo", "Hola · alemán")),
        (
            "Miguel de Cervantes",
            "autor del Quijote",
            "",
            ("Miguel de Cervantes", "Autor del Quijote"),
        ),
        # Frases: punto final.
        (
            "Te quedan 120 GB libres en C:",
            "",
            "",
            ("Te quedan 120 GB libres en C:.", ""),
        ),
        ("No suena nada", "", "", ("No suena nada.", "")),  # lleva verbo: es una frase
        (
            "La capital es Madrid",
            "desde 1561",
            "",
            ("La capital es Madrid.", "Desde 1561"),
        ),
        # La pequeña no aporta: relleno o lo mismo que la grande.
        ("Madrid", "respuesta", "", ("Madrid", "")),
        ("Vale", "prueba", "", ("Vale", "")),
        ("10 archivos en Descargas", "archivos en descargas", "", ("10 archivos en Descargas", "")),
        # Grande de una palabra sin contenido: la primera frase de la voz.
        (
            "Sí",
            "respuesta",
            "Sí, mañana va a llover por la tarde. Lleva paraguas.",
            ("Sí, mañana va a llover por la tarde.", ""),
        ),
        (
            "Claro",
            "",
            "Claro que sí, dime qué necesitas.",
            ("Claro que sí, dime qué necesitas.", ""),
        ),
        # Una palabra que SÍ es el dato no se toca.
        ("Hallo", "hola · alemán", "En alemán se dice Hallo.", ("Hallo", "Hola · alemán")),
        # Marcas con mayúsculas por dentro.
        ("iPhone 15", "", "", ("iPhone 15", "")),
        ("¿qué tal?", "", "", ("¿Qué tal?", "")),
        ("«imagine»", "John Lennon", "", ("«Imagine»", "John Lennon")),
    ],
)
def test_tidy(display: str, secondary: str, spoken: str, want: tuple[str, str]) -> None:
    assert tidy(display, secondary, spoken) == want


def test_sentence_or_label() -> None:
    assert is_sentence("El uso de CPU está al 30 %")
    assert is_sentence("Suena «Imagine» de John Lennon")
    assert not is_sentence("Nivel de batería")
    assert not is_sentence("Queen · Spotify")
    assert not is_sentence("40 %")
    assert capitalize("") == ""


def test_fixed_texts_keep_their_accents() -> None:
    """Los textos fijos que ve o escucha el usuario llevan sus tildes (6.23)."""
    need = {
        "bateria", "cancion", "cronometro", "musica", "energia", "reproduccion", "aqui",
        "tambien", "ningun", "ultimo", "ultima", "ultimos", "ultimas", "telefono", "busqueda",
        "pagina", "paginas", "aplicacion", "configuracion", "conexion", "informacion",
        "direccion", "camara", "imagenes", "menu", "numero", "maximo", "minimo", "rapido",
        "despues", "todavia", "ademas", "alli", "dia", "dias",
    }  # fmt: skip
    root = Path(__file__).parent.parent / "nyx"
    files = [
        *(p for p in (root / "tools").glob("*.py") if p.name != "groups.py"),
        root / "brain" / "phrases.py",
        root / "brain" / "answers.py",
        root / "executor.py",
        root / "pipeline.py",
        root / "game" / "controller.py",
        root / "alarms" / "ringer.py",
        root / "alarms" / "spoken.py",
    ]
    bad: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and " " in node.value
                and id(node) not in docstrings
            ):
                words = set(re.findall(r"[a-záéíóúñü]+", node.value.lower()))
                if missing := words & need:
                    bad.append(f"{path.name}:{node.lineno} {sorted(missing)} {node.value[:60]!r}")
    assert bad == []


# Cabeceras del modelo sin relación con nada (ERRORES.md, 2026-11-14: «[Noche]» a todo).
@pytest.mark.parametrize(
    ("display", "secondary", "spoken", "asked", "want"),
    [
        ("Noche", "", "¡Guau guau! ¿Qué tal, amigo?", "Hazme la voz de un perro.", True),
        ("Noche", "", "Hoy es sábado 14 de noviembre de 2026.", "¿Qué día es hoy?", True),
        ("Partida", "", "Eso lo decido yo.", "¿Cuál es mi P?", True),
        # Tienen que ver con lo dicho o con lo pedido: se quedan.
        ("Fidelidad", "koden", "En japonés se dice koden.", "¿Cómo se dice fidelidad?", False),
        ("Buenas noches", "", "Que descanses.", "Buenas noches, Nyx", False),
        ("Toca descansar", "", "Descansa, que mañana madrugas.", "Me voy a dormir", False),
        ("Un agujero negro", "", "Un agujero negro es una región…", "¿Qué es?", False),
        # Números y cabeceras largas no se miran.
        ("3 %", "probabilidad de lluvia", "Mañana, un tres por ciento.", "¿Lloverá?", False),
        ("Aún no sé hacer eso", "", "Puedo abrirte la app.", "Tweet.", False),
        ("IP", "", "Tu IP es esta.", "¿Cuál es mi IP?", False),
        # Un número que no sale en lo dicho (registros del 2026-11-15).
        (
            "18 %",
            "uso de CPU",
            "Deshago eso y te desmuto el micrófono.",
            "Quiero que me desmutes el micrófono.",
            True,
        ),
        ("17 °C", "", "Son 17 grados en Madrid.", "¿Qué tiempo hace?", False),
    ],
)
def test_unrelated(display: str, secondary: str, spoken: str, asked: str, want: bool) -> None:
    assert unrelated(display, secondary, spoken, asked) is want


def test_tidy_replaces_an_unrelated_header() -> None:
    spoken = "El aire dispersa más la luz azul. Por eso lo ves así."
    assert tidy("Noche", "", spoken, "¿Por qué el cielo es azul?") == (
        "El aire dispersa más la luz azul.",
        "",
    )
    # Sin saber qué se pidió (avisos, alarmas), no se toca.
    assert tidy("Noche", "", spoken) == ("Noche", "")
