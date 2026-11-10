//! Asistente de primer arranque (SPEC sección 13): ventana propia con el cristal del motor,
//! como Ajustes pero de tamaño fijo. La isla la abre si el núcleo dice que aún no se ha
//! pasado por él («welcome»: onboarding_done = false); también se repite desde Ajustes → Ayuda.

use std::path::PathBuf;

use tauri::{AppHandle, Manager, PhysicalPosition, WebviewUrl, WebviewWindowBuilder};

use crate::{island, win32};

pub const LABEL: &str = "welcome";
const WIDTH: f64 = 760.0;
const HEIGHT: f64 = 580.0;

/// Abre el asistente o, si ya está abierto, lo trae al frente.
/// Asíncrono: crear una ventana desde un comando síncrono bloquea Tauri en Windows.
#[tauri::command]
pub async fn welcome_open(app: AppHandle) {
    if let Some(window) = app.get_webview_window(LABEL) {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
        return;
    }
    if let Err(err) = create(&app) {
        eprintln!("[nyx] asistente: {err}");
    }
}

fn create(app: &AppHandle) -> tauri::Result<()> {
    let window = WebviewWindowBuilder::new(app, LABEL, WebviewUrl::App("bienvenida".into()))
        .title("Bienvenida a Nyx")
        .inner_size(WIDTH, HEIGHT)
        .transparent(true)
        .decorations(false)
        .shadow(false)
        .resizable(false)
        .visible(false)
        .build()?;
    if let Some(hwnd) = win32::hwnd(&window) {
        win32::remove_border(hwnd);
    }
    // Centrado en el monitor de Nyx.
    if let Some(m) = island::current_area(app).or_else(win32::cursor_monitor) {
        let w = (WIDTH * m.scale).round() as i32;
        let h = (HEIGHT * m.scale).round() as i32;
        window.set_position(PhysicalPosition::new(
            m.left + (m.width - w) / 2,
            m.top + (m.height - h) / 2,
        ))?;
    }
    window.show()?;
    window.set_focus()?;
    Ok(())
}

/// Ajustes → Ayuda: abre en el Explorador la carpeta de registros o la de acciones.
#[tauri::command]
pub fn open_folder(kind: String) -> Result<(), String> {
    let base = std::env::var_os("LOCALAPPDATA").ok_or("sin LOCALAPPDATA")?;
    let sub = match kind.as_str() {
        "logs" => "logs",
        "actions" => "actions",
        _ => return Err(format!("carpeta desconocida: {kind}")),
    };
    let path = PathBuf::from(base).join("Nyx").join(sub);
    std::fs::create_dir_all(&path).map_err(|e| e.to_string())?;
    std::process::Command::new("explorer")
        .arg(&path)
        .spawn()
        .map(|_| ())
        .map_err(|e| e.to_string())
}
