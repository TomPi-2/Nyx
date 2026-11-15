//! «Arrancar con Windows» (Ajustes → General): la clave Run del usuario, sin administrador.
//!
//! La pone el instalador si se elige (9.08) y se quita al desinstalar (install_hooks.rs). Aquí se
//! lee y se cambia. Apunta al lanzador de Velopack (`%LOCALAPPDATA%\TepnyxNyx\Nyx.exe`), que
//! abre siempre la versión actual; sin instalar (desarrollo), al propio ejecutable.

use std::path::PathBuf;

const RUN: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";
const VALUE: &str = "Nyx";

/// El ejecutable que debe abrirse al encender: el lanzador de Velopack si está instalada.
fn launcher() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    // Instalada: …\TepnyxNyx\current\nyx-ui.exe → …\TepnyxNyx\Nyx.exe
    let stub = exe.parent()?.parent()?.join("Nyx.exe");
    Some(if stub.is_file() { stub } else { exe })
}

#[tauri::command]
pub fn autostart_get() -> bool {
    #[cfg(windows)]
    {
        use windows::Win32::System::Registry::{HKEY_CURRENT_USER, RRF_RT_REG_SZ, RegGetValueW};
        use windows::core::HSTRING;
        // SAFETY: solo se pregunta si existe (sin búfer).
        unsafe {
            RegGetValueW(
                HKEY_CURRENT_USER,
                &HSTRING::from(RUN),
                &HSTRING::from(VALUE),
                RRF_RT_REG_SZ,
                None,
                None,
                None,
            )
            .is_ok()
        }
    }
    #[cfg(not(windows))]
    false
}

#[tauri::command]
pub fn autostart_set(on: bool) -> Result<bool, String> {
    #[cfg(windows)]
    {
        use windows::Win32::Foundation::ERROR_SUCCESS;
        use windows::Win32::System::Registry::{
            HKEY_CURRENT_USER, REG_SZ, RegDeleteKeyValueW, RegSetKeyValueW,
        };
        use windows::core::HSTRING;
        let status = if on {
            let exe = launcher().ok_or("No encuentro el ejecutable de Nyx")?;
            let value: Vec<u16> = format!("\"{}\"", exe.display())
                .encode_utf16()
                .chain(Some(0))
                .collect();
            // SAFETY: cadenas terminadas en cero; el tamaño va en bytes.
            unsafe {
                RegSetKeyValueW(
                    HKEY_CURRENT_USER,
                    &HSTRING::from(RUN),
                    &HSTRING::from(VALUE),
                    REG_SZ.0,
                    Some(value.as_ptr().cast()),
                    (value.len() * 2) as u32,
                )
            }
        } else {
            // SAFETY: cadenas constantes; si no existe, da igual.
            let status = unsafe {
                RegDeleteKeyValueW(
                    HKEY_CURRENT_USER,
                    &HSTRING::from(RUN),
                    &HSTRING::from(VALUE),
                )
            };
            if status.0 == 2 {
                ERROR_SUCCESS // ERROR_FILE_NOT_FOUND: ya no estaba
            } else {
                status
            }
        };
        if status != ERROR_SUCCESS {
            return Err(format!("No he podido cambiarlo ({})", status.0));
        }
    }
    Ok(autostart_get())
}
