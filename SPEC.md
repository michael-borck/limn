# Limn — specification

> *to **limn** (verb): to depict or describe; to paint.*

A small, privacy-first tool that turns a text description into an image. Type a
prompt, get a picture. No account, minimal options, bring your own provider.

---

## 1. Vision

Most image tools are either a single locked-in web app (an account, your data on
their servers) or a full studio (ComfyUI/SwarmUI — powerful but heavy). **Limn
sits deliberately in between:** the simplest possible "text → image" surface,
that you own.

- **Type a description → get an image.** That's the whole interaction.
- **No account, no lock-in, privacy by default.** Your prompts and images are
  yours. On the desktop, nothing leaves your machine except the generation
  request to *your* chosen provider.
- **Bring your own provider.** Point Limn at a self-hosted server (SwarmUI /
  any OpenAI-compatible endpoint) or a cloud key (Google Imagen, OpenAI /
  DALL·E). Swap it with one setting.
- **Minimal by design.** A handful of knobs (prompt, size, count, seed). If you
  want inpainting, ControlNet, and node graphs, install something bigger —
  Limn stays lean.

Think "Black Forest Labs playground, but standalone, private, and yours."

## 2. Principles

1. **Simple beats powerful.** One prompt in, one image out. Advanced parameters
   live in the provider, not in Limn.
2. **Local-first & private.** No account, no telemetry, no server-side storage
   of prompts or images (desktop is fully local). The hosted demo is
   rate-limited and stores nothing.
3. **Provider-agnostic.** The same thin provider abstraction as `slide-stream`'s
   image layer — self-hosted or cloud, chosen by config.
4. **Progressive surfaces.** The same core powers a CLI, a web UI, and a desktop
   app; each is optional.

## 3. Surfaces (roadmap)

### v1 — CLI
```
limn "a red bicycle against a brick wall" -o bike.png
limn "watercolour fox" --provider swarmui --size 1024x1024 --count 4 --seed 42
```
Options: `--provider`, `--model`, `--size`, `--count`, `--seed`, `--negative`,
`--out`. Provider selection + API keys from a config file and/or environment
variables. Prints the saved path(s).

### v2 — Web UI (`limn serve`)
A single page: type a prompt → **Generate** → the image appears in-app →
**Save** (to disk), **Delete** (from the session gallery), or **Generate
another**. A running gallery of the session's images (prompt, thumbnail, seed).
FastAPI + a self-contained HTML page (same shape as `slide-stream serve`).
Local-first (binds `127.0.0.1`, auto-opens the browser); optional token when
hosted.

### v3 — Desktop (Tauri + Python sidecar)
A native, installable app. Users set **their own image provider** in Settings
(server URL or API key). Images are saved locally; the app stores nothing
remotely. Tauri (Rust) shell wrapping the Python core as a sidecar, with the
runtime bootstrapped on first run via `uv` (thin installer, not a 1GB bundle) —
the pattern explored for slide-stream. Not on the Mac App Store (runtime
download rules); distributed as a signed `.dmg` / installer.

### Demo — "try before install"
A hosted instance (`app.limn.<domain>`) that is **rate-limited and
non-storing**: generate a few images to try it, nothing saved server-side, with
a banner inviting users to install locally for full control and privacy. Same
`--demo` flag idea as slide-stream.

## 4. Providers (v1 set)

Generative backends only (Limn *makes* images; it is not a stock-photo
browser):

| Provider | What | Config |
|---|---|---|
| `swarmui` | Self-hosted SwarmUI native API | `base_url`, `model`, optional Bearer `api_key` |
| `openai-compatible` | Any `/v1/images` endpoint (LocalAI, …) | `base_url`, `model`, `api_key` |
| `openai` / `dalle` | OpenAI Images (DALL·E) | `OPENAI_API_KEY`, `model` |
| `gemini` / `imagen` | Google Imagen (cheap, ~$0.02/img) | `GEMINI_API_KEY`, `model` |
| `local` *(later)* | Bundled local diffusion (optional heavy extra) | — |

Each provider is a thin client: prompt (+ size/count/seed/negative) → image
bytes. Modeled on `slide-stream`'s image providers, but **standalone** — Limn
does not depend on slide-stream (a video tool). If code-sharing becomes
worthwhile, extract a small shared `image-providers` library later.

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

- **Python 3.10+**, `typer`, `requests`/`httpx`, `pillow`.
- **Web:** `fastapi` + `uvicorn` behind a `[serve]` extra.
- **Desktop:** Tauri (Rust) + Python sidecar, `uv`-bootstrapped runtime.
- **Packaging:** `uv` / hatchling; publish to PyPI (`pip install limn`).

## 6. Config

Layered, later wins (mirrors slide-stream): built-in defaults →
`~/.limn.yaml` (your provider + keys, set once) → `./limn.yaml` → CLI flags.
Secrets referenced as `${VAR}` so no plaintext keys in files.

```yaml
provider: swarmui
base_url: https://image.example.org
model: juggernautXL_v9
api_key: "${SWARMUI_TOKEN}"
size: [1024, 1024]
```

## 7. Privacy & governance

- **No account. No telemetry.** Nothing is required to run it.
- **No server-side storage** of prompts or images. Desktop = fully local;
  the demo is ephemeral and rate-limited.
- **Your provider, your data.** The only network egress is the generation
  request to the provider *you* configured.
- Clear, short docs on what leaves the machine and when.

## 8. Non-goals

- Not a full editing studio (no inpainting / ControlNet / node graphs — use
  ComfyUI/SwarmUI).
- Not a model host — Limn calls a provider you point it at.
- Not a prompt-engineering IDE — minimal knobs on purpose.

## 9. Milestones

1. **M1 — CLI:** `limn "prompt" -o out.png`, provider layer (swarmui + one
   cloud), layered config. Publish to PyPI.
2. **M2 — Web UI:** `limn serve` with generate / view / save / delete /
   regenerate + session gallery.
3. **M3 — Demo:** hosted, rate-limited, non-storing instance + landing page.
4. **M4 — Desktop:** Tauri app with BYO-provider settings, local saves.

---

*Companion project to [slide-stream](https://github.com/michael-borck/slide-stream),
which shares the same image-provider approach.*
