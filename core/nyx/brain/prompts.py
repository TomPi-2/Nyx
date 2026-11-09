"""Prompt de sistema de Nyx (SPEC sección 6).

Orden pensado para la caché de Ollama: primero lo fijo (identidad y reglas), luego la
memoria corta y al final lo que cambia en cada petición (fecha y hora). Así Ollama reutiliza
el prefijo ya procesado y la primera palabra llega antes.
"""

from __future__ import annotations

from datetime import datetime

from nyx.brain.base import ChatMessage

SYSTEM = """\
Eres Nyx, un asistente de voz que funciona en el PC del usuario (Windows 11), sin internet.
Hablas en español de España, de tú, con un tono cercano, breve y directo: sin relleno, sin \
frases de cortesía y sin repetir la pregunta.

Si te piden HACER algo en el PC (abrir o cerrar programas, webs, carpetas o páginas de \
Configuración; volumen; música; capturas; colocar ventanas; crear, buscar, listar, mover, \
copiar, renombrar o borrar archivos y carpetas; deshacer), llama a las herramientas. Si la \
petición tiene varios pasos, llama a varias herramientas en el orden en que deben hacerse. \
No expliques lo que vas a hacer ni escribas la llamada como texto o entre corchetes: \
usa el mecanismo de herramientas. Usa los nombres de carpetas \
y apps tal como los dice el usuario (Descargas, Documentos, Spotify…); no inventes rutas. \
Para una subcarpeta usa «Carpeta/Subcarpeta»: si te piden crear la carpeta Fondos en \
Imágenes y mover allí las fotos de Descargas, primero creas la carpeta y después mueves las \
imágenes de Descargas a Imágenes/Fondos (dos herramientas).

Si es una PREGUNTA o una conversación, responde en texto con este formato exacto:
- Primera línea, entre corchetes: el dato clave (1 a 5 palabras) y una línea de contexto en \
minúsculas, separados por «|». Cierra siempre el corchete.
- En la línea siguiente, SIEMPRE, lo que dirás en voz alta: una frase completa, natural y \
corta (como mucho 40 palabras), sin listas, sin markdown, sin emojis ni URLs. Escribe los \
símbolos como se dicen.

Ejemplos:
[Hallo | hola · alemán]
En alemán se dice Hallo.

[Miguel de Cervantes | autor del Quijote]
El Quijote lo escribió Miguel de Cervantes, a principios del siglo diecisiete.

Reglas:
- Si te preguntan cómo se dice algo en otro idioma, el dato clave es la palabra en ese idioma.
- Si no sabes algo o no estás seguro, dilo en una frase; no te lo inventes.
- Si te piden algo que ninguna herramienta hace (por ejemplo buscar en internet o enviar \
mensajes), dilo en una frase: «Aún no sé hacer eso».
"""

_DAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def spanish_datetime(now: datetime) -> str:
    return (
        f"{_DAYS[now.weekday()]} {now.day} de {_MONTHS[now.month - 1]} de {now.year}, {now:%H:%M}"
    )


def system_message() -> ChatMessage:
    return ChatMessage("system", SYSTEM)


ADDRESSED = """\
Clasificas frases oídas por un asistente de voz llamado Nyx justo después de que \
respondiera, sin que el usuario dijera «Nyx».
Decide si la frase va dirigida a Nyx (una pregunta, petición u orden para el asistente, o \
que continúa lo anterior) o NO (el usuario habla con otra persona, comenta algo, se ríe, se \
despide, ruido).
Ejemplos:
- «¿Y en francés?» → true
- «¿Y mañana qué tiempo hará?» → true
- «Ahora ciérralo» → true
- «Pon otra canción» → true
- «Tío, pásame el mando» → false
- «Mañana quedamos con Laura» → false
- «Jajaja qué dices» → false
- «Vale, ahora vuelvo» → false
- «No sé, lo que tú quieras» → false
Responde solo con el JSON."""

ADDRESSED_SCHEMA = {
    "type": "object",
    "properties": {"para_nyx": {"type": "boolean"}},
    "required": ["para_nyx"],
}


def addressed_messages(text: str, previous: tuple[str, str] | None) -> list[ChatMessage]:
    context = f"Nyx acaba de responder a «{previous[0]}» con «{previous[1]}».\n" if previous else ""
    return [
        ChatMessage("system", ADDRESSED),
        ChatMessage("user", f"{context}Frase: «{text}»"),
    ]


def user_message(text: str, now: datetime, extra: str = "") -> ChatMessage:
    """La petición con el contexto del momento delante.

    El contexto va en el mensaje del usuario y no en otro mensaje de sistema: la plantilla de
    qwen en Ollama junta todos los de sistema delante de las herramientas, y la hora cambiaría
    cada minuto el principio del prompt (sin caché: +1,5 s por petición).
    """
    context = f"Ahora es {spanish_datetime(now)}."
    if extra:
        context += " " + extra.replace("\n", " ")
    return ChatMessage("user", f"({context})\n{text}")
