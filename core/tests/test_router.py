import pytest

from nyx.brain.router import Miss, Route, parse_number, route
from nyx.index.service import SystemIndex


def call(text: str, index: SystemIndex) -> tuple[str, dict[str, object]]:
    result = route(text, index)
    assert isinstance(result, Route), f"{text!r} → {result!r}"
    assert len(result.calls) == 1
    return result.calls[0].name, result.calls[0].arguments


@pytest.mark.parametrize(
    ("text", "tool", "args"),
    [
        ("Abre Visual Studio Code.", "open_app", {"name": "Visual Studio Code"}),
        ("abre el vscode, por favor", "open_app", {"name": "Visual Studio Code"}),
        ("Lanza Spotify", "open_app", {"name": "Spotify"}),
        ("abre el lol", "open_app", {"name": "League of Legends"}),
        ("Abre la configuración del ratón", "open_settings", {"page": "raton"}),
        ("abre la configuración", "open_settings", {"page": ""}),
        ("abre los ajustes de sonido", "open_settings", {"page": "sonido"}),
        ("Abre YouTube", "open_url", {"target": "YouTube"}),
        ("Abre Claude en el navegador", "open_url", {"target": "Claude"}),
        ("abre marca.com", "open_url", {"target": "marca punto com"}),
        ("Sube el volumen", "set_volume", {"change": 10}),
        ("sube el volumen mucho", "set_volume", {"change": 20}),
        ("baja el volumen un poco", "set_volume", {"change": -10}),
        ("Sube el volumen al 40", "set_volume", {"level": 40}),
        ("pon el volumen al cuarenta y cinco", "set_volume", {"level": 45}),
        ("volumen 30", "set_volume", {"level": 30}),
        ("Silencia.", "set_volume", {"mute": True}),
        ("silencia discord", "set_volume", {"mute": True, "app": "Discord PTB"}),
        ("quita el silencio", "set_volume", {"mute": False}),
        ("Pausa la música", "media_control", {"action": "pause"}),
        ("reanuda", "media_control", {"action": "play"}),
        ("Pon algo de música", "media_control", {"action": "play", "music": True}),
        (
            "Sube el volumen en Spotify",
            "app_action",
            {"app": "Spotify", "action": "volume_up", "times": 1},
        ),
        (
            "baja mucho el volumen de spotify",
            "app_action",
            {"app": "Spotify", "action": "volume_down", "times": 2},
        ),
        ("baja el volumen de discord al 20", "set_volume", {"level": 20, "app": "Discord PTB"}),
        ("sube el volumen al 50 en spotify", "set_volume", {"level": 50, "app": "Spotify"}),
        ("Pon un temporizador de 5 minutos", "set_timer", {"minutes": 5}),
        ("temporizador de diez segundos", "set_timer", {"seconds": 10}),
        ("Avísame en media hora", "set_timer", {"minutes": 30}),
        ("avísame en 2 horas y media", "set_timer", {"hours": 2, "minutes": 30}),
        ("Pon una alarma a las 10:50", "set_alarm", {"time": "10:50"}),
        ("pon una alarma para las siete y media", "set_alarm", {"time": "07:30"}),
        ("Alarma a las 5 de la tarde", "set_alarm", {"time": "17:00"}),
        ("pon una alarma a las ocho menos cuarto", "set_alarm", {"time": "07:45"}),
        ("Despiértame mañana a las 8", "set_alarm", {"time": "08:00", "day": "tomorrow"}),
        ("despiértame a la una del mediodía", "set_alarm", {"time": "13:00"}),
        ("Siguiente canción", "media_control", {"action": "next"}),
        ("pon la anterior", "media_control", {"action": "previous"}),
        ("Haz una captura de pantalla", "screenshot", {"target": "current"}),
        ("captura del monitor principal", "screenshot", {"target": "primary"}),
        ("hazme una captura de todas las pantallas", "screenshot", {"target": "all"}),
        ("haz un pantallazo de esta ventana", "screenshot", {"target": "window"}),
        ("maximiza Chrome", "window_layout", {"action": "maximize", "name": "chrome"}),
        ("minimiza esta ventana", "window_layout", {"action": "minimize"}),
        ("pon Discord a la derecha", "window_layout", {"action": "right", "name": "discord"}),
        ("mueve esta ventana al otro monitor", "window_layout", {"action": "next_monitor"}),
        ("cambia a Chrome", "focus_window", {"name": "chrome"}),
        ("pasa a Discord", "focus_window", {"name": "discord"}),
    ],
)
async def test_routes(index: SystemIndex, text: str, tool: str, args: dict[str, object]) -> None:
    assert call(text, index) == (tool, args)


