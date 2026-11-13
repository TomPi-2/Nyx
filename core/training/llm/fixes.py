"""Lo que rompió la ronda 2 (6.27, ronda 3): ejemplos escritos a mano para el LoRA.

La ronda 2 (`nyx-r2:7b`) mejoró mucho sin actuar nunca sin deber, pero falló 8 frases que el
modelo base acertaba (`docs/benchmarks/lora-6.27.md`, «En Ollama»). Aquí van frases **nuevas**
con la misma intención, nunca las de la batería ni de la reserva (lo comprueba
`make_dataset.excluded`):

- «ponme el X» es abrir (`open_app`), no traer delante una ventana;
- «la ventana del X» es `focus_window`, no colocarla;
- «está muy alto» es bajar el volumen, sin preguntar de qué app;
- «a las 5 de la tarde tengo…, avísame» es a esa hora, no media hora antes;
- `move_files` con la carpeta de origen (obligatoria) y el tipo de archivo;
- dos cambios de volumen son dos llamadas, cada una con sus argumentos;
- `app_action` solo con las acciones de su lista (`incognito`, no `new_incognito_window`);
- las notas: desde la 6.28 Nyx sí las guarda (`save_note`), y lo que guarda de lo que se le dice
  es una pregunta de privacidad (`nyx_info`).

Las carpetas, por su nombre (como en las semillas: nunca rutas del equipo).
"""

from __future__ import annotations

from typing import Any

Call = dict[str, Any]


def _c(tool: str, /, **arguments: Any) -> Call:
    return {"name": tool, "arguments": arguments}


