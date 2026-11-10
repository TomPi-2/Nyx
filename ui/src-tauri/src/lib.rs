//! Proceso principal de Nyx: bandeja, instancia única, ventanas y núcleo Python.

mod core_process;
mod glass;
mod hotkeys;
mod input;
mod island;
mod monitors;
mod settings_window;
mod tray;
mod welcome_window;
mod win32;

use tauri::RunEvent;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        // Debe registrarse el primero (instancia única, SPEC sección 14).
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            // Abrir Nyx otra vez muestra los Ajustes (SPEC sección 14).
            settings_window::open(app);
        }))
        .plugin(hotkeys::plugin())
        // Alarmas y avisos: además de la burbuja, notificación de Windows (SPEC sección 11).
        .plugin(tauri_plugin_notification::init())
        .invoke_handler(tauri::generate_handler![
            core_process::core_endpoint,
            core_process::core_restart,
            island::island_set_visible,
            island::island_set_hit_rects,
            island::island_set_size,
            island::island_backdrop_luma,
            island::overlay_policy,
            monitors::monitors_list,
            input::input_hide,
            glass::glass_attach,
            glass::glass_set_options,
            glass::glass_set_shapes,
            glass::glass_poke,
            glass::glass_detach,
            glass::glass_set_game,
            glass::gallery::glass_toggle_bubble,
            glass::gallery::glass_close_gallery,
            settings_window::settings_open,
            welcome_window::welcome_open,
            welcome_window::open_folder,
        ])
        .setup(|app| {
            let handle = app.handle();
            // Antes que las ventanas: el motor de cristal (no toca la GPU hasta que se usa).
            glass::init(handle);
            core_process::start(handle);
            island::create(handle)?;
            input::create(handle)?;
            hotkeys::register(handle);
            tray::build(handle)?;
            // Ayuda de desarrollo: NYX_GLASS=1 abre la galería del motor de cristal al arrancar.
            if std::env::var("NYX_GLASS").as_deref() == Ok("1") {
                glass::gallery::toggle(handle);
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("no se pudo iniciar Nyx");

    app.run(|_app, event| {
        // Nyx vive en la bandeja: cerrar ventanas no lo termina; solo «Salir».
        if let RunEvent::ExitRequested {
            api, code: None, ..
        } = event
        {
            api.prevent_exit();
        }
    });
}
