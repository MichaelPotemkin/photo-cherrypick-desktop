// Tauri v2 shell for Photo Cherrypick (desktop).
//
// Launches the bundled Python sidecar (the FastAPI server frozen with PyInstaller as an onedir tree
// shipped in the app's Resources) which serves the built SPA + the API on 127.0.0.1, WAITS until it is
// accepting connections, then opens a webview onto it. The folder picker comes from tauri-plugin-dialog
// (exposed to the SPA via withGlobalTauri as window.__TAURI__.dialog.open).
//
// Auto-update: tauri-plugin-updater is registered and a best-effort check runs on startup
// (`spawn_update_check`) — it pulls latest.json from the GitHub Release and, if a newer SIGNED build
// is published, downloads + installs it in place. Every failure path (offline, no release yet,
// signature mismatch) is swallowed so the app always continues to launch.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader};
use std::net::{SocketAddr, TcpStream};
use std::process::{Child, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

use tauri::path::BaseDirectory;
use tauri::{Emitter, Listener, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};
#[cfg(desktop)]
use tauri_plugin_updater::UpdaterExt;

const PORT: u16 = 8756;

// A freshly-downloaded unsigned build is quarantined; the bundled sidecar inherits com.apple.quarantine
// and macOS blocks the helper when the app spawns it. The MAIN app has already been approved by the user
// (that's how we got here), so strip the quarantine flag off the onedir sidecar tree before launching it
// — the user never has to touch a terminal. RECURSIVE (-r): under onedir the exe AND every dylib it
// dlopen()s under _internal/ are quarantined, and clearing only the exe would still let macOS block the
// libraries. Best-effort: a no-op when the attribute is absent, and only compiled on macOS.
#[cfg(target_os = "macos")]
fn dequarantine_sidecar(dir: &std::path::Path) {
    let _ = std::process::Command::new("/usr/bin/xattr")
        .args(["-dr", "com.apple.quarantine"])
        .arg(dir)
        .status();
}
#[cfg(not(target_os = "macos"))]
fn dequarantine_sidecar(_dir: &std::path::Path) {}

// Managed handle to our spawned sidecar so we can terminate it when the app exits (see the RunEvent
// handler in `main`). Without this the ~200 MB Python server can outlive the app and keep holding the
// loopback port — orphaning onto it so the NEXT launch's webview connects to this stale server.
struct SidecarChild(std::sync::Mutex<Option<Child>>);

// Set true when WE intentionally stop the sidecar (on app exit), so the stderr-EOF monitor can tell an
// orderly shutdown from an unexpected crash and only warns about the latter. (#67)
struct ShutdownFlag(Arc<AtomicBool>);

// Kill any cull-server already running BEFORE we spawn ours. tauri-plugin-single-instance guarantees
// we're the only app instance, so any live cull-server is an orphan from a previous run (a crash,
// force-quit, or an update whose child outlived the parent). Left alone it keeps our fixed loopback
// port, and our webview connects to ITS stale server — serving an OLD SPA under a NEW app version
// (the recurring "updated, but the interface is from the previous version" bug). SIGKILL because a
// graceful SIGTERM lets uvicorn linger and hold the socket; then wait for the port to actually free
// before the caller spawns our own.
#[cfg(target_os = "macos")]
fn kill_stale_sidecars(port: u16) {
    let _ = std::process::Command::new("/usr/bin/pkill")
        .args(["-9", "-x", "cull-server"])
        .status();
    let addr: SocketAddr = ([127, 0, 0, 1], port).into();
    for _ in 0..20 {
        if TcpStream::connect_timeout(&addr, Duration::from_millis(100)).is_err() {
            return; // port released
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    eprintln!("[shell] warning: port {port} still busy after killing stale sidecar(s)");
}
#[cfg(not(target_os = "macos"))]
fn kill_stale_sidecars(_port: u16) {}

// Poll until the sidecar is accepting TCP connections; return whether it came up. The onedir sidecar
// starts in ~2s once warm, but the FIRST launch after an install/update pays a one-time cost (cold disk
// read of the ~200 MB runtime + macOS scanning the freshly-written dylibs), so the budget stays generous
// and overridable via CULL_STARTUP_TIMEOUT_SECS.
fn wait_for_server(port: u16) -> bool {
    let addr: SocketAddr = ([127, 0, 0, 1], port).into();
    let secs: u64 = std::env::var("CULL_STARTUP_TIMEOUT_SECS")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(180);
    for _ in 0..(secs * 2).max(1) {
        if TcpStream::connect_timeout(&addr, Duration::from_millis(500)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    eprintln!("[shell] sidecar not ready after {secs}s");
    false
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

    // Check at startup AND on a timer: a long-running session (a photographer may leave the app open
    // for hours) would otherwise never see a release published after launch, since the check ran once
    // when the then-current version was latest. `staged` avoids re-downloading a version already fetched
    // this session on every tick; a failed download simply retries on the next tick.
    const CHECK_INTERVAL: Duration = Duration::from_secs(60 * 60); // hourly

    tauri::async_runtime::spawn(async move {
        let mut staged: Option<String> = None;
        loop {
            match handle.updater() {
                Ok(updater) => match updater.check().await {
                    Ok(Some(update)) if staged.as_deref() != Some(update.version.as_str()) => {
                        let version = update.version.clone();
                        eprintln!(
                            "[updater] update {version} available, downloading in background"
                        );
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
                                staged = Some(version.clone());
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
                    Ok(Some(_)) => {
                        eprintln!("[updater] newest version already staged; awaiting relaunch")
                    }
                    Ok(None) => eprintln!("[updater] up to date"),
                    Err(e) => {
                        // surface check failures (offline, unreachable endpoint, bad signature) the
                        // same way as download failures — logged AND emitted to the SPA — instead of
                        // only printing to stderr.
                        eprintln!("[updater] check failed (continuing): {e}");
                        emit_state(
                            &handle,
                            &cache,
                            "update-error",
                            serde_json::json!({ "message": e.to_string() }),
                        );
                    }
                },
                Err(e) => {
                    eprintln!("[updater] init failed: {e}");
                    emit_state(
                        &handle,
                        &cache,
                        "update-error",
                        serde_json::json!({ "message": e.to_string() }),
                    );
                }
            }
            tokio::time::sleep(CHECK_INTERVAL).await;
        }
    });
}

fn main() {
    tauri::Builder::default()
        // MUST be the first plugin: a second launch (a stray/older copy, e.g. left over after an
        // update) would otherwise bind nothing — the running instance already holds the loopback port,
        // so the new window loads the OLD instance's SPA and shows a stale UI with a mismatched version.
        // Instead, focus the window that's already open and let the second process exit.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            // 0. resolve the onedir sidecar inside the app bundle's Resources (the `cull-server` exe
            //    plus its `_internal/` sibling). Shipped as a Tauri RESOURCE, not externalBin (which is
            //    single-file only) — onedir means the runtime is pre-extracted, so there's no ~30s
            //    per-launch unpack. In a packaged .app this is Contents/Resources/resources/cull-server/.
            let exe = app
                .path()
                .resolve("resources/cull-server/cull-server", BaseDirectory::Resource)?;
            let exe_dir = exe.parent().map(|d| d.to_path_buf()).unwrap_or_default();

            // 0a. ensure the exe is executable — a bundled-resource directory copy doesn't reliably
            //     preserve the +x bit, and a non-executable sidecar fails to spawn (EACCES).
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                if let Ok(meta) = std::fs::metadata(&exe) {
                    let mut perms = meta.permissions();
                    perms.set_mode(perms.mode() | 0o755);
                    let _ = std::fs::set_permissions(&exe, perms);
                }
            }

            // 0b. clear quarantine over the whole onedir tree (exe + _internal/ dylibs) so a freshly
            //     downloaded unsigned build isn't blocked, then kill any orphaned sidecar from a previous
            //     run before we bind our port (see fn docs).
            dequarantine_sidecar(&exe_dir);

            // The loopback port the sidecar binds; overridable via CULL_PORT (testing / relocation),
            // defaulting to PORT. Threaded through everything below so the override is honored.
            let port: u16 = std::env::var("CULL_PORT")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(PORT);
            kill_stale_sidecars(port);

            // 1. spawn the packaged local server (single-user, binds to loopback only). std::process
            //    directly rather than the shell plugin: the path is a dynamic per-install resource path
            //    (can't be statically scoped), and this gives us a plain Child to kill on exit. Forward
            //    the sidecar's stderr with the existing "[cull-server]" prefix via a reader thread.
            let mut child = std::process::Command::new(&exe)
                .args(["--host", "127.0.0.1", "--port", &port.to_string()])
                .current_dir(&exe_dir)
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::piped())
                .spawn()?;

            // Monitor the sidecar's liveness: its stderr reaches EOF exactly when the process exits.
            // If that happens without us asking it to stop (the flag below), it died unexpectedly
            // (crash/OOM) — which would otherwise be silent, leaving the webview hung against a dead
            // server. The flag is flipped on app exit so an orderly shutdown isn't mistaken for a crash.
            let shutting_down = Arc::new(AtomicBool::new(false));
            app.manage(ShutdownFlag(shutting_down.clone()));
            if let Some(stderr) = child.stderr.take() {
                std::thread::spawn(move || {
                    for line in BufReader::new(stderr).lines() {
                        match line {
                            Ok(l) => eprintln!("[cull-server] {l}"),
                            Err(_) => break,
                        }
                    }
                    if !shutting_down.load(Ordering::SeqCst) {
                        eprintln!(
                            "[shell] WARNING: the cull-server sidecar exited unexpectedly (not asked \
                             to stop) — the UI has lost its backend; relaunch the app to recover."
                        );
                    }
                });
            }
            // keep the child handle so we can kill it on exit (don't orphan it onto the port)
            app.manage(SidecarChild(std::sync::Mutex::new(Some(child))));

            // 2. open the window IMMEDIATELY on a bundled "Starting…" splash. setup() must return
            //    promptly for the event loop to render it, so the wait-for-server-then-swap runs on a
            //    background thread below — the user sees a spinner, never a blank window, during a slow
            //    first launch (cold disk + macOS dylib scan on a freshly-installed/updated build).
            let version = app.package_info().version.to_string();
            let window =
                WebviewWindowBuilder::new(app, "main", WebviewUrl::App("splash.html".into()))
                    .title("Photo Cherrypick")
                    .inner_size(1280.0, 860.0)
                    .initialization_script(format!("window.__APP_VERSION__ = {version:?};"))
                    .build()?;

            // 3. auto-update plumbing: replay the latest state to the SPA on `spa-ready`, and apply a
            //    staged update when the in-app button emits `update-relaunch`. The check itself is
            //    started only AFTER the server is up (below), so a background download can't starve a
            //    slow first-launch startup.
            #[cfg(desktop)]
            let updater_handle = app.handle().clone();
            #[cfg(desktop)]
            let update_cache: UpdateCache = std::sync::Arc::new(std::sync::Mutex::new(None));
            #[cfg(desktop)]
            {
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

            // 4. wait for the sidecar off the main thread, then swap the splash for the real app. The
            //    `?v=<version>` cache-buster is load-bearing: the WKWebView persists its cache across
            //    versions and won't reliably revalidate index.html even with no-store, so a version-
            //    stamped URL (one it has never cached) forces the fresh post-update bundle. Same origin,
            //    so the SPA's localStorage (e.g. language) survives. If the server never comes up, show
            //    a retry state instead of a blank window.
            std::thread::spawn(move || {
                if wait_for_server(port) {
                    let target = format!("http://127.0.0.1:{port}/?v={version}");
                    let _ = window.eval(format!("window.location.replace({target:?})"));
                    #[cfg(desktop)]
                    spawn_update_check(updater_handle, update_cache);
                } else {
                    let _ = window.eval("window.__onServerFailed && window.__onServerFailed()");
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            // On exit, terminate our sidecar so it can't outlive the app and orphan onto the loopback
            // port (which would make the next launch render this stale server's old SPA).
            if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
                // mark the shutdown as intentional first, so the liveness monitor doesn't log a
                // spurious "exited unexpectedly" warning when we kill the sidecar below.
                if let Some(flag) = app_handle.try_state::<ShutdownFlag>() {
                    flag.0.store(true, Ordering::SeqCst);
                }
                if let Some(state) = app_handle.try_state::<SidecarChild>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(mut child) = guard.take() {
                            let _ = child.kill();
                            let _ = child.wait();
                        }
                    }
                }
            }
        });
}
