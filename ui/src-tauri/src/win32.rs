//! Llamadas directas a Win32/DWM que Tauri no expone.

use raw_window_handle::{HasWindowHandle, RawWindowHandle};
use tauri::{Runtime, WebviewWindow};
use windows::Win32::Foundation::{HWND, POINT, RECT};
use windows::Win32::Graphics::Dwm::{DWMWA_BORDER_COLOR, DwmSetWindowAttribute};
use windows::Win32::Graphics::Gdi::{
    GetMonitorInfoW, MONITOR_DEFAULTTONEAREST, MONITORINFO, MonitorFromPoint,
};
use windows::Win32::UI::HiDpi::{GetDpiForMonitor, GetDpiForWindow, MDT_EFFECTIVE_DPI};
use windows::Win32::UI::WindowsAndMessaging::{
    GWL_EXSTYLE, GetCursorPos, GetWindowLongPtrW, GetWindowRect, HWND_TOPMOST, SW_HIDE,
    SW_SHOWNOACTIVATE, SWP_FRAMECHANGED, SWP_NOACTIVATE, SWP_NOMOVE, SWP_NOOWNERZORDER, SWP_NOSIZE,
    SWP_NOZORDER, SetWindowLongPtrW, SetWindowPos, ShowWindow, WS_EX_LAYERED, WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW, WS_EX_TRANSPARENT,
};

/// Valor de DWMWA_BORDER_COLOR que quita el borde de 1 px de Windows 11.
const DWMWA_COLOR_NONE: u32 = 0xFFFF_FFFE;

pub fn hwnd<R: Runtime>(window: &WebviewWindow<R>) -> Option<HWND> {
    let handle = window.window_handle().ok()?;
    match handle.as_raw() {
        RawWindowHandle::Win32(h) => Some(HWND(h.hwnd.get() as *mut _)),
        _ => None,
    }
}

/// Ventana que nunca toma el foco y no aparece en Alt+Tab (WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW).
pub fn make_non_activating(hwnd: HWND) {
    unsafe {
        let ex = GetWindowLongPtrW(hwnd, GWL_EXSTYLE);
        let extra = (WS_EX_NOACTIVATE.0 | WS_EX_TOOLWINDOW.0) as isize;
        SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex | extra);
    }
}

/// Fuera de Alt+Tab (WS_EX_TOOLWINDOW) pero sin WS_EX_NOACTIVATE: puede recibir el teclado.
pub fn make_tool_window(hwnd: HWND) {
    unsafe {
        let ex = GetWindowLongPtrW(hwnd, GWL_EXSTYLE);
        SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex | WS_EX_TOOLWINDOW.0 as isize);
    }
}

pub fn remove_border(hwnd: HWND) {
    let color = DWMWA_COLOR_NONE;
    unsafe {
        let _ = DwmSetWindowAttribute(
            hwnd,
            DWMWA_BORDER_COLOR,
            &color as *const u32 as *const _,
            size_of::<u32>() as u32,
        );
    }
}

/// Área del monitor (en píxeles físicos) y su escala.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct MonitorArea {
    pub left: i32,
    pub top: i32,
    pub width: i32,
    pub height: i32,
    pub scale: f64,
}

/// Monitor donde está el puntero del ratón.
pub fn cursor_monitor() -> Option<MonitorArea> {
    unsafe {
        let mut pt = POINT::default();
        GetCursorPos(&mut pt).ok()?;
        let monitor = MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST);
        let mut info = MONITORINFO {
            cbSize: size_of::<MONITORINFO>() as u32,
            ..Default::default()
        };
        if !GetMonitorInfoW(monitor, &mut info).as_bool() {
            return None;
        }
        let (mut dpi_x, mut dpi_y) = (96u32, 96u32);
        let _ = GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI, &mut dpi_x, &mut dpi_y);
        let RECT {
            left,
            top,
            right,
            bottom,
        } = info.rcMonitor;
        Some(MonitorArea {
            left,
            top,
            width: right - left,
            height: bottom - top,
            scale: f64::from(dpi_x) / 96.0,
        })
    }
}

