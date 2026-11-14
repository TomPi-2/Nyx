//! Lo que el instalador necesita de Windows y de la red.

use std::io::Read;
use std::path::Path;

use windows::Win32::Foundation::ERROR_SUCCESS;
use windows::Win32::Storage::FileSystem::GetDiskFreeSpaceExW;
use windows::Win32::System::Com::{
    CLSCTX_INPROC_SERVER, COINIT_APARTMENTTHREADED, CoCreateInstance, CoInitializeEx,
    CoUninitialize, IPersistFile,
};
use windows::Win32::System::Registry::{HKEY_CURRENT_USER, REG_SZ, RegSetKeyValueW};
use windows::Win32::UI::Shell::{
    FOLDERID_Desktop, IShellLinkW, KF_FLAG_DEFAULT, SHGetKnownFolderPath, ShellExecuteW, ShellLink,
};
use windows::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;
use windows::core::{HSTRING, Interface, PCWSTR, w};

/// Descarga entera en memoria (el Setup de Velopack o la lista de huellas), por HTTPS, con el
/// avance (hecho, total) en bytes.
pub fn http_get(url: &str, progress: impl Fn((u64, u64))) -> Result<Vec<u8>, String> {
    if !url.starts_with("https://") {
        return Err("solo se descarga por HTTPS".into());
    }
    let response = ureq::get(url).call().map_err(|e| e.to_string())?;
    let total = response
        .headers()
        .get("content-length")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.parse::<u64>().ok())
        .unwrap_or(0);
    let mut reader = response.into_body().into_reader();
    let mut out = Vec::with_capacity(total as usize);
    let mut buf = vec![0u8; 1 << 16];
    loop {
        let n = reader.read(&mut buf).map_err(|e| e.to_string())?;
        if n == 0 {
            break;
        }
        out.extend_from_slice(&buf[..n]);
        progress((out.len() as u64, total));
    }
    Ok(out)
}

pub fn free_bytes(path: &Path) -> Option<u64> {
    let mut free = 0u64;
    let wide = HSTRING::from(path.as_os_str());
    // SAFETY: ruta válida terminada en cero y una variable local para el resultado.
    unsafe { GetDiskFreeSpaceExW(&wide, Some(&mut free), None, None).ok()? };
    Some(free)
}

pub fn open_url(url: &str) {
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

/// Arrancar con Windows: la clave Run del usuario (sin administrador). Nyx la quita al
/// desinstalarse.
pub fn set_autostart(exe: &Path) -> Result<(), String> {
    let value: Vec<u16> = format!("\"{}\"", exe.display())
        .encode_utf16()
        .chain(Some(0))
        .collect();
    // SAFETY: cadenas terminadas en cero; el tamaño va en bytes.
    let status = unsafe {
        RegSetKeyValueW(
            HKEY_CURRENT_USER,
            w!(r"Software\Microsoft\Windows\CurrentVersion\Run"),
            w!("Nyx"),
            REG_SZ.0,
            Some(value.as_ptr().cast()),
            (value.len() * 2) as u32,
        )
    };
    if status == ERROR_SUCCESS {
        Ok(())
    } else {
        Err(format!("{status:?}"))
    }
}

/// Acceso directo en el escritorio (`Nyx.lnk`). Nyx lo quita al desinstalarse.
pub fn desktop_shortcut(exe: &Path, name: &str) -> Result<(), String> {
    // SAFETY: COM en este hilo, objetos que se sueltan al salir; cadenas válidas.
    unsafe {
        let _ = CoInitializeEx(None, COINIT_APARTMENTTHREADED);
        let result = (|| -> windows::core::Result<()> {
            let desktop = SHGetKnownFolderPath(&FOLDERID_Desktop, KF_FLAG_DEFAULT, None)?;
            let folder = desktop.to_string().unwrap_or_default();
            windows::Win32::System::Com::CoTaskMemFree(Some(desktop.0.cast()));
            let link: IShellLinkW = CoCreateInstance(&ShellLink, None, CLSCTX_INPROC_SERVER)?;
            link.SetPath(&HSTRING::from(exe.as_os_str()))?;
            if let Some(dir) = exe.parent() {
                link.SetWorkingDirectory(&HSTRING::from(dir.as_os_str()))?;
            }
            link.SetDescription(w!("Nyx, tu asistente de voz"))?;
            let file: IPersistFile = link.cast()?;
            let path = Path::new(&folder).join(format!("{name}.lnk"));
            file.Save(&HSTRING::from(path.as_os_str()), true)?;
            Ok(())
        })();
        CoUninitialize();
        result.map_err(|e| e.to_string())
    }
}
