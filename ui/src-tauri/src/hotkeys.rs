//! Atajos globales (SPEC secciones 3 y 4). Configurables en la fase 5.
//!
//! - Win+Alt+N: campo de texto para escribir a Nyx.
//! - Win+Alt+H: hablar. Un toque escucha hasta que te calles; mantenerlo escucha mientras
//!   lo mantienes. El evento llega a la isla, que lo reenvía al núcleo por el WebSocket.

use tauri::plugin::TauriPlugin;
use tauri::{AppHandle, Emitter, Runtime};
use tauri_plugin_global_shortcut::{
    Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutEvent, ShortcutState,
};

use crate::input;

fn text_shortcut() -> Shortcut {
    Shortcut::new(Some(Modifiers::SUPER | Modifiers::ALT), Code::KeyN)
}

fn talk_shortcut() -> Shortcut {
    Shortcut::new(Some(Modifiers::SUPER | Modifiers::ALT), Code::KeyH)
}

pub fn plugin<R: Runtime>() -> TauriPlugin<R> {
    tauri_plugin_global_shortcut::Builder::new()
        .with_handler(handle::<R>)
        .build()
}

fn handle<R: Runtime>(app: &AppHandle<R>, shortcut: &Shortcut, event: ShortcutEvent) {
    let pressed = matches!(event.state(), ShortcutState::Pressed);
    if shortcut.id() == talk_shortcut().id() {
        let _ = app.emit("hotkey://talk", pressed);
    } else if shortcut.id() == text_shortcut().id() && pressed {
        input::show(app);
    }
}

/// Si otra app ya usa un atajo, Nyx arranca igual y lo avisa en el registro.
pub fn register(app: &AppHandle) {
    let shortcuts = [
        ("escribir", "Win+Alt+N", text_shortcut()),
        ("hablar", "Win+Alt+H", talk_shortcut()),
    ];
    for (what, keys, shortcut) in shortcuts {
        if let Err(err) = app.global_shortcut().register(shortcut) {
            eprintln!("[nyx] no se pudo registrar el atajo de {what} ({keys}): {err}");
        }
    }
}
