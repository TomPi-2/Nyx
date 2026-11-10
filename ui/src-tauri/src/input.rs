//! Campo de texto (SPEC sección 11): pastilla sobre el motor de cristal arriba en el centro del monitor del
//! ratón, en el mismo sitio que la isla. A diferencia de la isla, toma el foco para escribir.
//! Enter envía, Esc o hacer clic fuera la cierran.
//!
//! Si Nyx está a la vista, el campo va debajo de ella (TextInput.svelte): la página pide el
//! alto de la ventana para que quepan los dos sitios (input_set_height).

use std::sync::Mutex;

use tauri::{
    AppHandle, Emitter, Manager, Runtime, WebviewUrl, WebviewWindow, WebviewWindowBuilder,
};

use crate::{island, win32};

pub const LABEL: &str = "input";
/// Pastilla de 520 px que crece hacia abajo hasta 6 líneas (~166 px) + margen para la
/// sombra y la ondulación del borde (motor de cristal).
const WIDTH: f64 = 600.0;
const HEIGHT: f64 = 300.0;
/// Alto que pide la página (px CSS): depende del tamaño de Nyx.
static PAGE_HEIGHT: Mutex<f64> = Mutex::new(HEIGHT);

fn height() -> f64 {
    PAGE_HEIGHT.lock().map(|h| *h).unwrap_or(HEIGHT)
}

pub fn create(app: &AppHandle) -> tauri::Result<()> {
    let window = WebviewWindowBuilder::new(app, LABEL, WebviewUrl::App("input".into()))
        .title("Nyx")
        .inner_size(WIDTH, HEIGHT)
        .transparent(true)
        .decorations(false)
        .shadow(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .resizable(false)
        .focused(false)
        .visible(false)
        .build()?;
    if let Some(hwnd) = win32::hwnd(&window) {
        win32::make_tool_window(hwnd);
        win32::remove_border(hwnd);
    }
    Ok(())
}

pub fn show(app: &AppHandle) {
    let Some(window) = app.get_webview_window(LABEL) else {
        return;
    };
    // En el mismo monitor que Nyx (sigue al ratón o el fijo de Ajustes).
    if let Some(area) = island::current_area(app).or_else(win32::cursor_monitor) {
        island::place_top_center_at(&window, area, WIDTH, height(), 0.0);
    }
    let _ = window.show();
    // tao reescribe los estilos al mostrar la ventana y quita WS_EX_TOOLWINDOW: se vuelve a
    // poner después, en el mismo hilo y en orden (fuera de Alt+Tab mientras se escribe).
    if let Some(hwnd) = win32::hwnd(&window) {
        let raw = hwnd.0 as isize;
        let _ = window.run_on_main_thread(move || {
            win32::make_tool_window(windows::Win32::Foundation::HWND(raw as *mut _));
        });
    }
    // El atajo global da permiso a Nyx para traer su ventana al frente.
    let _ = window.set_focus();
    let _ = window.emit("input://show", ());
}

/// La página pide el alto: el campo bajo Nyx más grande, con 6 líneas.
#[tauri::command]
pub fn input_set_height(app: AppHandle, window: WebviewWindow, height: f64) {
    let height = height.clamp(120.0, 900.0);
    if let Ok(mut h) = PAGE_HEIGHT.lock() {
        *h = height;
    }
    if window.is_visible().unwrap_or(false)
        && let Some(area) = island::current_area(&app)
    {
        island::place_top_center_at(&window, area, WIDTH, height, 0.0);
    }
}

#[tauri::command]
pub fn input_hide<R: Runtime>(window: WebviewWindow<R>) {
    let _ = window.hide();
}
