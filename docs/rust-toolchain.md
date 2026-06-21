# Rust toolchain & MSRV

The Tauri shell (`desktop/src-tauri/`) is the only Rust in this repo. This note documents which
Rust version it needs and how that version is currently chosen in CI. Most people never touch Rust —
the app ships as a frozen binary (see `RELEASING.md`). This matters only if you **build from source**.

## Minimum Supported Rust Version (MSRV): **1.77.2**

`desktop/src-tauri/Cargo.toml` declares `edition = "2021"` and pins Tauri v2 (`Cargo.lock`:
`tauri 2.11.3`). Tauri v2's own MSRV is **Rust 1.77.2**, and that floor propagates to this crate via
`tauri` / `tauri-build` and their transitive deps (`serde`, `tokio`, …). So:

> **Build from source with stable Rust ≥ 1.77.2.** Older toolchains are not supported and may fail
> to compile `tauri` or one of its dependencies.

Install / upgrade via [rustup](https://rustup.rs):

```sh
rustup toolchain install stable   # any stable ≥ 1.77.2
rustc --version
```

`Cargo.toml` does **not** carry a `rust-version` field today, so Cargo won't itself reject an older
toolchain with a clear message — you'd hit a deep dependency compile error instead. 1.77.2 is the
floor; in practice we build (and CI builds) on current **stable**, which is always newer.

## How the toolchain is selected in CI

Neither CI job pins an exact version — both install whatever **stable** is current on the runner via
[`dtolnay/rust-toolchain`](https://github.com/dtolnay/rust-toolchain):

| Workflow | Runner | Toolchain step | Extras |
| --- | --- | --- | --- |
| `.github/workflows/ci-rust.yml` (lint/test gate) | `macos-14` | `dtolnay/rust-toolchain@stable` | `components: rustfmt, clippy` |
| `.github/workflows/release-macos.yml` (release build) | `macos-14` | `dtolnay/rust-toolchain@stable` | `targets: aarch64-apple-darwin` |

Because `@stable` floats, the exact compiler changes over time and differs between a CI run today and
one six months from now. As long as stable stays ≥ 1.77.2 (it always will) the build is fine, but the
toolchain is **not reproducible** — two builds of the same commit can use different `rustc` versions.

## Recommendation: pin via `rust-toolchain.toml`

For reproducible source builds (and so a contributor's local `rustc` matches CI), add a
`rust-toolchain.toml` at `desktop/src-tauri/` that rustup auto-respects:

```toml
[toolchain]
channel = "1.77.2"            # or a pinned recent stable, e.g. "1.83.0"
components = ["rustfmt", "clippy"]
targets = ["aarch64-apple-darwin"]
```

This is **not** committed yet (the file does not exist anywhere in the repo). Pinning it would make
`dtolnay/rust-toolchain` install the named channel instead of floating `@stable`, giving every
build — CI and local — the same compiler. Track this as follow-up: add the file and, optionally,
mirror the floor as `rust-version = "1.77.2"` in `Cargo.toml` so Cargo emits a friendly error on too-old
toolchains.
