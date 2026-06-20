// Tauri v2 shell for Photo Cherrypick (desktop).
//
// Responsibility: launch the bundled Python sidecar (the FastAPI server, packaged with PyInstaller
// as `bin/cull-server`) which serves both the SPA and the API on 127.0.0.1, then open a webview
// onto it. The folder picker is provided by tauri-plugin-dialog (exposed to the SPA via
// withGlobalTauri as window.__TAURI__.dialog.open).
//
// NOTE: requires the Rust toolchain (rustup) + tauri-cli to build — see ../README.md. Not compiled
// in the prototype environment; the same server runs standalone today (`uvicorn server.app:app`).

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

const PORT: u16 = 8756;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            // 1. spawn the packaged local server (single-user, binds to loopback only)
            let sidecar = app
                .shell()
                .sidecar("cull-server")?
                .args(["--host", "127.0.0.1", "--port", &PORT.to_string()]);
            let (mut rx, _child) = sidecar.spawn()?;
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    if let CommandEvent::Stderr(line) = event {
                        eprintln!("[cull-server] {}", String::from_utf8_lossy(&line));
                    }
                }
            });

            // 2. open the window onto the local server (it serves the SPA + API same-origin)
            let url = format!("http://127.0.0.1:{PORT}");
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url.parse().unwrap()))
                .title("Photo Cherrypick")
                .inner_size(1280.0, 860.0)
                .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
