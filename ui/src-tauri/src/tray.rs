//! Icono de la bandeja del sistema. Nyx no tiene ventana principal: este es el único
//! punto de control visible (SPEC sección 11).

use std::time::Duration;

use tauri::AppHandle;
use tauri::image::Image;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;

use crate::{core_process, glass};

pub fn build(app: &AppHandle) -> tauri::Result<()> {
    let glass_item =
        MenuItem::with_id(app, "glass", "Motor gráfico (ejemplos)", true, None::<&str>)?;
    let restart = MenuItem::with_id(app, "restart-core", "Reiniciar núcleo", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Salir", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[
            &glass_item,
            &restart,
            &PredefinedMenuItem::separator(app)?,
            &quit,
        ],
    )?;

    let mut builder = TrayIconBuilder::with_id("nyx")
        .tooltip("Nyx")
        .menu(&menu)
        .show_menu_on_left_click(true)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "glass" => glass::gallery::toggle(app),
            "restart-core" => core_process::restart(app),
            "quit" => app.exit(0),
            _ => {}
        });
    // El icono de Nyx (forma «Sólido»): blanco con la barra de tareas oscura y gris oscuro con
    // la clara, para que se vea siempre. Si se cambia el tema de Windows, se cambia también.
    let light = taskbar_is_light();
    builder = builder.icon(tray_icon(light));
    let tray = builder.build(app)?;
    tauri::async_runtime::spawn(async move {
        let mut current = light;
        loop {
            tokio::time::sleep(THEME_POLL).await;
            let now = taskbar_is_light();
            if now != current {
                current = now;
                let _ = tray.set_icon(Some(tray_icon(now)));
            }
        }
    });
    Ok(())
}

const THEME_POLL: Duration = Duration::from_secs(5);

fn tray_icon(light_taskbar: bool) -> Image<'static> {
    let bytes: &[u8] = if light_taskbar {
        include_bytes!("../icons/tray-light.png")
    } else {
        include_bytes!("../icons/tray-dark.png")
    };
    Image::from_bytes(bytes).expect("icono de la bandeja")
}

/// ¿Barra de tareas en tema claro? (Configuración → Personalización → Colores → «Elige tu modo»:
/// el de Windows es el que pinta la barra de tareas.)
#[cfg(windows)]
fn taskbar_is_light() -> bool {
    use windows::Win32::System::Registry::{HKEY_CURRENT_USER, RRF_RT_REG_DWORD, RegGetValueW};
    use windows::core::w;

    let mut value: u32 = 0;
    let mut size = std::mem::size_of::<u32>() as u32;
    // SAFETY: lectura de un DWORD del registro en variables locales del tamaño indicado.
    let status = unsafe {
        RegGetValueW(
            HKEY_CURRENT_USER,
            w!(r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"),
            w!("SystemUsesLightTheme"),
            RRF_RT_REG_DWORD,
            None,
            Some((&raw mut value).cast()),
            Some(&raw mut size),
        )
    };
    status.is_ok() && value == 1
}

#[cfg(not(windows))]
fn taskbar_is_light() -> bool {
    false
}