async def test_open_folder_uses_its_path(index: SystemIndex) -> None:
    name, args = call("abre Descargas", index)
    assert name == "open_path"
    assert str(args["target"]).endswith("Descargas")


@pytest.mark.parametrize(
    "text",
    [
        "¿Qué hora es?",
        "¿Cómo se dice hola en alemán?",
        "Abre el bloc de notas y abre una nueva pestaña",  # varios pasos: LLM (3c)
        "pon el volumen al 300",
    ],
)
async def test_goes_to_llm(index: SystemIndex, text: str) -> None:
    assert route(text, index) is None


async def test_unknown_app_is_a_miss_with_suggestion(index: SystemIndex) -> None:
    result = route("abre photoshop", index)
    assert isinstance(result, Miss)
    assert result.target == "photoshop"


@pytest.mark.parametrize(
    ("text", "value"),
    [("40", 40), ("cuarenta", 40), ("cuarenta y cinco", 45), ("cien", 100), ("setenta y dos", 72)],
)
def test_parse_number(text: str, value: int) -> None:
    assert parse_number(text) == value


@pytest.mark.parametrize(
    ("text", "tool"),
    [
        ("abre Discord en segundo plano", "open_app"),
        ("abre Spotify sin enfocarlo", "open_app"),
        ("abre YouTube de fondo", "open_url"),
        ("abre Descargas sin cambiar de ventana", "open_path"),
    ],
)
async def test_background_opens_without_focus(index: SystemIndex, text: str, tool: str) -> None:
    name, args = call(text, index)
    assert name == tool
    assert args["focus"] is False


async def test_focus_is_default(index: SystemIndex) -> None:
    assert "focus" not in call("abre Discord", index)[1]  # la herramienta enfoca por defecto


@pytest.mark.parametrize(
    ("text", "tool", "args"),
    [
        ("Deshaz", "undo", {}),
        ("deshazlo", "undo", {}),
        ("Cierra Spotify", "close_app", {"name": "spotify"}),
        ("cierra esta ventana", "close_app", {}),
        (
            "Crea una carpeta en Documentos llamada Fondos.",
            "create_folder",
            {"name": "Fondos", "parent": "documentos"},
        ),
        (
            "crea una carpeta llamada Fotos Viaje en el escritorio",
            "create_folder",
            {"name": "Fotos Viaje", "parent": "el escritorio"},
        ),
        (
            "Mueve los últimos 5 archivos de Descargas a Documentos",
            "move_files",
            {"folder": "descargas", "destination": "documentos", "newest": 5},
        ),
        (
            "mueve las tres últimas fotos de descargas a imágenes",
            "move_files",
            {"folder": "descargas", "destination": "imagenes", "newest": 3, "kind": "images"},
        ),
        (
            "copia los 2 últimos pdf de descargas a documentos",
            "copy_files",
            {"folder": "descargas", "destination": "documentos", "newest": 2, "extension": "pdf"},
        ),
        (
            "mueve el último archivo de descargas al escritorio",
            "move_files",
            {"folder": "descargas", "destination": "escritorio", "newest": 1},
        ),
        (
            "Borra los últimos 3 archivos de Descargas",
            "delete_files",
            {"folder": "descargas", "newest": 3},
        ),
        (
            "elimina el archivo factura de descargas",
            "delete_files",
            {"folder": "descargas", "names": ["factura"]},
        ),
        ("Busca la factura de la luz", "find_files", {"query": "factura de la luz"}),
        ("busca fotos de la playa", "find_files", {"query": "la playa", "kind": "images"}),
        ("¿Qué hay en Descargas?", "list_files", {"folder": "descargas"}),
        (
            "enséñame los últimos 5 archivos de descargas",
            "list_files",
            {"folder": "descargas", "newest": 5},
        ),
    ],
)
async def test_file_routes(
    index: SystemIndex, text: str, tool: str, args: dict[str, object]
) -> None:
    assert call(text, index) == (tool, args)


