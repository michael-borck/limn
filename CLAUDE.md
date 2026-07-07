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

**Specification only — no implementation yet.** The repo contains `SPEC.md`,
`README.md`, `.gitignore`, and this file. Nothing has been built.

## Where to start (Milestone 1 — CLI)

Per `SPEC.md` §9, M1 is the CLI + provider layer:

1. Scaffold the `limn` Python package (`pyproject.toml`, `src/limn/`), Python
   3.10+, Typer CLI. Mirror slide-stream's tooling: `uv`, `ruff`,
   `basedpyright` (zero errors), `pytest`.
2. Port a **thin, standalone** provider layer (do NOT depend on slide-stream):
   start with `swarmui` (self-hosted, native API) and one cloud provider
   (`gemini`/Imagen or `openai`/DALL·E). Each: prompt (+ size/count/seed/
   negative) → image bytes. Reference implementations live in
   `../slide-stream/src/slide_stream/providers/images.py`.
3. Layered config (`~/.limn.yaml` < `./limn.yaml` < CLI flags), `${VAR}`
   secret expansion — same pattern as slide-stream's `config_loader.py`.
4. `limn "a red bicycle" -o out.png` with `--provider/--model/--size/--count/
   --seed/--negative/--out`. Print saved path(s).
5. Publish to PyPI (`pip install limn`). Slide-stream uses **twine** (not
   `uv publish`); assume the same here unless told otherwise.

Then M2 (web UI, like `slide-stream serve`), M3 (demo), M4 (Tauri desktop).

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
