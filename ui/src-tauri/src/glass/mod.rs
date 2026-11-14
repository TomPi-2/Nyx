//! Motor gráfico de cristal en la app: las órdenes de Tauri sobre el crate compartido
//! `nyx-glass` (crates/nyx-glass, que también usa el instalador) y la galería de ejemplos.

pub mod gallery;

use tauri::{Runtime, State, WebviewWindow};

pub use nyx_glass::{Engine, GlassOptions, Shape, init};

/// La ventana empieza a usar el cristal. Las estadísticas llegan en el evento `glass-stats`.
#[tauri::command]
pub fn glass_attach<R: Runtime>(
    window: WebviewWindow<R>,
    engine: State<'_, Engine>,
    options: GlassOptions,
) -> Result<(), String> {
    engine.attach(&window, options)
}

#[tauri::command]
pub fn glass_set_options<R: Runtime>(
    window: WebviewWindow<R>,
    engine: State<'_, Engine>,
    options: GlassOptions,
) {
    engine.set_options(window.label(), options);
}

#[tauri::command]
pub fn glass_set_shapes<R: Runtime>(
    window: WebviewWindow<R>,
    engine: State<'_, Engine>,
    shapes: Vec<Shape>,
) {
    engine.set_shapes(window.label(), shapes);
}

/// Interacción (aparecer, pasar el ratón, pulsar): en el modo «al interactuar» el borde
/// ondula un rato.
#[tauri::command]
pub fn glass_poke<R: Runtime>(window: WebviewWindow<R>, engine: State<'_, Engine>) {
    engine.poke(window.label());
}

#[tauri::command]
pub fn glass_detach<R: Runtime>(window: WebviewWindow<R>, engine: State<'_, Engine>) {
    engine.detach(window.label());
}

/// Partida en curso (SPEC sección 9): nunca se captura la pantalla con un juego abierto.
#[tauri::command]
pub fn glass_set_game(engine: State<'_, Engine>, active: bool) {
    engine.set_game(active);
}