async def test_delete_folder_by_name(index: SystemIndex) -> None:
    name, args = call("Elimina la carpeta Fondos", index)
    assert name == "delete_files"
    assert args["names"] == ["Fondos"] and args["include_folders"] is True
    assert str(args["folder"]).endswith("Imagenes")


@pytest.mark.parametrize("text", ["busca recetas en google", "cierra sesión"])
async def test_file_routes_left_for_later(index: SystemIndex, text: str) -> None:
    assert route(text, index) is None


async def test_la_carpeta_de(index: SystemIndex) -> None:
    name, args = call(
        "mueve los dos últimos archivos de la carpeta de descargas a la carpeta de documentos",
        index,
    )
    assert name == "move_files"
    assert args["folder"] == "descargas" and args["destination"] == "documentos"


@pytest.mark.parametrize("text", ["recupéralo", "recupera el archivo de la papelera", "restáuralo"])
async def test_restore_means_undo(index: SystemIndex, text: str) -> None:
    assert call(text, index) == ("undo", {})


@pytest.mark.parametrize("open_now", [True, False])
def test_new_tab_in_app(
    index: SystemIndex, monkeypatch: pytest.MonkeyPatch, open_now: bool
) -> None:
    from nyx.brain import router as router_module

    monkeypatch.setattr(
        router_module, "_find_windows", lambda name, process: [1] if open_now else []
    )
    result = route("Abre una nueva pestaña dentro del bloc de notas", index)
    assert isinstance(result, Route)
    call = result.calls[0]
    if open_now:  # ya abierto: Ctrl+T en su ventana
        assert (call.name, call.arguments) == (
            "app_action",
            {"action": "new_tab", "app": "Bloc de notas"},
        )
    else:  # abrirlo ya deja una pestaña nueva
        assert (call.name, call.arguments["name"]) == ("open_app", "Bloc de notas")


@pytest.mark.parametrize(
    "text",
    ["Pasa la siguiente canción en Spotify.", "pasa a la siguiente", "canción anterior en spotify"],
)
def test_media_with_app_suffix(index: SystemIndex, text: str) -> None:
    result = route(text, index)
    assert isinstance(result, Route) and result.calls[0].name == "media_control"


@pytest.mark.parametrize(
    ("text", "action", "app"),
    [
        ("cierra esta pestaña", "close_tab", None),
        ("reabre la última pestaña cerrada", "reopen_tab", None),
        ("recarga la página", "reload", None),
        ("abre una ventana de incógnito", "incognito", None),
        ("silencia el micro en Discord", "toggle_mute", "Discord"),
        ("ensordéceme", "toggle_deafen", "Discord"),
    ],
)
def test_in_app_actions(index: SystemIndex, text: str, action: str, app: str | None) -> None:
    result = route(text, index)
    assert isinstance(result, Route)
    call = result.calls[0]
    assert call.name == "app_action" and call.arguments["action"] == action
    assert call.arguments.get("app") == app


@pytest.mark.parametrize(
    ("text", "refused"),
    [
        ("vacía la papelera", True),
        ("borra los archivos de descargas para siempre", True),
        ("escribe en el chat del Valorant que voy", True),
        ("abre el Valorant", False),
        ("borra el último archivo de descargas", False),
    ],
)
def test_refusals(index: SystemIndex, text: str, refused: bool) -> None:
    from nyx.brain.router import refusal

    assert (refusal(text, index) is not None) is refused


@pytest.mark.parametrize(
    ("text", "tool"),
    [
        ("abre Spotify y maximízalo", None),  # varios pasos → LLM
        ("pon Chrome a la izquierda y Discord a la derecha", "window_layout"),
        ("pon el aleatorio en Spotify", "app_action"),
        ("dale a me gusta a esta canción", "app_action"),
        ("busca un canal en Discord", None),
        ("guarda el documento del bloc de notas", "app_action"),
        ("pantalla completa", "app_action"),
    ],
)
def test_battery_fixes(index: SystemIndex, text: str, tool: str | None) -> None:
    result = route(text, index)
    if tool is None:
        assert result is None
    else:
        assert isinstance(result, Route) and result.calls[0].name == tool