# (frase, llamadas)
CALLS: list[tuple[str, list[Call]]] = [
    # «ponme el X» = abrir
    ("ponme el Spotify, anda", [_c("open_app", name="Spotify")]),
    ("ponme el Steam, porfa", [_c("open_app", name="Steam")]),
    ("ponme el WhatsApp un momento", [_c("open_app", name="WhatsApp")]),
    ("venga, ponme el Telegram", [_c("open_app", name="Telegram")]),
    ("ponme la calculadora, porfa", [_c("open_app", name="Calculadora")]),
    ("ponme el Word que tengo que escribir", [_c("open_app", name="Word")]),
    # «la ventana del X» = traerla delante
    ("cámbiame a la ventana del Word", [_c("focus_window", name="Word")]),
    ("vete a la ventana de Spotify", [_c("focus_window", name="Spotify")]),
    ("sácame la ventana del Excel delante", [_c("focus_window", name="Excel")]),
    ("quiero ir a la ventana de Steam", [_c("focus_window", name="Steam")]),
    ("cambia a la ventana del Explorador", [_c("focus_window", name="Explorador")]),
    # «está muy alto» = bajar
    ("esto suena demasiado fuerte", [_c("set_volume", change=-20)]),
    ("uf, qué alto está todo", [_c("set_volume", change=-20)]),
    ("me revienta los oídos el volumen", [_c("set_volume", change=-20)]),
    ("está altísima la música", [_c("set_volume", change=-20)]),
    ("se oye muy bajo, no me entero", [_c("set_volume", change=20)]),
    ("apenas se escucha nada", [_c("set_volume", change=20)]),
    # recordatorio a la hora dicha
    (
        "a las 6 de la tarde tengo dentista, avísame",
        [_c("set_alarm", time="18:00", label="dentista")],
    ),
    (
        "a las 4 de la tarde viene el fontanero, recuérdamelo",
        [_c("set_alarm", time="16:00", label="viene el fontanero")],
    ),
    (
        "a las 9 de la noche juega el Madrid, avísame",
        [_c("set_alarm", time="21:00", label="juega el Madrid")],
    ),
    (
        "mañana a las 10 de la mañana tengo una entrevista, avísame",
        [_c("set_alarm", time="10:00", day="tomorrow", label="entrevista")],
    ),
    (
        "a las 7 y media de la tarde tengo que llamar a mi madre, avísame",
        [_c("set_alarm", time="19:30", label="llamar a mi madre")],
    ),
    # move_files con su carpeta de origen
    (
        "pasa los vídeos del escritorio a Vídeos",
        [_c("move_files", folder="Escritorio", kind="videos", destination="Vídeos")],
    ),
    (
        "lleva las fotos de Descargas a Imágenes",
        [_c("move_files", folder="Descargas", kind="images", destination="Imágenes")],
    ),
    (
        "mete las imágenes del escritorio en la carpeta Imágenes",
        [_c("move_files", folder="Escritorio", kind="images", destination="Imágenes")],
    ),
    (
        "manda los documentos del escritorio a Documentos",
        [_c("move_files", folder="Escritorio", kind="documents", destination="Documentos")],
    ),
    (
        "pasa los PNG de Descargas al escritorio",
        [_c("move_files", folder="Descargas", extension="png", destination="Escritorio")],
    ),
    (
        "mueve las canciones de Descargas a Música",
        [_c("move_files", folder="Descargas", kind="audio", destination="Música")],
    ),
    # dos cambios de volumen, dos llamadas
    (
        "silencia el Chrome y sube el volumen general",
        [_c("set_volume", app="Chrome", mute=True), _c("set_volume", change=10)],
    ),
    (
        "quítale el sonido al Steam y baja un poco el volumen",
        [_c("set_volume", app="Steam", mute=True), _c("set_volume", change=-10)],
    ),
    (
        "baja el Chrome y sube el Discord",
        [_c("set_volume", app="Chrome", change=-10), _c("set_volume", app="Discord", change=10)],
    ),
    (
        "pon el Discord al 30 y el volumen general al 60",
        [_c("set_volume", app="Discord", level=30), _c("set_volume", level=60)],
    ),
    # app_action con su lista
    (
        "ábreme una ventana privada en Firefox",
        [_c("app_action", action="incognito", app="Firefox")],
    ),
    ("abre el modo incógnito del Edge", [_c("app_action", action="incognito", app="Edge")]),
    (
        "quiero navegar en privado en Chrome",
        [_c("app_action", action="incognito", app="Chrome")],
    ),
    ("ábreme una pestaña nueva en Firefox", [_c("app_action", action="new_tab", app="Firefox")]),
    (
        "vuelve a abrir la pestaña que he cerrado en Chrome",
        [_c("app_action", action="reopen_tab", app="Chrome")],
    ),
    # lo que Nyx guarda de lo que se le dice: privacidad
    ("¿grabas todo lo que hablo?", [_c("nyx_info", topic="privacidad")]),
    ("¿te quedas con lo que te cuento?", [_c("nyx_info", topic="privacidad")]),
    ("¿mandas lo que digo a algún sitio?", [_c("nyx_info", topic="privacidad")]),
    ("¿me estás escuchando todo el rato?", [_c("nyx_info", topic="privacidad")]),
    # notas (6.28)
    (
        "guárdame en una nota la lista: leche, huevos y pan",
        [_c("save_note", title="Lista de la compra", text="- Leche\n- Huevos\n- Pan")],
    ),
    (
        "hazme una nota con la contraseña del wifi de casa: gato1234",
        [_c("save_note", title="Wifi de casa", text="Contraseña del wifi de casa: gato1234")],
    ),
]

# (frase, respuesta con cabecera): lo que Nyx sí sabe hacer, contado sin actuar.
REPLIES: list[tuple[str, str]] = [
    (
        "¿sabes tomar notas?",
        "[Sí, en notas | Documentos › Notas de Nyx]\nSí. Dime «apunta en una nota que…» y la "
        "guardo en Documentos, en Notas de Nyx.",
    ),
    (
        "¿puedes apuntarme cosas para que no se me olviden?",
        "[Sí, en notas | Documentos › Notas de Nyx]\nClaro. Dime «apunta que…» y te lo guardo "
        "en una nota.",
    ),
    (
        "¿dónde guardas las notas que te pido?",
        "[Documentos › Notas de Nyx]\nEn tu carpeta Documentos, en Notas de Nyx, cada una en un "
        "archivo de texto con la fecha.",
    ),
]


def rows() -> list[tuple[str, dict[str, Any]]]:
    """(frase, mensaje del asistente) de las dos listas."""
    out: list[tuple[str, dict[str, Any]]] = []
    for text, calls in CALLS:
        out.append(
            (
                text,
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{"type": "function", "function": c} for c in calls],
                },
            )
        )
    for text, reply in REPLIES:
        out.append((text, {"role": "assistant", "content": reply}))
    return out
