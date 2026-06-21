# Updater signing key: lifecycle & disaster recovery

How the **minisign** keypair that signs Photo Cherrypick's auto-update artifacts works, why losing
or leaking it is a release-blocking event, and the exact runbook for rotating to a fresh key when
that happens.

This is the disaster-recovery companion to [`RELEASING.md`](../RELEASING.md), which covers the
one-time signing-secret setup and the normal release flow. Read this **before** you need it — once
the private key is gone, the recovery path forces a manual re-install on every existing user.

> This is the **updater** key (a free minisign keypair, distinct from Apple code signing). Photo
> Cherrypick ships **unsigned** with no Apple Developer ID / notarization; the minisign signature is
> the only thing the in-app updater trusts.

---

## How the key is wired

Auto-update is Tauri v2 `tauri-plugin-updater`. Every release uploads an `.app.tar.gz` updater
artifact, its detached `.sig` (a minisign signature), and `latest.json` to the GitHub Release.
Installed apps fetch `latest.json` from
`https://github.com/MichaelPotemkin/photo-cherrypick-desktop/releases/latest/download/latest.json`
(the `plugins.updater.endpoints` entry in `tauri.conf.json`) and **verify the `.sig` against the
public key baked into the running binary** before installing anything.

There are three copies of the key, in two halves:

| Half        | Where it lives                                                            | Role                                                                                          |
| ----------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| **Public**  | `plugins.updater.pubkey` in `desktop/src-tauri/tauri.conf.json`           | Committed to the repo and **baked into the app at build time**. Each install trusts this key. |
| **Private** | GitHub Actions secret `TAURI_SIGNING_PRIVATE_KEY`                         | CI reads it to sign the updater artifacts during the release build.                           |
| **Private** | Local file `~/.photo-cherrypick/updater.key` (per-maintainer backup)      | The canonical copy the CI secret was pasted from; generated with an **empty** passphrase.     |

The release workflow (`.github/workflows/release-macos.yml`) passes the secret to
`tauri-apps/tauri-action` via the env vars the action expects:

- `TAURI_SIGNING_PRIVATE_KEY` — `${{ secrets.TAURI_SIGNING_PRIVATE_KEY }}`
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` — `${{ secrets.TAURI_SIGNING_PRIVATE_KEY_PASSWORD }}` (empty;
  the key has no passphrase)

The `Check release prerequisites` step **fails the build fast** if `TAURI_SIGNING_PRIVATE_KEY` is
missing, so a release can never ship updater artifacts that no install would accept because they were
left unsigned.

The matching public key currently committed to `tauri.conf.json`:

```
dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IDc3RTQ3QTFBNkExRjRDNkYK...
```

(base64; minisign key id `77E47A1A6A1F4C6F`). Decode it with `echo <pubkey> | base64 -d` if you ever
need to confirm which key id a build trusts.

---

## Why losing or leaking the key is serious

The embedded public key is immutable for every copy already installed — it was compiled into the
binary. That cuts two ways:

- **Lost private key.** You can no longer produce a `.sig` that verifies against the pubkey those
  installs carry. Any new release you publish will have its signature **rejected** by the updater,
  and auto-update silently stops working for **everyone** on the old key — no error the user sees,
  the app just never updates again. You cannot "recover" the same key; minisign keys are not
  derivable, so the only path forward is rotating to a new keypair (below).
- **Leaked private key.** Anyone holding it can sign an artifact that **every existing install will
  trust and auto-install** — i.e. push arbitrary code to all users through the update channel. Treat
  a leak as a security incident: rotate immediately and assume the old key is burned.

Either way the fix is the same rotation, and the same hard consequence applies:

> **A new keypair breaks the auto-update bridge for current users.** Installs on the OLD pubkey will
> never accept a build signed by the NEW key, because they still trust only the old key baked into
> them. They are stranded on whatever version they have and must **manually re-download and
> re-install** the first build that carries the new pubkey. From that build onward, auto-update
> works again. There is no way to remotely re-key an existing install.

This is why the backup discipline in `RELEASING.md` matters: keeping
`~/.photo-cherrypick/updater.key` in a password manager (and/or with a trusted second maintainer) is
what keeps you out of this runbook entirely.

---

## Recovery runbook: rotate to a fresh key

Run this when the private key is **lost** (you no longer have `~/.photo-cherrypick/updater.key` and
it isn't in the GitHub secret either) or **compromised**. All of it happens through the normal
release machinery — there is no special CI path.

### 1. Confirm the key is actually gone / burned

- **Lost:** check the backup (password manager, second maintainer) and the existing
  `TAURI_SIGNING_PRIVATE_KEY` GitHub secret. If you can recover the key contents from either, you do
  **not** need to rotate — restore it and ship normally.
- **Symptom of a release built without the right key:** the `.sig` won't verify against the embedded
  pubkey, so installed apps fetch `latest.json`, attempt the update, and reject it — auto-update
  appears dead in the field even though a Release exists.

Only proceed if the key is genuinely unrecoverable or leaked.

### 2. Generate a fresh minisign keypair

Same command `RELEASING.md` uses for the initial setup (empty passphrase, matching the existing CI
secret convention):

```sh
npx @tauri-apps/cli@2 signer generate -w ~/.photo-cherrypick/updater.key
```

This writes the new private key to `~/.photo-cherrypick/updater.key` and prints (and writes
`~/.photo-cherrypick/updater.key.pub`) the new **public** key. **Back up the new private key
immediately** — a password manager and/or a trusted second maintainer — so you never run this
runbook twice.

### 3. Replace the public key in `tauri.conf.json`

Paste the new `.pub` contents into `plugins.updater.pubkey` in `desktop/src-tauri/tauri.conf.json`,
replacing the old value. Commit and merge it to `main` (via PR — direct pushes to `main` are not
allowed). Every build from this commit onward bakes in the new pubkey.

### 4. Rotate the CI signing secret

In the GitHub repo → **Settings → Secrets and variables → Actions**, update
`TAURI_SIGNING_PRIVATE_KEY` to the **full contents** of the new `~/.photo-cherrypick/updater.key`.
Leave `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` empty (the key has no passphrase). The new private key and
the new committed pubkey must be from the **same** keypair, or CI will sign with a key the new build
doesn't trust.

### 5. Ship a new build with the new key

Bump the version and cut a release exactly as in `RELEASING.md` (the tag must match
`tauri.conf.json`'s `version`). CI signs the updater artifacts with the new private key; the build
embeds the new pubkey, so **future** auto-updates verify and resume — for anyone running this build
or later.

### 6. Tell existing users they must re-install manually

Installs on the old pubkey **cannot** auto-update across the key change. Make the new build's GitHub
Release (and the itch.io page) clearly state that current users must download and re-install the
`.dmg` once; after that, auto-update is restored. Without this notice, users on the old key will
simply stop receiving updates with no visible error.

---

## Quick reference

| Item                              | Value                                                            |
| --------------------------------- | --------------------------------------------------------------- |
| Public key (embedded at build)    | `plugins.updater.pubkey` in `desktop/src-tauri/tauri.conf.json` |
| Private key — CI                  | GitHub Actions secret `TAURI_SIGNING_PRIVATE_KEY`               |
| Private key — passphrase secret   | `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` (empty)                    |
| Private key — local backup        | `~/.photo-cherrypick/updater.key` (+ `.key.pub`)                |
| Generate keypair                  | `npx @tauri-apps/cli@2 signer generate -w ~/.photo-cherrypick/updater.key` |
| Updater manifest endpoint         | `.../releases/latest/download/latest.json`                      |
| After rotation                    | Existing installs must **re-download & re-install** once        |
