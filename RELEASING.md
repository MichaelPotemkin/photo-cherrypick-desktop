# Releasing Photo Cherrypick

How to cut a public release of **Photo Cherrypick** (macOS, Apple Silicon, unsigned).

A release is driven entirely by a **git tag** matching `v*`. Pushing the tag triggers GitHub Actions
(on the `macos-14` arm64 runner), which builds the `.dmg` + Tauri **updater** artifacts and publishes
them to a **GitHub Release**. You then upload the same `.dmg` to **itch.io** (the primary public
download). GitHub Releases is also the free static endpoint the in-app auto-updater reads.

- App: `Photo Cherrypick` — identifier `dev.photocherrypick.desktop`
- Target: **macOS Apple Silicon (arm64) only**, target triple `aarch64-apple-darwin`
- Distribution: **unsigned** (no Apple Developer ID, no notarization)
- Auto-update: Tauri v2 `tauri-plugin-updater`, signed with a **minisign** keypair (not Apple signing)

---

## One-time setup: updater signing secret (do this once, before your first release)

Auto-update is **already wired** in the repo — `tauri-plugin-updater` is in `Cargo.toml` and
registered in `src/main.rs`, `plugins.updater` + `bundle.createUpdaterArtifacts` are set in
`tauri.conf.json`, and the updater **public** key is already committed there. A free **minisign**
keypair (unrelated to Apple code signing) was generated for this project at:

```
~/.photo-cherrypick/updater.key       # PRIVATE — keep secret; generated with an EMPTY passphrase
~/.photo-cherrypick/updater.key.pub   # public — already pasted into tauri.conf.json
```

The only thing left is to give CI the **private** key:

### 1. Add the GitHub secret

In the GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret name                          | Value                                                       |
| ------------------------------------ | ----------------------------------------------------------- |
| `TAURI_SIGNING_PRIVATE_KEY`          | the **full contents** of `~/.photo-cherrypick/updater.key`  |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | leave **empty** (the key has no passphrase) — or omit it    |

CI reads these to sign the updater artifacts; it **fails fast** if `TAURI_SIGNING_PRIVATE_KEY` is
missing. The built-in `GITHUB_TOKEN` (no secret needed) lets the workflow create the Release.

### 2. Back up the private key

Copy `~/.photo-cherrypick/updater.key` somewhere safe (a password manager). **If you lose it you
cannot ship updates existing installs will accept** — they'd have to re-download manually.

> **Prefer to roll your own key?** Run
> `npx @tauri-apps/cli@2 signer generate -w ~/.photo-cherrypick/updater.key`, paste the new `.pub`
> contents into `plugins.updater.pubkey` in `tauri.conf.json`, and set the two secrets to match.

You only do this section once. Subsequent releases are just the steps below.

---

## Cut a release

### 1. Bump the version in all three places (they must match)

The version lives in three files — keep them identical:

| File                                      | Field        |
| ----------------------------------------- | ------------ |
| `desktop/src-tauri/tauri.conf.json`       | `"version"`  |
| `frontend/package.json`                   | `"version"`  |
| `desktop/src-tauri/Cargo.toml`            | `version`    |

For the first public release, set all three to `1.0.0`. The Tauri `version` is what the updater
compares, so a release MUST have a higher version than what's installed or clients won't update.

### 2. Commit the bump (on a branch / PR, per repo policy — never commit straight to `main`)

```bash
git checkout -b release/v1.0.0
git add desktop/src-tauri/tauri.conf.json frontend/package.json desktop/src-tauri/Cargo.toml
git commit -m "Release v1.0.0"
git push -u origin release/v1.0.0
# open + merge the PR into main
```

### 3. Tag and push the tag (the tag is what triggers CI)

After the bump is on `main`:

```bash
git checkout main && git pull
git tag v1.0.0
git push origin v1.0.0
```

The tag **must** match the `v*` pattern (e.g. `v1.0.0`) and should match the version you set in step 1.

### 4. CI builds + publishes (automatic)

The `release` workflow runs on the `macos-14` (arm64) runner and:

1. builds the SPA (`cd frontend && npm ci && npm run build`),
2. freezes the Python sidecar with PyInstaller and places it at
   `desktop/src-tauri/bin/cull-server-aarch64-apple-darwin`,
3. runs `tauri build` (via `tauri-action`), which produces the `.dmg`, the updater artifact
   (`.app.tar.gz`) and its `.sig`, signed with the secrets above,
4. creates/updates the **GitHub Release** for the tag and uploads the `.dmg`, the updater
   artifacts, and **`latest.json`** (the manifest the in-app updater fetches).

When the workflow finishes, check the Release at
`https://github.com/MichaelPotemkin/photo-cherrypick-desktop/releases/tag/v1.0.0`:
- `Photo Cherrypick_1.0.0_aarch64.dmg` is attached,
- `latest.json`, the `.app.tar.gz`, and `.app.tar.gz.sig` are attached,
- the Release is **published** (not draft) so `…/releases/latest/download/latest.json` resolves —
  this is the URL the installed app polls, so existing installs auto-update from here.

### 5. Upload the `.dmg` to itch.io (primary public download)

GitHub hosts the auto-update artifacts; **itch.io is where the public downloads the app.** Download
the `.dmg` from the GitHub Release and upload it to the itch.io project
(`https://fludanutiy.itch.io/photo-cherrypick`) → **Edit game → Uploads**. Mark it as a
**macOS** download and set/refresh the version label.

**Optional automation — itch.io `butler`:** instead of the web uploader you can push the `.dmg`
from your machine (or wire it into CI):

```bash
# one-time: brew install butler ; butler login
butler push "Photo Cherrypick_1.0.0_aarch64.dmg" fludanutiy/photo-cherrypick:osx --userversion 1.0.0
```

### 6. Verify

- Fresh download from itch.io launches after the Gatekeeper bypass (see README → **Download (macOS)**).
- An older install, on next launch, sees the new version and updates itself in place.

---

## Notes & gotchas

- **arm64 only.** CI runs on `macos-14` (Apple Silicon). There is no Intel/`x86_64` build; the
  sidecar is built only for `aarch64-apple-darwin`.
- **Unsigned is intentional.** We do not sign or notarize. End users bypass Gatekeeper once
  (documented in the README). Do not add Apple signing config expecting it to "just work" — that
  requires a paid Developer ID and is out of scope.
- **Updater version is the source of truth.** The updater compares the Tauri `version`. If
  `tauri.conf.json` isn't bumped, clients won't be offered the update even if the tag is new.
- **Keep `latest.json` reachable.** The app polls
  `…/releases/latest/download/latest.json`. Don't delete or unpublish past releases in a way that
  breaks the `latest` redirect, or auto-update silently stops working.
- **Frozen sidecar serves the SPA.** The Tauri webview loads `http://127.0.0.1:8756` (the Python
  server), not Tauri's bundled assets — so `desktop/cull-server.spec` bundles `frontend/dist` into the
  binary and `server/app.py` resolves it under `sys._MEIPASS` when frozen. The spec **fails the build**
  if `frontend/dist` is missing, so the SPA must be built before the freeze (the workflow does this).
  `server/run.py` imports the app **object** (`from server.app import app`), not the `"server.app:app"`
  string, so PyInstaller traces `server`/`desktop_core`/`pipeline` into the bundle.
- **First-launch readiness.** The onefile re-extracts the ML runtime on first launch; `main.rs` polls
  the port (up to ~90s) before opening the window, so a cold start shows the window only once the
  server is up rather than a blank/connection-refused page.