@pytest.mark.parametrize(
    "text",
    [
        "Para el vídeo de YouTube.",
        "Pausa el vídeo de YouTube.",
        "reanuda el vídeo de YouTube",
        "dale al play en Spotify",
    ],
)
def test_media_with_source(index: SystemIndex, text: str) -> None:
    result = route(text, index)
    assert isinstance(result, Route)
    args = result.calls[0].arguments
    assert args["action"] in ("pause", "play")
    assert args["source"] in ("youtube", "spotify")


@pytest.mark.parametrize(
    ("text", "refused"),
    [
        # ERRORES.md, 2026-11-11: en partida no hace falta nombrar el juego.
        ("Quiero que saltes y tires hacia adelante el coche.", True),
        ("acelera", True),
        ("dispara a ese", True),
        ("juega por mí", True),
        ("sube el volumen", False),
        ("pon música", False),
        ("mueve Discord al otro monitor", False),
        ("¿qué hora es?", False),
        ("abre el correo", False),
    ],
)
def test_refusals_while_playing(index: SystemIndex, text: str, refused: bool) -> None:
    from nyx.brain.router import refusal

    assert (refusal(text, index, playing=True) is not None) is refused
    # Sin partida, solo cuenta lo que nombra un juego.
    assert refusal("salta", index) is None


