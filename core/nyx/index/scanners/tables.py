"""Tablas fijas: páginas de Configuración (ms-settings:) y webs frecuentes (SPEC sección 10).

La tabla de webs será editable desde Ajustes en la fase 5; los alias del usuario ya se
guardan en la caché.
"""

from __future__ import annotations

from nyx.index.aliases import generate
from nyx.index.model import Entry, Kind, Launch, LaunchKind

# (URI, nombre, alias)
SETTINGS_PAGES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("ms-settings:", "Configuración", ("ajustes", "configuracion de windows", "settings")),
    ("ms-settings:display", "Pantalla", ("resolucion", "escala", "monitores", "monitor")),
    ("ms-settings:display-advancedgraphics", "Gráficos", ("graficos", "configuracion de graficos")),
    ("ms-settings:nightlight", "Luz nocturna", ("filtro de luz azul",)),
    ("ms-settings:sound", "Sonido", ("audio", "altavoces", "microfono", "sonidos")),
    ("ms-settings:apps-volume", "Mezclador de volumen", ("mezclador", "volumen de las apps")),
    ("ms-settings:notifications", "Notificaciones", ("no molestar",)),
    ("ms-settings:powersleep", "Energía", ("suspension", "inicio apagado y suspension", "energia")),
    ("ms-settings:batterysaver", "Batería", ("ahorro de bateria", "bateria")),
    ("ms-settings:storagesense", "Almacenamiento", ("espacio en disco", "disco", "discos")),
    ("ms-settings:multitasking", "Multitarea", ("ventanas", "acoplar ventanas")),
    ("ms-settings:clipboard", "Portapapeles", ("historial del portapapeles",)),
    ("ms-settings:about", "Información del sistema", ("acerca de", "especificaciones", "mi pc")),
    ("ms-settings:bluetooth", "Bluetooth", ("dispositivos bluetooth", "dispositivos")),
    ("ms-settings:printers", "Impresoras", ("impresora", "escaner")),
    ("ms-settings:mousetouchpad", "Ratón", ("mouse", "raton", "touchpad", "panel tactil")),
    ("ms-settings:typing", "Escritura", ("teclado", "autocorreccion")),
    ("ms-settings:usb", "USB", ()),
    ("ms-settings:network-status", "Red e internet", ("red", "internet", "conexion")),
    ("ms-settings:network-wifi", "Wifi", ("wi-fi", "wi fi", "redes wifi")),
    ("ms-settings:network-ethernet", "Ethernet", ("cable de red",)),
    ("ms-settings:network-vpn", "VPN", ()),
    ("ms-settings:network-proxy", "Proxy", ()),
    ("ms-settings:network-airplanemode", "Modo avión", ("modo avion",)),
    ("ms-settings:personalization", "Personalización", ("personalizar",)),
    ("ms-settings:personalization-background", "Fondo de pantalla", ("fondo", "wallpaper")),
    ("ms-settings:colors", "Colores", ("modo oscuro", "tema oscuro", "modo claro")),
    ("ms-settings:themes", "Temas", ("tema",)),
    ("ms-settings:lockscreen", "Pantalla de bloqueo", ("bloqueo",)),
    ("ms-settings:taskbar", "Barra de tareas", ("taskbar",)),
    ("ms-settings:appsfeatures", "Aplicaciones instaladas", ("aplicaciones", "desinstalar")),
    ("ms-settings:defaultapps", "Aplicaciones predeterminadas", ("navegador predeterminado",)),
    ("ms-settings:startupapps", "Aplicaciones de inicio", ("inicio automatico", "arranque")),
    ("ms-settings:yourinfo", "Cuenta", ("tu informacion", "cuentas", "mi cuenta")),
    ("ms-settings:signinoptions", "Inicio de sesión", ("contrasena", "pin", "windows hello")),
    ("ms-settings:dateandtime", "Fecha y hora", ("hora", "zona horaria", "reloj")),
    ("ms-settings:regionlanguage", "Idioma y región", ("idioma", "region")),
    ("ms-settings:gaming-gamebar", "Game Bar", ("barra de juegos", "xbox game bar")),
    ("ms-settings:gaming-gamemode", "Modo juego", ("modo de juego", "game mode")),
    ("ms-settings:easeofaccess", "Accesibilidad", ()),
    ("ms-settings:privacy", "Privacidad", ("privacidad y seguridad", "permisos")),
    ("ms-settings:privacy-microphone", "Permisos del micrófono", ("privacidad del microfono",)),
    ("ms-settings:privacy-webcam", "Cámara", ("webcam", "permisos de la camara")),
    ("ms-settings:windowsupdate", "Windows Update", ("actualizaciones", "actualizar windows")),
    ("ms-settings:recovery", "Recuperación", ("restablecer", "recuperacion")),
    ("ms-settings:activation", "Activación", ("activar windows", "licencia")),
)

# (URL, nombre, alias)
WEBSITES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("https://www.youtube.com", "YouTube", ("youtube", "yutub", "youtub")),
    ("https://claude.ai", "Claude", ("claude", "claud", "clod")),
    ("https://chatgpt.com", "ChatGPT", ("chat gpt", "chatgpt", "chat de openai")),
    ("https://mail.google.com", "Gmail", ("gmail", "correo", "mi correo", "el correo")),
    ("https://www.google.com", "Google", ("buscador",)),
    ("https://drive.google.com", "Google Drive", ("drive",)),
    ("https://maps.google.com", "Google Maps", ("maps", "mapas")),
    ("https://translate.google.com", "Traductor de Google", ("traductor", "google translate")),
    ("https://www.twitch.tv", "Twitch", ("twitch", "twich")),
    ("https://www.netflix.com", "Netflix", ()),
    ("https://www.primevideo.com", "Prime Video", ("amazon prime video",)),
    ("https://www.disneyplus.com", "Disney+", ("disney plus", "disney")),
    ("https://github.com", "GitHub", ("github", "git hub")),
    ("https://es.wikipedia.org", "Wikipedia", ("wikipedia", "la wikipedia")),
    ("https://www.amazon.es", "Amazon", ()),
    ("https://x.com", "X", ("twitter",)),
    ("https://www.instagram.com", "Instagram", ("insta",)),
    ("https://www.reddit.com", "Reddit", ()),
    ("https://web.whatsapp.com", "WhatsApp Web", ("whatsapp web",)),
    ("https://outlook.live.com", "Outlook", ("hotmail",)),
    ("https://www.linkedin.com", "LinkedIn", ("linkedin",)),
    ("https://www.tiktok.com", "TikTok", ("tik tok",)),
)


def scan_settings() -> list[Entry]:
    return [
        Entry(
            key=f"setting:{uri}",
            kind=Kind.SETTING,
            name=name,
            launch=Launch(LaunchKind.URI, uri),
            source="settings",
            aliases=generate(name, extra),
        )
        for uri, name, extra in SETTINGS_PAGES
    ]


def scan_websites() -> list[Entry]:
    return [
        Entry(
            key=f"web:{url}",
            kind=Kind.WEB,
            name=name,
            launch=Launch(LaunchKind.URI, url),
            source="websites",
            aliases=generate(name, extra),
        )
        for url, name, extra in WEBSITES
    ]
