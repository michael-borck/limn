# Limn — agent handover / working notes

This file is auto-loaded when you open a Claude Code session in this repo. It
tells you what Limn is, where things stand, and how to start. **`SPEC.md` is the
source of truth** — read it before writing any code.

## What Limn is

A small, privacy-first **text-to-image** tool: type a prompt, get an image. No
account, minimal options, bring your own provider. Surfaces (in order): a CLI, a
simple web UI (generate / view / save / delete / regenerate), then a Tauri
desktop app with bring-your-own-provider, plus a rate-limited, non-storing demo.

## Current status

**0.4.0: provider model listing.** `list_models()` on every provider
(SwarmUI /API/ListModels with weight-extension stripping — the generate API
wants bare names like "juggernautXL_v9"; OpenAI /models filtered to image
models, compatible unfiltered; Gemini /models filtered to imagen*), CLI
`limn models`, web UI ⟳ next to the model field, POST /api/models (demo
ignores overrides — no proxying). serve has CORS for tauri://localhost only,
so the desktop Settings sheet can call the sidecar. NOTE: SwarmUI *requires*
a model on generate. Desktop pins limn via LIMN_VERSION + a venv marker file
that auto-upgrades existing runtimes when the pin changes.

**M4 (desktop) built: Tauri shell in `desktop/`, CI-built installers.**
Architecture: Rust shell (tauri v2, vanilla-HTML frontend, no node/npm) that
(1) bootstraps a private runtime on first launch — finds/downloads `uv`,
`uv venv --python 3.12` in app-data (uv downloads managed CPython, no system
Python), installs `limn[serve]==LIMN_VERSION` (const in main.rs — bump with
PyPI releases); (2) spawns `limn serve` on a random localhost port as a
sidecar (killed on RunEvent::Exit), `--out-dir` = Pictures/Limn; (3) shows
the served UI in an iframe under a header bar with a ⚙ BYOK Settings sheet
that reads/writes ~/.limn.yaml (merge-preserving, chmod 600) — shown
automatically when no provider is configured. Release: tag `desktop-v*` →
`.github/workflows/desktop.yml` (tauri-action) builds unsigned macOS
arm64+x86_64 / Windows / Linux installers into a draft GitHub release.
Local dev on this machine: set CARGO_TARGET_DIR to internal disk (exFAT).

**M3 (demo mode) done: shipped in 0.3.0.** `limn serve --demo` (or
LIMN_DEMO=1): tokenless but bounded — 10 images/hour/IP (X-Forwarded-For
aware), provider+model locked to server config (visitors can't route spend),
count=1, size clamped ≤1024px, Save returns 403 (UI swaps to Download with
Content-Disposition), gallery entries expire after 15 min (lazy eviction),
banner with pip-install nudge. Deploy notes in docs/demo-deploy.md. The
actual hosting (app.limn.<domain>, reverse proxy) is infra the user does.

**M2 (web UI) done: `limn serve` shipped in 0.2.0.** `src/limn/serve.py` is a
FastAPI app factory (`create_app(config, token, out_dir)`) + a self-contained
`serve_page.html` (package data, no CDNs). Session gallery is in-memory only
(dict capped at 100, privacy by design); endpoints: POST /api/generate,
GET/DELETE /api/images/{id}, POST .../save (basename-sanitized, never
overwrites), GET /api/config. Token auth (Bearer / ?token= / cookie) gates
everything; `limn serve` auto-generates a token when binding non-locally.
The CLI is now a `DefaultCommandGroup`: bare `limn "prompt"` routes to the
`generate` command, `limn serve` is a real subcommand. Default port 5466
("LIMN" on a phone keypad). Verified end-to-end against real Imagen.

**M1 (CLI) built and published to PyPI as `limn` 0.1.0.** The package lives in
`src/limn/`: `config.py` (layered ~/.limn.yaml < ./limn.yaml < flags, `${VAR}`
expansion, per-provider `providers:` overlays), `providers/` (swarmui,
openai, openai-compatible, gemini/imagen — all plain `requests`, no SDKs),
`core.py` (generate + save with slug naming / no-overwrite), `cli.py` (Typer,
single command). Tests in `tests/` (45, all green), basedpyright zero errors,
ruff clean. Verified end-to-end against the real Imagen API.

Design choices made during M1 (beyond SPEC):
- Providers raise `ProviderError` and the CLI exits non-zero — **no** silent
  text-image fallback like slide-stream (that only makes sense in a video
  pipeline).
- `openai`/`dalle` and `openai-compatible` share one class; the compatible
  variant *requires* `base_url` so a stray OPENAI_API_KEY never sends prompts
  to the wrong server.
- Imagen (Gemini API) gets nearest-aspect-ratio mapping from `--size`;
  seed/negative are warn-and-ignore on backends that lack them (OpenAI,
  Gemini API).

## Machine gotcha (this repo lives on an exFAT drive)

`uv sync` with a local `.venv` fails here: macOS writes AppleDouble `._*`
files (SIP-protected `com.apple.provenance` xattr) into binary wheels (ruff,
basedpyright) and uv's RECORD validation rejects them. Workaround used:

```bash
export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/limn"   # venv on internal disk
uv sync --all-groups
uv run --no-sync ruff check src tests && uv run --no-sync basedpyright && uv run --no-sync pytest
```

## Next milestones

M2 (web UI, `limn serve` behind a `[serve]` extra, like `slide-stream serve`),
M3 (hosted demo), M4 (Tauri desktop). Release flow: bump version in
`pyproject.toml` + `src/limn/__init__.py`, `uv build`, `twine upload dist/*`.

## Key decisions already made

- **Standalone**, not a slide-stream dependency (slide-stream is a video tool).
  Reuse the *pattern*, not the package. Extract a shared image-providers lib
  later only if it clearly pays off.
- **Generative providers only** (Limn *makes* images) — no Pexels/Unsplash stock
  unless the user asks.
- **Minimal knobs** on purpose: prompt, size, count, seed. Advanced params live
  in the provider. Don't add options without a reason.
- **Privacy-first:** no account, no telemetry, no server-side storage of prompts
  or images; the demo is rate-limited and ephemeral.

## Reference

- Companion project: `../slide-stream` (on this machine) —
  https://github.com/michael-borck/slide-stream, published on PyPI. Its image
  providers, layered config, and `serve` web UI are the templates to adapt.
- Repo: https://github.com/michael-borck/limn (public).