def test_focus_only_for_real_windows_or_apps(
    index: SystemIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nyx.brain import router as router_module

    monkeypatch.setattr(router_module, "_find_windows", lambda name, process: [])
    result = route("muéstrame los FPS en el Rocket League", index)
    assert not (isinstance(result, Route) and result.calls[0].name == "focus_window")
    assert call("ve a Discord", index)[0] == "focus_window"


def test_short_names_are_not_fuzzy(index: SystemIndex) -> None:
    # «Ábrela» dejaba «la», que se parecía a «Calculadora» (ERRORES.md, 2026-11-11).
    assert index.confident(index.resolve("la")) is None
    assert index.confident(index.resolve("chrome")) is not None


@pytest.mark.parametrize(
    "text",
    ["¿qué tienes pendiente?", "¿Qué hay pendiente?", "Dime, Nix, ¿qué tienes pendiente ahora?"],
)
def test_pending_rules(index: SystemIndex, text: str) -> None:
    assert call(text, index) == ("pending", {"action": "list"})
    assert call("olvida lo pendiente", index) == ("pending", {"action": "cancel"})


def test_several_orders_in_one_request(index: SystemIndex, monkeypatch: pytest.MonkeyPatch) -> None:
    # ERRORES.md, 2026-11-11: «abre Discord, abre tus ajustes y…» era una sola app.
    from nyx.brain import router as router_module

    monkeypatch.setattr(router_module, "_find_windows", lambda name, process: [])
    result = route("Abre Discord, abre tus ajustes y pon música", index)
    assert isinstance(result, Route)
    assert [c.name for c in result.calls] == ["open_app", "open_nyx_settings", "media_control"]
    # Si una no la entienden las reglas, se encarga el LLM de la frase entera.
    assert (
        route("Abre Discord, abre tus ajustes y muéstrame los FPS en el Rocket League", index)
        is None
    )
    # No se parte lo que no empieza por un verbo.
    assert isinstance(route("Dime, Nix, ¿qué tienes pendiente?", index), Route)


def test_resume_is_not_music(index: SystemIndex) -> None:
    # «Reanuda» sigue lo que sonaba; «pon música» va a la app de música (Spotify).
    assert call("reanuda", index) == ("media_control", {"action": "play"})
    assert call("pon música de YouTube", index) == (
        "media_control",
        {"action": "play", "source": "youtube"},
    )


@pytest.mark.parametrize(
    "text",
    ["abre la", "ábrela", "abre eso", "abre la que has creado", "abre la carpeta de antes"],
)
def test_references_go_to_the_llm(index: SystemIndex, text: str) -> None:
    # Whisper oye «ábrela» como «abre la»: no es una app llamada «la» (ERRORES.md, 2026-11-11).
    assert route(text, index) is None


@pytest.mark.parametrize(
    ("text", "refused"),
    [
        ("compra unas zapatillas en Amazon", True),
        ("¿puedes comprarme el juego en Steam?", True),
        ("paga la factura de la luz", True),
        ("hazme un pedido en Glovo", True),
        ("transfiere 20 euros a Laura", True),
        ("busca la factura de la luz", False),
        ("abre Amazon", False),
        ("¿cuánto cuesta un iPhone?", False),
    ],
)
def test_money_is_always_refused(index: SystemIndex, text: str, refused: bool) -> None:
    from nyx.brain.router import refusal

    assert (refusal(text, index) is not None) is refused


@pytest.mark.parametrize(
    "text",
    ["¿qué alarmas tengo?", "¿tengo alguna alarma puesta?", "¿cuánto le queda al temporizador?"],
)
def test_alarm_questions_use_the_tool(index: SystemIndex, text: str) -> None:
    assert call(text, index) == ("list_alarms", {})


@pytest.mark.parametrize(
    ("text", "args"),
    [
        (
            "recuérdame a las 6 de la tarde llamar a mamá",
            {"time": "18:00", "label": "llamar a mamá"},
        ),
        (
            "Recuérdame llamar a mamá a las 6 de la tarde",
            {"time": "18:00", "label": "llamar a mamá"},
        ),
        (
            "recuérdame mañana a las 8 que tengo dentista",
            {"time": "08:00", "day": "tomorrow", "label": "tengo dentista"},
        ),
        ("avísame a las 10 y media de sacar la ropa", {"time": "10:30", "label": "sacar la ropa"}),
    ],
)
def test_reminders_by_rule(index: SystemIndex, text: str, args: dict[str, object]) -> None:
    # 6.03: con más herramientas, el 7B escribía «pon una alarma…» como texto.
    assert call(text, index) == ("set_alarm", args)


@pytest.mark.parametrize(
    "text",
    [
        "¿qué puedes hacer?",
        "¿qué cosas no haces nunca?",
        "¿quién eres?",
        "explícame tu configuración para el modo partida",
        "¿cómo funciona tu modo partida?",
    ],
)
def test_questions_about_nyx_use_nyx_info(index: SystemIndex, text: str) -> None:
    name, args = call(text, index)
    assert name == "nyx_info" and args["topic"]


@pytest.mark.parametrize(
    ("text", "which"),
    [
        ("cancela el temporizador", "temporizador"),
        ("quita la alarma de las 7", "7"),
        ("borra las alarmas", "todas"),
        ("elimina el recordatorio de llamar a mamá", "llamar a mama"),
    ],
)
def test_cancel_alarms_by_rule(index: SystemIndex, text: str, which: str) -> None:
    assert call(text, index) == ("cancel_alarm", {"which": which})


def test_alarm_in_seconds_is_a_timer(index: SystemIndex) -> None:
    # 6.03: el LLM puso «una alarma que suene en 10 segundos» a las 00:10.
    assert call("pon una alarma que suene en 10 segundos", index) == (
        "set_timer",
        {"seconds": 10},
    )
    assert call("pon una alarma dentro de 5 minutos", index) == ("set_timer", {"minutes": 5})


@pytest.mark.parametrize(
    ("text", "args"),
    [
        ("¿va a llover mañana?", {}),
        ("¿qué temperatura hace?", {}),
        ("¿qué tiempo hace hoy?", {}),
        ("¿qué tiempo hace en Madrid?", {"city": "Madrid"}),
        ("¿va a llover mañana en Sevilla?", {"city": "Sevilla"}),
        ("¿qué tiempo hará en Valencia mañana?", {"city": "Valencia"}),
        ("¿hace falta paraguas hoy en Bilbao?", {"city": "Bilbao"}),
        ("¿hace frío afuera?", {}),
    ],
)
def test_weather_by_rule(index: SystemIndex, text: str, args: dict[str, object]) -> None:
    assert call(text, index) == ("get_weather", args)


@pytest.mark.parametrize(
    ("text", "what"),
    [
        ("¿cuánta batería me queda?", "battery"),
        ("¿está enchufado el portátil?", "battery"),
        ("¿cuánta CPU estoy usando?", "cpu"),
        ("¿a cuánto está el procesador?", "cpu"),
        ("¿cuánta RAM uso?", "ram"),
        ("¿cuánta memoria RAM me queda?", "ram"),
        ("¿cuánto espacio me queda?", "disk"),
        ("¿cuánto espacio libre tengo en el disco?", "disk"),
        ("¿qué consume más CPU?", "top"),
        ("¿qué programa consume más?", "top"),
    ],
)
def test_system_info_by_rule(index: SystemIndex, text: str, what: str) -> None:
    assert call(text, index) == ("system_info", {"what": what})


@pytest.mark.parametrize(
    ("text", "tool", "args"),
    [
        ("¿qué tengo copiado?", "clipboard", {"action": "read"}),
        ("¿qué hay en el portapapeles?", "clipboard", {"action": "read"}),
        ("traduce lo que he copiado", "clipboard", {"action": "read"}),
        ("resume lo copiado", "clipboard", {"action": "read"}),
        ("corrige la ortografía de lo copiado", "clipboard", {"action": "read"}),
        (
            "copia hola mundo al portapapeles",
            "clipboard",
            {"action": "write", "text": "hola mundo"},
        ),
        ("escribe: llego en 10 minutos", "type_text", {"text": "llego en 10 minutos"}),
        ("escribe hola qué tal", "type_text", {"text": "hola qué tal"}),
    ],
)
def test_clipboard_and_type_text_by_rule(
    index: SystemIndex, text: str, tool: str, args: dict[str, object]
) -> None:
    assert call(text, index) == (tool, args)


@pytest.mark.parametrize(
    ("text", "tool", "args"),
    [
        ("baja el brillo", "set_brightness", {"change": -20}),
        ("sube mucho el brillo", "set_brightness", {"change": 40}),
        ("pon el brillo al 50", "set_brightness", {"level": 50}),
        ("pon el brillo al máximo", "set_brightness", {"level": 100}),
        ("apaga el bluetooth", "toggle_bluetooth", {"enabled": False}),
        ("activa el bluetooth", "toggle_bluetooth", {"enabled": True}),
        ("desactiva el wifi", "toggle_wifi", {"enabled": False}),
        ("enciende el wifi", "toggle_wifi", {"enabled": True}),
        ("bloquea el PC", "system_power", {"action": "lock"}),
        ("suspende el ordenador", "system_power", {"action": "sleep"}),
        ("reinicia el equipo", "system_power", {"action": "restart"}),
        ("apaga el ordenador", "system_power", {"action": "shutdown"}),
    ],
)
def test_brightness_power_and_radios_by_rule(
    index: SystemIndex, text: str, tool: str, args: dict[str, object]
) -> None:
    assert call(text, index) == (tool, args)


@pytest.mark.parametrize(
    ("text", "tool", "args"),
    [
        ("¿qué suena?", "now_playing", {}),
        ("¿qué está sonando ahora en Spotify?", "now_playing", {}),
        ("¿qué canción es esta?", "now_playing", {}),
        ("¿quién canta esto?", "now_playing", {}),
        ("empieza un cronómetro", "stopwatch", {"action": "start"}),
        ("inicia el cronómetro", "stopwatch", {"action": "start"}),
        ("¿cuánto lleva?", "stopwatch", {"action": "status"}),
        ("¿cuánto lleva el cronómetro?", "stopwatch", {"action": "status"}),
        ("para el cronómetro", "stopwatch", {"action": "stop"}),
        ("cambia la salida de audio", "audio_output", {}),
        ("pon el sonido en los auriculares", "audio_output", {"device": "auriculares"}),
        (
            "pon una alarma todos los días a las 7",
            "set_alarm",
            {"time": "07:00", "repeat": "daily"},
        ),
        (
            "pon una alarma todos los días laborables a las 7",
            "set_alarm",
            {"time": "07:00", "repeat": "weekdays"},
        ),
        (
            "despiértame de lunes a viernes a las 7 y media",
            "set_alarm",
            {"time": "07:30", "repeat": "weekdays"},
        ),
        (
            "alarma a las 9 los fines de semana",
            "set_alarm",
            {"time": "09:00", "repeat": "weekends"},
        ),
        (
            "recuérdame todos los días a las 21:00 tomar la pastilla",
            "set_alarm",
            {"time": "21:00", "label": "tomar la pastilla", "repeat": "daily"},
        ),
    ],
)
def test_music_and_time_by_rule(
    index: SystemIndex, text: str, tool: str, args: dict[str, object]
) -> None:
    assert call(text, index) == (tool, args)
