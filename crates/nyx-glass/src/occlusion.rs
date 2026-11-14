//! ¿Tapan otras ventanas por completo a una ventana con cristal? Si es así, el motor no la
//! dibuja ni captura la pantalla para ella: no se ve, así que no gasta. En cuanto asoma un
//! trozo, vuelve a dibujarse (y a ondular). Sirve sobre todo para Ajustes, que puede quedarse
//! abierta detrás de otras ventanas mucho rato.
//!
//! Se recorre el orden de las ventanas hacia arriba y se resta del área visible el rectángulo
//! de cada una que tape de verdad. Ante la duda, se considera que no tapa (mejor dibujar de
//! más que dejar un panel quieto a la vista): ventanas transparentes o superpuestas (como la
//! isla de Nyx, o los overlays de otros programas), ocultas, minimizadas o en otro escritorio.

use windows::Win32::Foundation::{HWND, RECT};
use windows::Win32::Graphics::Dwm::{
    DWMWA_CLOAKED, DWMWA_EXTENDED_FRAME_BOUNDS, DwmGetWindowAttribute,
};
use windows::Win32::Graphics::Gdi::{
    CombineRgn, CreateRectRgn, DeleteObject, NULLREGION, RGN_DIFF,
};
use windows::Win32::UI::WindowsAndMessaging::{
    GW_HWNDPREV, GWL_EXSTYLE, GetClassNameW, GetWindow, GetWindowLongPtrW, GetWindowRect,
    GetWindowTextW, IsIconic, IsWindowVisible, WS_EX_LAYERED, WS_EX_TOPMOST, WS_EX_TRANSPARENT,
};

/// Como mucho se miran tantas ventanas por encima (de sobra en la práctica).
const MAX_ABOVE: usize = 512;

/// ¿Está `area` (coordenadas de pantalla) totalmente tapada por ventanas que hay encima de
/// `hwnd`?
/// Devuelve la ventana que termina de taparla (para el registro), o None si se ve algo.
pub fn covering(hwnd: HWND, area: &RECT) -> Option<HWND> {
    if area.right <= area.left || area.bottom <= area.top {
        return None;
    }
    // SAFETY: región propia; se libera al final en todos los caminos.
    let visible = unsafe { CreateRectRgn(area.left, area.top, area.right, area.bottom) };
    if visible.is_invalid() {
        return None;
    }
    let mut covered = None;
    let mut current = hwnd;
    for _ in 0..MAX_ABOVE {
        // SAFETY: consulta del orden de ventanas; falla al llegar arriba del todo.
        let Ok(above) = (unsafe { GetWindow(current, GW_HWNDPREV) }) else {
            break;
        };
        current = above;
        let Some(rect) = opaque_bounds(above) else {
            continue;
        };
        if rect.right <= area.left
            || rect.left >= area.right
            || rect.bottom <= area.top
            || rect.top >= area.bottom
        {
            continue;
        }
        // SAFETY: regiones propias; la temporal se libera enseguida.
        unsafe {
            let cut = CreateRectRgn(rect.left, rect.top, rect.right, rect.bottom);
            let kind = CombineRgn(Some(visible), Some(visible), Some(cut), RGN_DIFF);
            let _ = DeleteObject(cut.into());
            if kind == NULLREGION {
                covered = Some(above);
                break;
            }
        }
    }
    // SAFETY: región creada arriba.
    let _ = unsafe { DeleteObject(visible.into()) };
    covered
}

/// Rectángulo que una ventana tapa de verdad, o None si no cuenta.
fn opaque_bounds(hwnd: HWND) -> Option<RECT> {
    // SAFETY: consultas de solo lectura sobre una ventana que existe (o fallan sin más).
    unsafe {
        if !IsWindowVisible(hwnd).as_bool() || IsIconic(hwnd).as_bool() {
            return None;
        }
        let ex = GetWindowLongPtrW(hwnd, GWL_EXSTYLE) as u32;
        if ex & (WS_EX_LAYERED.0 | WS_EX_TRANSPARENT.0) != 0 {
            return None; // transparente o superpuesta: puede dejar ver lo de debajo
        }
        // «Siempre encima»: así son los overlays (Epic, Steam, Discord, AMD…), que cubren la
        // pantalla entera siendo casi del todo transparentes y sin marcarse como tales. Tras
        // una partida pueden quedarse encima de Ajustes, que se quedaba sin cristal
        // (ERRORES.md, 2026-11-11). Una app normal maximizada no lo es, así que se sigue
        // ahorrando con Ajustes detrás de otras ventanas.
        if ex & WS_EX_TOPMOST.0 != 0 {
            return None;
        }
        let mut cloaked = 0u32;
        let _ = DwmGetWindowAttribute(
            hwnd,
            DWMWA_CLOAKED,
            &mut cloaked as *mut u32 as *mut _,
            size_of::<u32>() as u32,
        );
        if cloaked != 0 {
            return None; // en otro escritorio virtual o suspendida
        }
        // El marco visible, sin los bordes invisibles de redimensionar que tiene GetWindowRect.
        let mut rect = RECT::default();
        if DwmGetWindowAttribute(
            hwnd,
            DWMWA_EXTENDED_FRAME_BOUNDS,
            &mut rect as *mut RECT as *mut _,
            size_of::<RECT>() as u32,
        )
        .is_err()
            && GetWindowRect(hwnd, &mut rect).is_err()
        {
            return None;
        }
        (rect.right > rect.left && rect.bottom > rect.top).then_some(rect)
    }
}

/// «clase · título» de una ventana, para el registro.
pub fn describe(hwnd: HWND) -> String {
    let mut class = [0u16; 128];
    let mut title = [0u16; 128];
    // SAFETY: búferes propios del tamaño indicado.
    let (c, t) = unsafe {
        (
            GetClassNameW(hwnd, &mut class),
            GetWindowTextW(hwnd, &mut title),
        )
    };
    format!(
        "{} · {}",
        String::from_utf16_lossy(&class[..c.max(0) as usize]),
        String::from_utf16_lossy(&title[..t.max(0) as usize])
    )
}
