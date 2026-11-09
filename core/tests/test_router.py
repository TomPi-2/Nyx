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
        ("Pausa la música", "media_control", {"action": "play_pause"}),
        ("reanuda", "media_control", {"action": "play_pause"}),
        ("Pon algo de música", "media_control", {"action": "play_pause"}),
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
        "Recuérdame a las 10:50 llamar a mamá",
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
