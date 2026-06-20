// Tauri v2 shell for Photo Cherrypick (desktop).
//
// Launches the bundled Python sidecar (the FastAPI server frozen with PyInstaller as
// `bin/cull-server`) which serves the built SPA + the API on 127.0.0.1, WAITS until it is accepting
// connections, then opens a webview onto it. The folder picker comes from tauri-plugin-dialog
// (exposed to the SPA via withGlobalTauri as window.__TAURI__.dialog.open).
//
// Auto-update: tauri-plugin-updater is registered and a best-effort check runs on startup
// (`spawn_update_check`) — it pulls latest.json from the GitHub Release and, if a newer SIGNED build
// is published, downloads + installs it in place. Every failure path (offline, no release yet,
// signature mismatch) is swallowed so the app always continues to launch.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::{SocketAddr, TcpStream};
use std::time::Duration;

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;
#[cfg(desktop)]
use tauri_plugin_updater::UpdaterExt;

const PORT: u16 = 8756;

// Block until the sidecar is accepting TCP connections, or give up after ~90s. A frozen onefile
// re-extracts and imports torch/opencv on first launch (many seconds); opening the webview before
// the server binds would show a connection-refused / blank page.
fn wait_for_server(port: u16) {
    let addr: SocketAddr = ([127, 0, 0, 1], port).into();
    for _ in 0..180 {
        if TcpStream::connect_timeout(&addr, Duration::from_millis(500)).is_ok() {
            return;
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    eprintln!("[shell] sidecar not ready after ~90s; opening the window anyway");
}

// Best-effort, non-blocking update check. Runs once on startup in a background task. On macOS the
// replaced bundle inherits the (ad-hoc) signature of the running app, so the in-place swap works
// without an Apple Developer ID.
#[cfg(desktop)]
fn spawn_update_check(handle: tauri::AppHandle) {
    tauri::async_runtime::spawn(async move {
        let updater = match handle.updater() {
            Ok(u) => u,
            Err(e) => {
                eprintln!("[updater] init failed: {e}");
                return;
            }
        };
        match updater.check().await {
            Ok(Some(update)) => {
                eprintln!("[updater] update {} available, installing", update.version);
                if let Err(e) = update.download_and_install(|_, _| {}, || {}).await {
                    eprintln!("[updater] install failed: {e}");
                }
            }
            Ok(None) => eprintln!("[updater] up to date"),
            Err(e) => eprintln!("[updater] check failed (continuing): {e}"),
        }
    });
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
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

            // 2. fire-and-forget auto-update check (no-op off-desktop / on any error)
            #[cfg(desktop)]
            spawn_update_check(app.handle().clone());

            // 3. wait for the sidecar, then open the window onto it (it serves the SPA + API)
            wait_for_server(PORT);
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
