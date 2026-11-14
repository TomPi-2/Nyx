// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    // Lo primero (Velopack, 9.06): atiende la instalación, las actualizaciones y la
    // desinstalación, y aplica una versión ya descargada si se cerró Nyx antes de aplicarla.
    // Sin instalar con Velopack (desarrollo) no hace nada.
    velopack::VelopackApp::build().run();
    nyx_ui_lib::run()
}
