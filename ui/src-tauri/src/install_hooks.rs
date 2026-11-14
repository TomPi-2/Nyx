//! Lo que hace Nyx en la instalación y la desinstalación con Velopack (9.08).
//!
//! - Al acabar de instalar, el Setup abre la app; si la ha lanzado el instalador de Nyx
//!   (`NYX_INSTALLER=1`), se cierra: el instalador la abre él al terminar de bajar el oído y
//!   la voz, para que el primer arranque empiece ya con la voz.
//! - Al desinstalar, se quitan el arranque con Windows (clave Run del usuario) y el acceso
//!   directo del escritorio, que puso el instalador. Los datos de Nyx (%APPDATA%\Nyx y
//!   %LOCALAPPDATA%\Nyx) se quedan: no están en la carpeta de Velopack.

/// La app la ha abierto el Setup durante la instalación: no debe arrancar todavía.
pub fn opened_by_installer() -> bool {
    std::env::var("NYX_INSTALLER").as_deref() == Ok("1")
}

/// Quita lo que el instalador puso fuera de la carpeta de la app.
pub fn cleanup_on_uninstall() {
    #[cfg(windows)]
    {
        use windows::Win32::System::Registry::{HKEY_CURRENT_USER, RegDeleteKeyValueW};
        use windows::core::w;
        // SAFETY: cadenas constantes terminadas en cero; si no existe, no pasa nada.
        unsafe {
            let _ = RegDeleteKeyValueW(
                HKEY_CURRENT_USER,
                w!(r"Software\Microsoft\Windows\CurrentVersion\Run"),
                w!("Nyx"),
            );
        }
        if let Some(desktop) = desktop_dir() {
            let link = desktop.join("Nyx.lnk");
            // Solo el acceso directo que puso el instalador (`Nyx.lnk`), nada más.
            let _ = std::fs::remove_file(link);
        }
    }
}

#[cfg(windows)]
fn desktop_dir() -> Option<std::path::PathBuf> {
    use windows::Win32::System::Com::CoTaskMemFree;
    use windows::Win32::UI::Shell::{FOLDERID_Desktop, KF_FLAG_DEFAULT, SHGetKnownFolderPath};
    // SAFETY: devuelve una cadena que se libera con CoTaskMemFree.
    unsafe {
        let path = SHGetKnownFolderPath(&FOLDERID_Desktop, KF_FLAG_DEFAULT, None).ok()?;
        let text = path.to_string().ok();
        CoTaskMemFree(Some(path.0.cast()));
        text.map(std::path::PathBuf::from)
    }
}
