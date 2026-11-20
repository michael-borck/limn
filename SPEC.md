# Limn specification

> *to **limn** (verb): to depict or describe; to paint.*

A small, privacy-first tool that turns a text description into an image. Type a
prompt, get a picture. No account, minimal options, bring your own provider.

## 1. Vision

Most image tools are either a single locked-in web app that keeps an account and
your data on its servers, or a full studio such as ComfyUI or SwarmUI that is
powerful but heavy. Limn sits between them: the simplest possible text-to-image
surface, and you own it.

- Type a description and get an image. That's the whole interaction.
- No account, no lock-in, privacy by default. Your prompts and images are
  yours. On the desktop, nothing leaves your machine except the generation
  request to your chosen provider.
- Bring your own provider. Point Limn at a self-hosted server (SwarmUI or any
  OpenAI-compatible endpoint) or a cloud key (Google Imagen, OpenAI or DALL·E).
  Swap it with one setting.
- Minimal by design. A handful of knobs (prompt, size, count, seed). If you
  want inpainting, ControlNet and node graphs, install something bigger.

Think "Black Forest Labs playground, but standalone, private, and yours."

## 2. Principles

1. Simple beats powerful. One prompt in, one image out. Advanced parameters
   live in the provider, not in Limn.
2. Local-first and private. No account, no telemetry, and no server-side storage
   of prompts or images (the desktop is fully local). The hosted demo is
   rate-limited and stores nothing.
3. Provider-agnostic. The same thin provider abstraction as `slide-stream`'s
   image layer, self-hosted or cloud, chosen by config.
4. Progressive surfaces. The same core powers a CLI, a web UI and a desktop app,
   and each is optional.

## 3. Surfaces (roadmap)

### v1: CLI
```
limn "a red bicycle against a brick wall" -o bike.png
limn "watercolour fox" --provider swarmui --size 1024x1024 --count 4 --seed 42
```
Options: `--provider`, `--model`, `--size`, `--count`, `--seed`, `--negative`,
`--out`. Provider selection + API keys from a config file and/or environment
variables. Prints the saved path(s).

### v2: Web UI (`limn serve`)
A single page: type a prompt, click Generate, and the image appears in the app.
From there you can Save it to disk, Delete it from the session gallery, or
generate another. A running gallery shows the session's images with prompt,
thumbnail and seed. FastAPI and a self-contained HTML page (the same shape as
`slide-stream serve`). Local-first: it binds `127.0.0.1` and auto-opens the
browser, with an optional token when hosted.

### v3: Desktop (Tauri + Python sidecar)
A native, installable app. Users set their own image provider in Settings
(server URL or API key). Images are saved locally, and the app stores nothing
remotely. A Tauri (Rust) shell wraps the Python core as a sidecar, with the
runtime bootstrapped on first run via `uv` (a thin installer, not a 1GB
bundle), the pattern explored for slide-stream. Not on the Mac App Store
because of the runtime download rules; distributed as a signed `.dmg` or
installer.

### Demo: "try before install"
A hosted instance at `demo.limn.borck.dev` that is rate-limited and
non-storing. Generate a few images to try it, nothing is saved server-side, and
a banner invites visitors to install locally for full control and privacy. Same
`--demo` flag idea as slide-stream.

## 4. Providers (v1 set)

Limn generates images; it does not browse stock photos.

| Provider | What | Config |
|---|---|---|
| `swarmui` | Self-hosted SwarmUI native API | `base_url`, `model`, optional Bearer `api_key` |
| `openai-compatible` | Any `/v1/images` endpoint (LocalAI, …) | `base_url`, `model`, `api_key` |
| `openai` / `dalle` | OpenAI Images (DALL·E) | `OPENAI_API_KEY`, `model` |
| `gemini` / `imagen` | Google Imagen (cheap, ~$0.02/img) | `GEMINI_API_KEY`, `model` |
| `local` *(later)* | Bundled local diffusion (optional heavy extra) | n/a |

Each provider is a thin client that takes a prompt (plus size, count, seed and
negative) and returns image bytes. The design follows `slide-stream`'s image
providers, but Limn is standalone and does not depend on slide-stream (a video
tool). If code-sharing becomes worthwhile, extract a small shared
`image-providers` library later.

## 5. Architecture

```
limn/                      Python package
  providers/               thin per-backend clients (swarmui, openai, gemini, …)
  core.py                  generate(prompt, opts) -> image bytes / files
  config.py                layered config (~/.limn.yaml + ./limn.yaml + env)
  cli.py                   Typer CLI
  serve.py                 FastAPI web UI (optional [serve] extra)
desktop/                   Tauri shell + Python sidecar (later)
```

- Python 3.10+, `typer`, `requests`/`httpx`, `pillow`.
- Web: `fastapi` + `uvicorn` behind a `[serve]` extra.
- Desktop: Tauri (Rust) and a Python sidecar with a `uv`-bootstrapped runtime.
- Packaging: `uv` / hatchling, published to PyPI (`pip install limn`).

## 6. Config

Layered, later wins (mirrors slide-stream): built-in defaults, then
`~/.limn.yaml` (your provider and keys, set once), then `./limn.yaml`, then CLI
flags. Secrets are referenced as `${VAR}` so no plaintext keys live in files.

```yaml
provider: swarmui
base_url: https://image.example.org
model: juggernautXL_v9
api_key: "${SWARMUI_TOKEN}"
size: [1024, 1024]
```

## 7. Privacy & governance

- No account and no telemetry; nothing is required to run it.
- No server-side storage of prompts or images. The desktop is fully local, and
  the demo is ephemeral and rate-limited.
- Your provider, your data. The only network egress is the generation request
  to the provider you configured.
- Clear, short docs on what leaves the machine and when.

## 8. Non-goals

- Not a full editing studio: no inpainting, ControlNet or node graphs, so use
  ComfyUI/SwarmUI for those.
- Not a model host. Limn calls a provider you point it at.
- Not a prompt-engineering IDE; minimal knobs on purpose.

## 9. Milestones

1. M1, CLI: `limn "prompt" -o out.png`, a provider layer (SwarmUI plus one
   cloud), and layered config. Publish to PyPI.
2. M2, web UI: `limn serve` with generate, view, save, delete and regenerate,
   plus a session gallery.
3. M3, demo: a hosted, rate-limited, non-storing instance and landing page.
4. M4, desktop: a Tauri app with bring-your-own-provider settings and local
   saves.

*Companion project to [slide-stream](https://github.com/michael-borck/slide-stream),
which shares the same image-provider approach.*
