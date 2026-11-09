//! Prueba de cristal de la fase 1 (SPEC sección 11): compara tres formas de hacer la isla.
//!
//! - A: Acrylic de Windows 11 + esquinas nativas de DWM (suaves, pero de radio pequeño).
//! - B: Acrylic + región GDI con radio grande (forma correcta, bordes sin antialias).
//! - C: Ventana transparente con tinte gris dibujado en CSS (suave, sin desenfoque real).
//!
//! Las ventanas quedan encima y dejan pasar los clics, para poder mover fotos y
//! ventanas por detrás y ver cómo se comporta cada opción.

use tauri::window::{Effect, EffectsBuilder};
use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindowBuilder};
use windows::Win32::Graphics::Dwm::{DWMWCP_DONOTROUND, DWMWCP_ROUND};

use crate::win32;

struct Sample {
    label: &'static str,
    variant: &'static str,
    width: f64,
    height: f64,
    acrylic: bool,
    /// Radio de la región GDI en px lógicos (solo variante B).
    region_radius: Option<f64>,
}

const SAMPLES: &[Sample] = &[
    Sample {
        label: "glass-a",
        variant: "a",
        width: 520.0,
        height: 120.0,
        acrylic: true,
        region_radius: None,
    },
    Sample {
        label: "glass-b-pill",
        variant: "b-pill",
        width: 120.0,
        height: 44.0,
        acrylic: true,
        region_radius: Some(22.0),
    },
    Sample {
        label: "glass-b",
        variant: "b",
        width: 520.0,
        height: 120.0,
        acrylic: true,
        region_radius: Some(28.0),
    },
    Sample {
        label: "glass-c",
        variant: "c",
        width: 600.0,
        height: 240.0,
        acrylic: false,
        region_radius: None,
    },
];

pub fn toggle(app: &AppHandle) {
    if app.get_webview_window(SAMPLES[0].label).is_some() {
        for s in SAMPLES {
            if let Some(w) = app.get_webview_window(s.label) {
                let _ = w.close();
            }
        }
    } else if let Err(err) = open(app) {
        eprintln!("[nyx] prueba de cristal: {err}");
    }
}

fn open(app: &AppHandle) -> tauri::Result<()> {
    let Some(m) = win32::cursor_monitor() else {
        return Ok(());
    };
    let gap = 32.0 * m.scale;
    let mut y = f64::from(m.top) + 140.0 * m.scale;

    for s in SAMPLES {
        let mut builder = WebviewWindowBuilder::new(
            app,
            s.label,
            WebviewUrl::App(format!("glass?v={}", s.variant).into()),
        )
        .title("Nyx · prueba de cristal")
        .inner_size(s.width, s.height)
        .transparent(true)
        .decorations(false)
        .shadow(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .resizable(false)
        .focused(false)
        .visible(false);
        if s.acrylic {
            builder = builder.effects(EffectsBuilder::new().effect(Effect::Acrylic).build());
        }
        let window = builder.build()?;
        window.set_ignore_cursor_events(true)?;

        let Some(hwnd) = win32::hwnd(&window) else {
            continue;
        };
        win32::make_non_activating(hwnd);
        win32::remove_border(hwnd);
        let w = (s.width * m.scale).round() as i32;
        let h = (s.height * m.scale).round() as i32;
        match s.region_radius {
            Some(r) => {
                win32::set_corner_preference(hwnd, DWMWCP_DONOTROUND);
                win32::set_round_region(hwnd, w, h, (r * m.scale).round() as i32);
            }
            None if s.acrylic => win32::set_corner_preference(hwnd, DWMWCP_ROUND),
            None => win32::set_corner_preference(hwnd, DWMWCP_DONOTROUND),
        }
        let x = m.left + (m.width - w) / 2;
        win32::place_topmost(hwnd, x, y.round() as i32, w, h);
        win32::show_no_activate(hwnd);
        y += f64::from(h) + gap;
    }
    Ok(())
}