/// Coloca la ventana siempre encima sin activarla.
pub fn place_topmost(hwnd: HWND, x: i32, y: i32, width: i32, height: i32) {
    unsafe {
        let _ = SetWindowPos(
            hwnd,
            Some(HWND_TOPMOST),
            x,
            y,
            width,
            height,
            SWP_NOACTIVATE | SWP_NOOWNERZORDER,
        );
    }
}

pub fn show_no_activate(hwnd: HWND) {
    unsafe {
        let _ = ShowWindow(hwnd, SW_SHOWNOACTIVATE);
    }
}

pub fn hide(hwnd: HWND) {
    unsafe {
        let _ = ShowWindow(hwnd, SW_HIDE);
    }
}

/// Deja pasar los clics a lo que hay debajo (`WS_EX_TRANSPARENT | WS_EX_LAYERED`) o no.
///
/// Se cambia directamente el estilo y nada más: `set_ignore_cursor_events` de Tauri
/// reescribe todos los estilos según lo que tao cree de la ventana y, como la isla se
/// muestra con Win32, la ocultaba y le quitaba `WS_EX_NOACTIVATE`.
pub fn set_click_through(hwnd: HWND, through: bool) {
    unsafe {
        let ex = GetWindowLongPtrW(hwnd, GWL_EXSTYLE);
        let bits = (WS_EX_TRANSPARENT.0 | WS_EX_LAYERED.0) as isize;
        let new = if through { ex | bits } else { ex & !bits };
        if new != ex {
            SetWindowLongPtrW(hwnd, GWL_EXSTYLE, new);
            let _ = SetWindowPos(
                hwnd,
                None,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            );
        }
    }
}

/// ¿Está el ratón sobre alguno de estos rectángulos? Vienen de la página, en píxeles CSS
/// relativos a la ventana: `[x, y, ancho, alto]`.
pub fn cursor_in(hwnd: HWND, rects: &[[f64; 4]]) -> bool {
    unsafe {
        let mut pt = POINT::default();
        let mut win = RECT::default();
        if GetCursorPos(&mut pt).is_err() || GetWindowRect(hwnd, &mut win).is_err() {
            return false;
        }
        let scale = f64::from(GetDpiForWindow(hwnd).max(96)) / 96.0;
        let x = f64::from(pt.x - win.left) / scale;
        let y = f64::from(pt.y - win.top) / scale;
        rects
            .iter()
            .any(|[rx, ry, rw, rh]| x >= *rx && x <= rx + rw && y >= *ry && y <= ry + rh)
    }
}

/// Luminancia media (0–1) de lo que se ve en pantalla en un anillo alrededor de un punto de
/// la ventana (píxeles CSS). Se mira alrededor y no debajo porque debajo está la propia forma
/// de Nyx (decisión 2026-11-10: así Nyx sigue saliendo en capturas y streams).
pub fn ring_luma(hwnd: HWND, cx: f64, cy: f64, radius: f64) -> Option<f64> {
    use windows::Win32::Graphics::Gdi::{CLR_INVALID, GetDC, GetPixel, ReleaseDC};

    const SAMPLES: usize = 16;
    let mut rect = RECT::default();
    // SAFETY: hwnd es una ventana válida de esta app y rect es una variable local.
    unsafe { GetWindowRect(hwnd, &mut rect).ok()? };
    // SAFETY: consulta de solo lectura sobre una ventana válida.
    let scale = f64::from(unsafe { GetDpiForWindow(hwnd) }.max(96)) / 96.0;
    // SAFETY: DC de la pantalla entera; se libera al final.
    let dc = unsafe { GetDC(None) };
    if dc.is_invalid() {
        return None;
    }
    let mut total = 0.0;
    let mut count = 0usize;
    for i in 0..SAMPLES {
        let a = (i as f64) * std::f64::consts::TAU / (SAMPLES as f64);
        let x = rect.left + ((cx + radius * a.cos()) * scale).round() as i32;
        let y = rect.top + ((cy + radius * a.sin()) * scale).round() as i32;
        // SAFETY: lectura de un píxel del DC de pantalla.
        let c = unsafe { GetPixel(dc, x, y) };
        if c.0 == CLR_INVALID {
            continue;
        }
        let (r, g, b) = (c.0 & 0xFF, (c.0 >> 8) & 0xFF, (c.0 >> 16) & 0xFF);
        total += (0.2126 * f64::from(r) + 0.7152 * f64::from(g) + 0.0722 * f64::from(b)) / 255.0;
        count += 1;
    }
    // SAFETY: libera el DC obtenido arriba.
    unsafe { ReleaseDC(None, dc) };
    (count > 0).then(|| total / count as f64)
}

