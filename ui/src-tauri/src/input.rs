//! Campo de texto (SPEC sección 11): pastilla sobre el motor de cristal arriba en el centro del monitor del
//! ratón, en el mismo sitio que la isla. A diferencia de la isla, toma el foco para escribir.
//! Enter envía, Esc o hacer clic fuera la cierran.

use tauri::{
    AppHandle, Emitter, Manager, Runtime, WebviewUrl, WebviewWindow, WebviewWindowBuilder,
};

use crate::{island, win32};

pub const LABEL: &str = "input";
/// Pastilla de 520 px que crece hacia abajo hasta 6 líneas (~166 px) + margen para la
/// sombra y la ondulación del borde (motor de cristal).
const WIDTH: f64 = 600.0;
const HEIGHT: f64 = 300.0;

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

pub fn show<R: Runtime>(app: &AppHandle<R>) {
    let Some(window) = app.get_webview_window(LABEL) else {
        return;
    };
    island::place_top_center(&window, WIDTH, HEIGHT);
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

#[tauri::command]
pub fn input_hide<R: Runtime>(window: WebviewWindow<R>) {
    let _ = window.hide();
}
