# 🖼️ Limn

> *to **limn**: to depict or describe; to paint.*

A small, privacy-first tool that turns a text description into an image. Type a
prompt, get a picture — no account, minimal options, bring your own provider.

- **Type a description → get an image.** That's the whole thing.
- **No account, private by default.** Your prompts and images are yours.
- **Bring your own provider** — self-hosted (SwarmUI / any OpenAI-compatible
  endpoint) or a cloud key (Google Imagen, OpenAI / DALL·E). Swap with one
  setting.
- **Minimal by design.** Prompt, size, count, seed. Want power? Install
  something bigger — Limn stays lean.

Planned surfaces: a **CLI** first, then a simple **web UI** (type → generate →
view → save / delete / regenerate), then a **Tauri desktop app** with
bring-your-own-provider, plus a rate-limited, non-storing **demo** to try before
installing.

📄 See **[SPEC.md](SPEC.md)** for the full specification.

> Status: **specification** — implementation not started yet.

Companion to [slide-stream](https://github.com/michael-borck/slide-stream),
which shares the same image-provider approach.
