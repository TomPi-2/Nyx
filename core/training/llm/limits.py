"""Cuándo NO actuar (6.27, ronda 2): ejemplos de respuesta en texto para el LoRA.

La ronda 1 enseñó a actuar y no a no actuar (solo un 20 % de respuestas en texto, casi todas
de cultura general). Resultado: actuaba de más («llama a mi hermano» → una llamada de WhatsApp
a un número inventado; «pídeme una pizza» → un temporizador; una herramienta `send_whatsapp`
que no existe). Aquí, escritas a mano y revisadas:

- `UNSUPPORTED`: cosas que ninguna herramienta hace → «Aún no sé hacer eso» (lo que pide el
  prompt de sistema), con una salida útil si la hay, sin hacer nada.
- `INFO`: preguntas que suenan a orden pero piden un dato («¿cuánto tarda en hervir un
  huevo?» no es un temporizador; «¿cómo se hace una captura?» no es hacerla).
- `SMALL_TALK`: saludos y charla corta («nada, déjalo» no deshace nada).

Ninguna frase es de la batería ni de la reserva (lo comprueba `make_dataset.excluded`). Los
datos de `INFO` son fijos y comprobados: nada que dependa de la fecha o de la hora.
"""

from __future__ import annotations

# (frases, cabecera, respuestas habladas): cada frase se combina con una respuesta distinta.
Entry = tuple[tuple[str, ...], str, tuple[str, ...]]

UNSUPPORTED: list[Entry] = [
    (
        (
            "escríbele a Laura por WhatsApp que llego en diez minutos",
            "mándale un mensaje a mi padre",
            "envíale un Telegram a Pablo diciendo que mañana no puedo",
            "dile a mi novia que ya voy de camino",
            "contesta al último mensaje que me han mandado",
        ),
        "[Aún no sé hacer eso | mensajes]",
        (
            "Aún no sé mandar mensajes. Si quieres, te abro WhatsApp y lo escribes tú.",
            "Mandar mensajes aún no sé. Puedo abrirte la app para que lo envíes tú.",
            "Eso todavía no lo sé hacer: no mando mensajes por ti.",
        ),
    ),
    (
        (
            "llama a mi abuela",
            "haz una videollamada con Carlos",
            "llama al número de la pizzería",
            "pon una llamada al trabajo",
        ),
        "[Aún no sé hacer eso | llamadas]",
        (
            "Aún no sé hacer llamadas. Puedo abrirte WhatsApp o Discord para que llames tú.",
            "Llamar todavía no sé. Si quieres, te abro la app y llamas tú.",
            "Eso aún no lo sé hacer: no hago llamadas.",
        ),
    ),
    (
        (
            "envía un email a recursos humanos pidiendo vacaciones",
            "responde al correo de Amazon",
            "mándale un correo a la profesora con el trabajo",
            "léeme los correos nuevos",
        ),
        "[Aún no sé hacer eso | correo]",
        (
            "Aún no sé usar tu correo. Si quieres, te lo abro y lo haces tú.",
            "El correo todavía no lo manejo. Puedo abrirte Gmail o Outlook.",
            "Eso aún no lo sé hacer: no leo ni envío correos.",
        ),
    ),
    (
        (
            "reserva una mesa para dos esta noche",
            "pide un taxi para dentro de media hora",
            "pídeme un Uber a casa",
            "reserva un vuelo a Roma para el viernes",
        ),
        "[Aún no sé hacer eso | reservas y pedidos]",
        (
            "Aún no sé hacer reservas ni pedidos. Puedo abrirte la web para que lo hagas tú.",
            "Eso todavía no lo sé hacer. Si quieres, te abro la página y reservas tú.",
            "Reservar o pedir cosas aún no sé hacerlo.",
        ),
    ),
    (
        (
            "sube esta foto a Twitter",
            "publica un tuit diciendo que he aprobado",
            "comenta en el último vídeo de mi canal",
            "dale like a la última publicación de Ana",
        ),
        "[Aún no sé hacer eso | redes sociales]",
        (
            "Aún no sé publicar en redes. Te abro la app si quieres y lo haces tú.",
            "Publicar o comentar todavía no sé. Puedo abrirte la web.",
            "Eso aún no lo sé hacer: no publico nada por ti.",
        ),
    ),
    (
        (
            "apúntame el dentista el martes en el calendario",
            "¿qué tengo en la agenda esta semana?",
            "añade una reunión al calendario el lunes a las diez",
        ),
        "[Aún no sé hacer eso | calendario]",
        (
            "Aún no sé usar tu calendario. Si es para que te avise, puedo ponerte una alarma.",
            "Tu agenda todavía no la veo. Un recordatorio sí te lo puedo poner.",
        ),
    ),
    (
        (
            "crea un documento de Word con la lista de invitados",
            "hazme un Excel con los gastos del mes",
            "crea un archivo de texto que se llame ideas",
            "genera un PDF con esto",
        ),
        "[Aún no sé hacer eso | crear archivos]",
        (
            "Aún no sé crear archivos. Si quieres, te abro el programa y lo escribes tú.",
            "Crear archivos todavía no sé. Puedo abrirte Word o el Bloc de notas.",
        ),
    ),
    (
        (
            "enciende la tele del salón",
            "abre la puerta del garaje",
            "pon el aire acondicionado a 24",
            "baja las persianas",
            "enciende la lavadora",
        ),
        "[Aún no sé hacer eso | aparatos de casa]",
        (
            "Aún no sé controlar los aparatos de casa: solo manejo este PC.",
            "Eso todavía no lo sé hacer. Lo de casa queda fuera de este PC.",
            "Aún no puedo: no tengo acceso a los aparatos de casa.",
        ),
    ),
]

