//! La onda de «Nyx lista» (tarea 9.04; docs/INSTALADOR-Y-MOTOR-GRAFICO.md, apartado 4).
//!
//! Una ventana transparente por monitor (siempre encima, sin foco y dejando pasar los clics)
//! que existe solo mientras pasa la onda. Todas dibujan su trozo del mismo anillo, definido
//! en coordenadas del escritorio virtual y con el mismo reloj, así que se ve como una sola
//! onda que cruza de un monitor a otro según cómo estén colocados en Windows (aunque tengan
//! distinta escala). Una sola ventana gigante se descartó por las escalas mezcladas.
//!
//! El anillo lo dibuja el motor de cristal (forma con `ring`): deforma lo que hay detrás.
//! La página (`routes/onda`) se cierra sola al acabar.

use std::time::{SystemTime, UNIX_EPOCH};

use tauri::{AppHandle, Manager, Runtime, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

use crate::{island, win32};

/// Prefijo de las ventanas de la onda (la capacidad `default` las incluye con «onda-*»).
const PREFIX: &str = "onda-";
/// Margen para que todas las ventanas carguen y el motor tenga la primera captura antes de
/// que empiece (si no, los primeros fotogramas serían solo tinte). Una que llegue tarde se
/// une a la onda donde vaya: el reloj es el mismo.
const START_DELAY_MS: u128 = 800;

/// Lanza la onda desde el sitio de Nyx: arriba en el centro del monitor donde aparecería, a
/// `cy` píxeles CSS del borde de arriba (el centro de su forma). Aunque Nyx esté oculta.
/// Asíncrono: crear ventanas desde un comando síncrono bloquea Tauri en Windows.
#[tauri::command]
pub async fn wave_play(app: AppHandle, cy: f64) -> Result<(), String> {
    let area = island::current_area(&app)
        .or_else(win32::cursor_monitor)
        .ok_or("sin monitor")?;
    // Origen en píxeles físicos del escritorio virtual.
    let ox = f64::from(area.left) + f64::from(area.width) / 2.0;
    let oy = f64::from(area.top) + cy * area.scale;
    play(&app, ox, oy);
    Ok(())
}

fn play<R: Runtime>(app: &AppHandle<R>, ox: f64, oy: f64) {
    // Si aún quedaba una (dos avisos seguidos), se quita.
    for (label, w) in app.webview_windows() {
        if label.starts_with(PREFIX) {
            let _ = w.destroy();
        }
    }
    let monitors = win32::monitors();
    if monitors.is_empty() {
        return;
    }
    // Hasta dónde tiene que llegar: la esquina del escritorio virtual más lejana.
    let reach = monitors
        .iter()
        .flat_map(|m| {
            let (l, t) = (f64::from(m.area.left), f64::from(m.area.top));
            let (r, b) = (l + f64::from(m.area.width), t + f64::from(m.area.height));
            [(l, t), (r, t), (l, b), (r, b)]
        })
        .map(|(x, y)| (x - ox).hypot(y - oy))
        .fold(0.0_f64, f64::max);
    let start = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or_default()
        + START_DELAY_MS;
    for (i, m) in monitors.iter().enumerate() {
        let a = m.area;
        // Todo en píxeles físicos; la página lo pasa a CSS con su propia escala.
        let url = format!(
            "onda?ox={}&oy={}&left={}&top={}&reach={}&start={}",
            ox.round(),
            oy.round(),
            a.left,
            a.top,
            reach.ceil(),
            start
        );
        if let Err(err) = open(app, &format!("{PREFIX}{i}"), &url, a) {
            eprintln!("[nyx] onda: {err}");
        }
    }
}

fn open<R: Runtime>(
    app: &AppHandle<R>,
    label: &str,
    url: &str,
    a: win32::MonitorArea,
) -> tauri::Result<()> {
    let window = WebviewWindowBuilder::new(app, label, WebviewUrl::App(url.into()))
        .title("Nyx")
        .transparent(true)
        .decorations(false)
        .shadow(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .resizable(false)
        .focused(false)
        .focusable(false)
        .visible(false)
        .build()?;
    if let Some(hwnd) = win32::hwnd(&window) {
        win32::make_non_activating(hwnd);
        win32::remove_border(hwnd);
        win32::set_click_through(hwnd, true);
        win32::place_topmost(hwnd, a.left, a.top, a.width, a.height);
        win32::show_no_activate(hwnd);
    }
    Ok(())
}

/// La página de la onda ha terminado: se quita su ventana.
#[tauri::command]
pub fn wave_done<R: Runtime>(window: WebviewWindow<R>) {
    if window.label().starts_with(PREFIX) {
        let _ = window.destroy();
    }
}
