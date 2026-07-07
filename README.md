# 🖼️ Limn

> *to **limn**: to depict or describe; to paint.*

A small, privacy-first tool that turns a text description into an image. Type a
prompt, get a picture — no account, minimal options, bring your own provider.

```bash
pip install limn

limn "a red bicycle against a brick wall" -o bike.png
```

- **Type a description → get an image.** That's the whole thing.
- **No account, private by default.** Your prompts and images are yours. The
  only network egress is the generation request to the provider *you* chose.
- **Bring your own provider** — self-hosted (SwarmUI / any OpenAI-compatible
  endpoint) or a cloud key (Google Imagen, OpenAI / DALL·E). Swap with one
  setting.
- **Minimal by design.** Prompt, size, count, seed. Want power? Install
  something bigger — Limn stays lean.

## Quick start

Pick whichever provider you already have:

```bash
# Google Imagen (cheap, ~$0.02/image on the Fast tier)
export GEMINI_API_KEY=...
limn "watercolour fox" --provider gemini

# OpenAI Images
export OPENAI_API_KEY=...
limn "watercolour fox" --provider openai

# Self-hosted SwarmUI
export SWARMUI_BASE_URL=https://image.example.org
limn "watercolour fox" --provider swarmui

# Any OpenAI-compatible /v1/images endpoint (LocalAI, ...)
export OPENAI_BASE_URL=http://localhost:8080/v1
limn "watercolour fox" --provider openai-compatible
```

Then set your provider once so you never pass `--provider` again:

```bash
limn --init-config        # writes a commented ./limn.yaml template
mv limn.yaml ~/.limn.yaml # personal defaults, used everywhere
```

## Usage

```
limn "a red bicycle against a brick wall" -o bike.png
limn "watercolour fox" --provider swarmui --size 1024x1024 --count 4 --seed 42
```

| Option | What |
|---|---|
| `-p, --provider` | `swarmui`, `openai-compatible`, `openai`, `gemini` |
| `-m, --model` | Model name (provider-specific) |
| `-s, --size` | e.g. `1024x1024` (Imagen maps to the nearest aspect ratio) |
| `-n, --count` | Number of images (1–10) |
| `--seed` | Reproducibility, where the backend supports it (SwarmUI) |
| `--negative` | Negative prompt, where supported (SwarmUI) |
| `-o, --out` | Output file; default is a slug of the prompt, never overwritten |
| `-c, --config` | Explicit config file |

## Config

Layered, later wins: built-in defaults → `~/.limn.yaml` (your provider + keys,
set once) → `./limn.yaml` → CLI flags. Secrets are referenced as `${VAR}` so no
plaintext keys live in files:

```yaml
provider: swarmui
size: [1024, 1024]

providers:            # keep several configured; swap with `provider:`
  swarmui:
    base_url: https://image.example.org
    model: juggernautXL_v9
    api_key: "${SWARMUI_TOKEN}"
  gemini:
    model: imagen-4.0-fast-generate-001
```

## Web UI

```bash
pip install "limn[serve]"
limn serve                # opens http://127.0.0.1:5466/ in your browser
```

One page: type a prompt → **Generate** → the image appears → **Save** (to
disk), **Again** (regenerate), or **Delete**. The session gallery lives in the
server process's memory only — nothing touches disk until you click Save.

Binds `127.0.0.1` by default. Binding any other host requires a token
(`--token`, or one is generated and printed); useful flags: `--port`,
`--out-dir`, `--no-browser`.

### Hosting a shared demo

`limn serve --demo` (or `LIMN_DEMO=1`) runs a friction-free public instance
with guardrails instead of a token: 10 images/hour per IP, provider/model
locked to the server config, one ≤1024px image per request, server-side Save
disabled (visitors download instead), gallery entries expire after 15 min,
and the page shows an "install locally" banner. See
[docs/demo-deploy.md](docs/demo-deploy.md).

## Roadmap

A **CLI**, a local **web UI**, and a hostable **demo mode** (this release),
then a **Tauri desktop app** with bring-your-own-provider.

📄 See **[SPEC.md](SPEC.md)** for the full specification.

Companion to [slide-stream](https://github.com/michael-borck/slide-stream),
which shares the same image-provider approach.
