# Limn desktop

A native shell (Tauri) around the Python core — SPEC §3 v3.

## How it works

1. **First launch** bootstraps a private runtime: finds (or downloads) `uv`,
   creates a venv in the app-data dir with a uv-managed Python, and installs
   `limn[serve]` pinned to `LIMN_VERSION` in `src-tauri/src/main.rs`. No
   system Python required; the installer stays a few MB ("thin installer,
   not a 1 GB bundle").
2. The shell runs `limn serve` on a random localhost port as a sidecar
   (killed on exit) and shows its web UI in the window via an iframe.
3. **Settings** (⚙, shown automatically on first run) is the BYO-provider
   screen: provider, server URL, API key, model → written to `~/.limn.yaml`
   (chmod 600), the same config the CLI uses. Saves land in `Pictures/Limn`.

Privacy: no account, no telemetry, no bundled cloud — the only egress is the
generation request to the provider the user configures.

## Develop

```bash
cargo install tauri-cli --locked
cd desktop
cargo tauri dev      # or: cargo tauri build
```

(On this repo's exFAT drive, set `CARGO_TARGET_DIR` to an internal disk.)

## Release

Bump `LIMN_VERSION` (if a new limn is on PyPI) and the versions in
`src-tauri/tauri.conf.json` + `src-tauri/Cargo.toml`, then:

```bash
git tag desktop-v0.1.0 && git push origin desktop-v0.1.0
```

`.github/workflows/desktop.yml` builds macOS (arm64 + x86_64), Windows
(msi/exe) and Linux (AppImage/deb/rpm) and attaches them to a **draft**
GitHub release — review and publish it. Builds are unsigned; the release
notes tell users how to open them.
