//! Icono de la bandeja del sistema. Nyx no tiene ventana principal: este es el único
//! punto de control visible (SPEC sección 11).

use tauri::AppHandle;
use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::TrayIconBuilder;

use crate::{core_process, glass};

pub fn build(app: &AppHandle) -> tauri::Result<()> {
    let glass_item =
        CheckMenuItem::with_id(app, "glass", "Prueba de cristal", true, false, None::<&str>)?;
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
            "glass" => glass::toggle(app),
            "restart-core" => core_process::restart(app),
            "quit" => app.exit(0),
            _ => {}
        });
    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }
    builder.build(app)?;
    Ok(())
}
