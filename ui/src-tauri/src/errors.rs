//! Códigos de error que ve el usuario (docs/CODIGOS-DE-ERROR.md): cada fallo que se le enseña
//! lleva uno («N-401») para buscar en la web qué ha pasado y qué hacer.

use tauri::AppHandle;
use tauri_plugin_notification::NotificationExt;

/// La explicación de cada código (con su ancla: `#N-401`).
pub const ERRORS_URL: &str = "https://tepnyx.com/nyx/errores";

/// El núcleo se ha cerrado tres veces seguidas al arrancar.
pub const CORE_CRASHED: &str = "N-401";
/// No se ha podido lanzar el núcleo (falta o un antivirus lo bloquea).
pub const CORE_MISSING: &str = "N-402";
/// Actualizaciones: comprobar, descargar y aplicar.
pub const UPDATE_CHECK: &str = "A-301";
pub const UPDATE_DOWNLOAD: &str = "A-302";
pub const UPDATE_APPLY: &str = "A-303";
/// La versión nueva no arrancaba y se ha vuelto a la anterior.
pub const UPDATE_ROLLED_BACK: &str = "A-304";

/// Abre la explicación de un código en el navegador (panel de descargas, avisos).
#[tauri::command]
pub fn open_error(code: String) {
    let code: String = code
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '-')
        .take(8)
        .collect();
    open_url(&format!("{ERRORS_URL}#{code}"));
}

/// Abre un enlace de la app (créditos y licencias) en el navegador. Solo `https://`: nada de
/// archivos ni otros esquemas aunque una página lo pidiera.
#[tauri::command]
pub fn open_link(url: String) -> Result<(), String> {
    let ok = url.starts_with("https://")
        && url.len() < 300
        && !url.chars().any(|c| c.is_whitespace() || c == '"');
    if !ok {
        return Err("enlace no válido".into());
    }
    open_url(&url);
    Ok(())
}

/// Aviso de Windows con el código (sirve aunque no haya ninguna ventana de Nyx a la vista).
pub fn notify(app: &AppHandle, code: &str, title: &str, body: &str) {
    let _ = app
        .notification()
        .builder()
        .title(title)
        .body(format!(
            "{body}\nCódigo {code} · más en tepnyx.com/nyx/errores"
        ))
        .show();
}

fn open_url(url: &str) {
    #[cfg(windows)]
    {
        use windows::Win32::UI::Shell::ShellExecuteW;
        use windows::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;
        use windows::core::{HSTRING, PCWSTR, w};
        let url = HSTRING::from(url);
        // SAFETY: abre una dirección con el programa predeterminado; cadenas válidas.
        unsafe {
            ShellExecuteW(
                None,
                w!("open"),
                &url,
                PCWSTR::null(),
                PCWSTR::null(),
                SW_SHOWNORMAL,
            );
        }
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn every_code_is_in_the_catalog() {
        let catalog = include_str!("../../../docs/CODIGOS-DE-ERROR.md");
        for code in [
            super::CORE_CRASHED,
            super::CORE_MISSING,
            super::UPDATE_CHECK,
            super::UPDATE_DOWNLOAD,
            super::UPDATE_APPLY,
            super::UPDATE_ROLLED_BACK,
        ] {
            assert!(catalog.contains(&format!("| {code} |")), "{code}");
        }
    }
}
