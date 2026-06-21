# Dev runbook: the dual-instance collision gotcha

Two copies of the app on the same Mac fight over **one fixed loopback port** and **one bundle
id**. Whichever binds the port first wins; the other ends up showing the first one's UI. This bites
developers immediately when a local dev/`target` build runs alongside the installed
`/Applications` copy, and the symptom — a version that doesn't match the UI — is confusing until you
know where it comes from.

## The two shared singletons

The shell is hardwired to a single loopback endpoint:

```rust
const PORT: u16 = 8756;   // desktop/src-tauri/src/main.rs
```

Every copy of the app spawns its `cull-server` sidecar with `--host 127.0.0.1 --port 8756`
(`setup()` in `main.rs`), then opens its webview onto `http://127.0.0.1:8756/?v=<version>`. The
port is **not** per-instance — the first process to bind `127.0.0.1:8756` holds it; a second
sidecar that tries to bind the same port fails (address in use).

The bundle id is also shared across every copy:

```jsonc
"identifier": "dev.photocherrypick.desktop"   // desktop/src-tauri/tauri.conf.json
```

The installed build, a `cargo tauri build` artifact under `target/`, and an old leftover copy all
carry the same id. That id is what `tauri-plugin-single-instance` keys on, and (per the issue) it's
also what the data dir is named after — `~/.photo-cherrypick-desktop` (overridable via
`CULL_DATA_DIR`, see `server/app.py`).

## The failure

Launch a second app copy (same bundle id) while the first is running:

1. The first instance already holds `127.0.0.1:8756` and is serving **its** SPA bundle there.
2. The second instance's sidecar can't bind 8756 (already taken), but the second webview still
   navigates to `http://127.0.0.1:8756/?v=<its-version>` — so it **loads the FIRST instance's
   SPA**.
3. The footer version and the UI now disagree. The footer label comes from the running shell's own
   `tauri.conf.json` version (`getAppVersion()` → `t.app.getVersion()` in `frontend/src/lib/tauri.ts`,
   rendered by `UpdateFooter`), i.e. the **second** copy. The actual UI/HTML is whatever the
   **first** copy's bound sidecar serves. You get "footer says one version, UI is from another."

This is exactly the comment at the top of the `main` builder in `main.rs`:

> a second launch (a stray/older copy, e.g. left over after an update) would otherwise bind nothing
> — the running instance already holds the loopback port, so the new window loads the OLD instance's
> SPA and shows a stale UI with a mismatched version.

## How production mitigates it

`tauri-plugin-single-instance` is registered **first**, before every other plugin, precisely so it
runs before any port/window work:

```rust
// MUST be the first plugin …
.plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}))
```

When you double-click the **same** installed app twice, the second process detects the existing
instance (matched by bundle id `dev.photocherrypick.desktop`), **focuses the already-open window**,
and the second process **exits** — no second sidecar, no second webview, no collision. So end users
who only have the one `/Applications` build never hit this.

### Why it doesn't save you in dev

Single-instance matches on the **bundle id**, not on the binary path or port. In production every
launch is the same `.app`, so the guard works. But it still has two gaps a developer can fall into:

- **A dev server with no shell.** Running the backend standalone
  (`python -m server.run --port 8756`) is just a FastAPI process — it never registers with the
  single-instance plugin. Launch the installed app afterward and one of them loses the port; whoever
  bound 8756 first wins, and the other's webview loads the wrong SPA (or the sidecar fails to bind).
- **A different on-disk copy can still slip through depending on how it's launched** (e.g. running
  the unpackaged binary directly rather than the registered `.app`). The safe assumption: don't rely
  on the guard during development — assume any second thing touching 8756 collides.

## Symptoms to recognize

- The **footer version doesn't match the UI** — e.g. the footer reads the version of the build you
  *think* you launched, but the screen shows an older/newer layout or a change you didn't expect.
- A code change you just rebuilt **isn't showing up**, because the webview is being served by the
  *other* copy's sidecar.
- The second app's sidecar logs an **address-already-in-use / bind** error for `127.0.0.1:8756`
  (visible as `[cull-server] …` lines on stderr).

## How to detect

1. **See who owns the port:**

   ```bash
   lsof -i :8756
   ```

   The `COMMAND`/`PID` columns tell you which process is bound. Map the PID back to a binary:

   ```bash
   ps -o pid,comm,args -p <PID>
   ```

   If the bound binary lives under `/Applications/Photo Cherrypick.app` but you meant to be testing a
   `target/.../bundle/...` build (or vice versa), that's the collision.

2. **Compare the footer version against the build you launched.** The footer is the running shell's
   `tauri.conf.json` version; if it doesn't match the bundle you opened, a different copy is in play.

3. **Check for more than one running copy:**

   ```bash
   pgrep -fl 'Photo Cherrypick|cull-server'
   ```

   More than one `cull-server` (or two shells) means two instances are live.

## How to fix / avoid in development

- **Quit ALL instances first.** Quit the `/Applications` build *and* any dev/`target` build, and
  kill any standalone server before launching the one you actually want to test:

  ```bash
  pkill -f 'Photo Cherrypick'
  pkill -f cull-server
  # or, target the port owner specifically:
  kill "$(lsof -ti :8756)"
  ```

- **Don't run a dev build alongside the installed app.** Pick one. If you want to iterate on the
  packaged shell, quit the `/Applications` copy first (and vice versa).

- **Remove stray `target/` builds.** Old `cargo tauri build` artifacts under
  `desktop/src-tauri/target/.../bundle/` share the same bundle id and port; delete or ignore the
  ones you're not testing so you don't accidentally launch a leftover. (This is the "stray/older
  copy" the `main.rs` comment warns about.)

- **For pure backend work, run the server standalone and use a browser**, not the packaged shell:

  ```bash
  python -m server.run --port 8756   # then open http://127.0.0.1:8756
  ```

  Just make sure no installed app is already holding 8756 (see detection above) — they collide the
  same way.

- **Isolate dev data if you must run two things.** The data dir is keyed off the bundle id
  (`~/.photo-cherrypick-desktop`). The server honors `CULL_DATA_DIR`, so pointing a dev server at a
  separate directory keeps its database/cache from mixing with the installed app's:

  ```bash
  CULL_DATA_DIR=~/.photo-cherrypick-dev python -m server.run --port 8756
  ```

  Note this only separates **data** — both still want port `8756`, so you must still avoid running
  two on the same port at once.