INFO: list[Entry] = [
    (
        ("¿cuántos minutos tiene un día?", "¿cuántos minutos hay en un día entero?"),
        "[1.440 minutos | un día]",
        ("Un día tiene mil cuatrocientos cuarenta minutos.",),
    ),
    (
        ("¿cuántos segundos tiene una hora?", "¿cuántos segundos son una hora?"),
        "[3.600 segundos | una hora]",
        ("Una hora tiene tres mil seiscientos segundos.",),
    ),
    (
        ("¿cuántos segundos son 25 minutos?",),
        "[1.500 segundos | 25 minutos]",
        ("Veinticinco minutos son mil quinientos segundos.",),
    ),
    (
        ("cuenta hasta cinco", "cuenta del uno al cinco"),
        "[1, 2, 3, 4, 5 | contar]",
        ("Uno, dos, tres, cuatro y cinco.",),
    ),
    (
        ("cuenta hacia atrás desde cinco", "haz una cuenta atrás de cinco"),
        "[5, 4, 3, 2, 1 | cuenta atrás]",
        ("Cinco, cuatro, tres, dos, uno… ¡ya!",),
    ),
    (
        ("¿en Londres es una hora menos que aquí?", "¿qué diferencia horaria hay con Londres?"),
        "[Una hora menos | Londres · respecto a España]",
        ("Sí, en Londres es una hora menos que en la España peninsular.",),
    ),
    (
        (
            "¿cuántas horas de diferencia hay con Nueva York?",
            "¿Nueva York va por detrás de España?",
        ),
        "[6 horas menos | Nueva York · respecto a España]",
        ("En Nueva York van normalmente seis horas por detrás de la España peninsular.",),
    ),
    (
        ("¿cuánto tarda en hervir un huevo?", "¿cuánto tiempo se cuece un huevo duro?"),
        "[Unos 10 minutos | huevo duro]",
        ("Un huevo duro, unos diez minutos desde que hierve el agua; pasado por agua, unos tres.",),
    ),
    (
        ("¿cuánto dura un partido de fútbol?",),
        "[90 minutos | partido de fútbol]",
        ("Noventa minutos, en dos partes de cuarenta y cinco, más el descuento.",),
    ),
    (
        ("¿cómo se pone una alarma en el móvil?",),
        "[Desde la app Reloj | alarma en el móvil]",
        ("Abre la app Reloj del móvil, ve a Alarmas y toca el más para crear una.",),
    ),
    (
        (
            "¿cómo se hace una captura de pantalla en Windows?",
            "¿con qué teclas se hace un pantallazo?",
        ),
        "[Windows + Mayúsculas + S | captura en Windows]",
        ("Pulsa Windows, Mayúsculas y S a la vez y elige la zona. También te la puedo hacer yo.",),
    ),
    (
        ("¿cómo se maximiza una ventana con el teclado?",),
        "[Windows + flecha arriba | maximizar]",
        ("Con Windows y la flecha hacia arriba. Si quieres, te lo hago yo.",),
    ),
    (
        ("¿qué volumen es seguro para los oídos?", "¿a qué volumen es malo escuchar música?"),
        "[Por debajo del 60 % | regla 60/60]",
        ("Lo habitual es no pasar del sesenta por ciento del volumen más de una hora seguida.",),
    ),
    (
        ("¿cuántos gigas tiene un tera?",),
        "[1.024 gigas | un terabyte]",
        ("Un terabyte son mil veinticuatro gigas, o mil según cómo se cuente.",),
    ),
    (
        ("¿qué es mejor, Spotify o YouTube Music?",),
        "[Depende de lo que busques | Spotify o YouTube Music]",
        ("Spotify va mejor para listas y podcasts; YouTube Music, para versiones y directos.",),
    ),
    (
        ("dime un número del 1 al 10",),
        "[7 | número al azar]",
        ("El siete.",),
    ),
]

