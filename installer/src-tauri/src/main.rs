// Sin consola en la versión final.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    nyx_installer_lib::run()
}