/// Un monitor conectado: nombre del dispositivo («\.\DISPLAY2», el mismo que usa el núcleo
/// para decir dónde está un juego), su área y si es el principal.
#[derive(Clone, Debug, PartialEq)]
pub struct Monitor {
    pub device: String,
    pub area: MonitorArea,
    pub primary: bool,
}

fn monitor_info(monitor: windows::Win32::Graphics::Gdi::HMONITOR) -> Option<Monitor> {
    use windows::Win32::Graphics::Gdi::MONITORINFOEXW;

    let mut info = MONITORINFOEXW::default();
    info.monitorInfo.cbSize = size_of::<MONITORINFOEXW>() as u32;
    // SAFETY: MONITORINFOEXW empieza por MONITORINFO y cbSize dice que es la versión «EX».
    let ok = unsafe { GetMonitorInfoW(monitor, &mut info.monitorInfo as *mut MONITORINFO) };
    if !ok.as_bool() {
        return None;
    }
    let (mut dpi_x, mut dpi_y) = (96u32, 96u32);
    // SAFETY: consulta sobre un monitor válido; variables locales.
    let _ = unsafe { GetDpiForMonitor(monitor, MDT_EFFECTIVE_DPI, &mut dpi_x, &mut dpi_y) };
    let len = info
        .szDevice
        .iter()
        .position(|&c| c == 0)
        .unwrap_or(info.szDevice.len());
    let RECT {
        left,
        top,
        right,
        bottom,
    } = info.monitorInfo.rcMonitor;
    Some(Monitor {
        device: String::from_utf16_lossy(&info.szDevice[..len]),
        area: MonitorArea {
            left,
            top,
            width: right - left,
            height: bottom - top,
            scale: f64::from(dpi_x) / 96.0,
        },
        // MONITORINFOF_PRIMARY = 1
        primary: info.monitorInfo.dwFlags & 1 != 0,
    })
}

/// Todos los monitores conectados, de izquierda a derecha (y de arriba abajo).
pub fn monitors() -> Vec<Monitor> {
    use windows::Win32::Foundation::LPARAM;
    use windows::Win32::Graphics::Gdi::{EnumDisplayMonitors, HDC, HMONITOR};
    use windows::core::BOOL;

    unsafe extern "system" fn visit(m: HMONITOR, _: HDC, _: *mut RECT, data: LPARAM) -> BOOL {
        // SAFETY: data apunta al Vec de abajo mientras dura EnumDisplayMonitors.
        let list = unsafe { &mut *(data.0 as *mut Vec<Monitor>) };
        if let Some(info) = monitor_info(m) {
            list.push(info);
        }
        BOOL(1)
    }

    let mut list: Vec<Monitor> = Vec::new();
    // SAFETY: la lista vive durante toda la enumeración (síncrona).
    unsafe {
        let _ = EnumDisplayMonitors(
            None,
            None,
            Some(visit),
            LPARAM(&mut list as *mut Vec<Monitor> as isize),
        );
    }
    list.sort_by_key(|m| (m.area.left, m.area.top));
    list
}

/// Dispositivo del monitor donde está el ratón.
pub fn cursor_device() -> Option<String> {
    let mut pt = POINT::default();
    // SAFETY: lectura de la posición del ratón en una variable local.
    unsafe { GetCursorPos(&mut pt).ok()? };
    // SAFETY: MonitorFromPoint siempre devuelve un monitor con MONITOR_DEFAULTTONEAREST.
    let monitor = unsafe { MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST) };
    monitor_info(monitor).map(|m| m.device)
}