SMALL_TALK: list[Entry] = [
    (
        ("hola", "hola Nyx", "buenas"),
        "[¡Hola! | aquí estoy]",
        ("¡Hola! ¿Qué necesitas?", "¡Hola! Dime.", "¡Buenas! ¿En qué te ayudo?"),
    ),
    (
        ("buenos días", "buenos días Nyx"),
        "[¡Buenos días!]",
        ("¡Buenos días! ¿En qué te ayudo?", "¡Buenos días! ¿Qué tal has dormido?"),
    ),
    (
        ("buenas noches", "me voy a dormir, buenas noches"),
        "[Buenas noches | que descanses]",
        ("Buenas noches, que descanses.", "¡Que descanses! Hasta mañana."),
    ),
    (
        ("¿estás ahí?", "¿me escuchas?", "¿me oyes?"),
        "[Aquí estoy | te escucho]",
        ("Aquí estoy, dime.", "Sí, te escucho perfectamente."),
    ),
    (
        ("¿cómo estás?", "¿qué tal te va?"),
        "[Muy bien | ¿y tú?]",
        ("Muy bien, con ganas de ayudar. ¿Y tú?", "¡Genial! ¿Qué tal tú?"),
    ),
    (
        ("nada, déjalo", "olvídalo", "da igual, no importa", "nada, era una prueba"),
        "[Vale | sin problema]",
        ("Vale, aquí estaré.", "Sin problema.", "De acuerdo, cuando quieras."),
    ),
    (
        ("perdona", "perdona por gritarte"),
        "[No pasa nada]",
        ("No pasa nada.", "Tranquilidad, no pasa nada."),
    ),
    (
        ("eres muy lista", "qué bien lo haces"),
        "[¡Gracias! | hago lo que puedo]",
        ("¡Gracias! Hago lo que puedo.", "¡Me alegra oírlo!"),
    ),
    (
        ("jajaja", "qué gracia"),
        "[¡Jaja!]",
        ("¡Me alegra hacerte reír!", "¡Jaja! Para eso estoy."),
    ),
    (
        ("me aburro", "no sé qué hacer"),
        "[Te propongo algo | contra el aburrimiento]",
        (
            "¿Te cuento un chiste o te pongo algo de música?",
            "¿Jugamos a algo o te cuento una curiosidad?",
        ),
    ),
    (
        ("estoy cansadísimo", "qué día más largo"),
        "[Toca descansar]",
        (
            "Pues date un respiro. Si quieres, te pongo música tranquila.",
            "Ánimo, que ya queda menos.",
        ),
    ),
]


def rows() -> list[tuple[str, str]]:
    """(frase, respuesta con cabecera) de las tres listas, repartiendo las respuestas."""
    out: list[tuple[str, str]] = []
    for phrases, header, spoken in (*UNSUPPORTED, *INFO, *SMALL_TALK):
        for i, phrase in enumerate(phrases):
            out.append((phrase, f"{header}\n{spoken[i % len(spoken)]}"))
    return out


# Lo mismo que piden las herramientas inventadas, pero sin la herramienta en la lista: no se
# inventa la llamada (la ronda 1 llegó a llamar a `send_whatsapp`, que no existe).
WITHOUT_TOOL = "[Aún no sé hacer eso]\n{}"
WITHOUT_TOOL_SPOKEN = (
    "Aún no sé hacer eso.",
    "Eso todavía no lo sé hacer.",
    "Aún no puedo hacer eso desde aquí.",
)
