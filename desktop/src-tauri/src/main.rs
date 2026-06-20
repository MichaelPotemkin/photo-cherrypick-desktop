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

use tauri::{Emitter, Listener, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;
#[cfg(desktop)]
use tauri_plugin_updater::UpdaterExt;

const PORT: u16 = 8756;

// A freshly-downloaded unsigned build is quarantined; the nested `cull-server` sidecar inherits
// com.apple.quarantine and macOS blocks the helper when the app spawns it. The MAIN app has already
// been approved by the user (that's how we got here), so strip the quarantine flag off the bundled
// sidecar before launching it — the user never has to touch a terminal. Best-effort: a no-op when
// the attribute isn't present, and only compiled on macOS.
#[cfg(target_os = "macos")]
fn dequarantine_sidecar() {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(sidecar) = exe.parent().map(|d| d.join("cull-server")) {
            let _ = std::process::Command::new("/usr/bin/xattr")
                .args(["-d", "com.apple.quarantine"])
                .arg(&sidecar)
                .status();
        }
    }
}
#[cfg(not(target_os = "macos"))]
fn dequarantine_sidecar() {}

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

// Latest update event, cached so a freshly-loaded SPA can be replayed the current state on its
// `spa-ready` signal. Emits to a not-yet-subscribed webview are dropped, and on a cold start the
// whole download can finish before the webview (and the SPA's listeners) even exist.
#[cfg(desktop)]
type UpdateCache = std::sync::Arc<std::sync::Mutex<Option<(String, serde_json::Value)>>>;

// Best-effort update check on startup (background task). Downloads a newer version silently while
// reporting progress to the SPA, which renders the whole update UI in-app (version label → progress
// bar → "Update ready" button) instead of a native OS dialog. The update applies on the next launch
// either way; the in-app button just lets the user relaunch now via the `update-relaunch` event
// (see the listener in `main`). On macOS the replaced bundle inherits the running app's ad-hoc
// signature, so the in-place swap works without an Apple Developer ID.
//
// IPC is event-only on purpose: the SPA is served from the remote 127.0.0.1 origin, where core
// events (`core:default`) are permitted — the same constraint that makes the folder dialog work.
#[cfg(desktop)]
fn spawn_update_check(handle: tauri::AppHandle, cache: UpdateCache) {
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::sync::Arc;

    // Emit an update event to the SPA AND remember it as the latest state, so a SPA that subscribes
    // late (cold start) gets the current state replayed on `spa-ready` instead of missing it.
    fn emit_state(
        handle: &tauri::AppHandle,
        cache: &UpdateCache,
        name: &str,
        payload: serde_json::Value,
    ) {
        *cache.lock().unwrap() = Some((name.to_string(), payload.clone()));
        let _ = handle.emit(name, payload);
    }

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
                let version = update.version.clone();
                eprintln!("[updater] update {version} available, downloading in background");
                emit_state(
                    &handle,
                    &cache,
                    "update-available",
                    serde_json::json!({ "version": version }),
                );

                let downloaded = Arc::new(AtomicU64::new(0));
                let progress_handle = handle.clone();
                let progress_cache = cache.clone();
                let progress_total = downloaded.clone();
                let result = update
                    .download_and_install(
                        move |chunk_len, content_len| {
                            let total = progress_total
                                .fetch_add(chunk_len as u64, Ordering::Relaxed)
                                + chunk_len as u64;
                            emit_state(
                                &progress_handle,
                                &progress_cache,
                                "update-progress",
                                serde_json::json!({ "downloaded": total, "total": content_len }),
                            );
                        },
                        || {},
                    )
                    .await;

                match result {
                    Ok(_) => {
                        eprintln!("[updater] {version} downloaded; ready to relaunch");
                        emit_state(
                            &handle,
                            &cache,
                            "update-ready",
                            serde_json::json!({ "version": version }),
                        );
                    }
                    Err(e) => {
                        eprintln!("[updater] install failed: {e}");
                        emit_state(
                            &handle,
                            &cache,
                            "update-error",
                            serde_json::json!({ "message": e.to_string() }),
                        );
                    }
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
            // 0. clear the bundled sidecar's quarantine so macOS doesn't block the nested helper
            //    on a freshly-downloaded unsigned build (no terminal step for the user).
            dequarantine_sidecar();

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

            // 2. fire-and-forget auto-update check (no-op off-desktop / on any error), and listen for
            //    the SPA's in-app "Update ready" button (the `update-relaunch` event) to apply a
            //    staged update now. restart() relaunches into the freshly-installed bundle.
            #[cfg(desktop)]
            {
                let update_cache: UpdateCache =
                    std::sync::Arc::new(std::sync::Mutex::new(None));
                spawn_update_check(app.handle().clone(), update_cache.clone());

                // The SPA emits `spa-ready` once its listeners are registered; replay the latest
                // update state to it so a download that finished before the webview existed still
                // surfaces the in-app progress / "Update ready" button this session.
                let replay_handle = app.handle().clone();
                let replay_cache = update_cache.clone();
                app.handle().listen_any("spa-ready", move |_event| {
                    if let Some((name, payload)) = replay_cache.lock().unwrap().clone() {
                        let _ = replay_handle.emit(name.as_str(), payload);
                    }
                });

                let relaunch_handle = app.handle().clone();
                app.handle().listen_any("update-relaunch", move |_event| {
                    relaunch_handle.restart();
                });
            }

            // 3. wait for the sidecar, then open the window onto it (it serves the SPA + API).
            //    The `?v=<version>` cache-buster is load-bearing: the WKWebView persists its cache
            //    across app versions and does NOT reliably revalidate the top-level document even with
            //    `Cache-Control: no-store` (server/app.py), so after an auto-update it would serve the
            //    cached old index.html — pointing at the previous hashed bundle — and the new UI would
            //    never appear. A version-stamped URL is one WKWebView has never cached, forcing a fresh
            //    document (which then references the new content-hashed assets). Same origin, so the
            //    SPA's localStorage — e.g. the language choice — is preserved across versions.
            let version = app.package_info().version.to_string();
            wait_for_server(PORT);
            let url = format!("http://127.0.0.1:{PORT}/?v={version}");
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url.parse().unwrap()))
                .title("Photo Cherrypick")
                .inner_size(1280.0, 860.0)
                .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
