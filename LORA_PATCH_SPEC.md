# Patch spec: LoRA + extra SwarmUI generation params

**Author context:** written from the retroverse/swipeverse card-art project,
which currently injects LoRAs into SwarmUI via the inline `<lora:name:weight>`
prompt-syntax hack (works, but undocumented and SwarmUI-specific). This spec
adds first-class support so any provider can accept LoRAs and common sampler
controls, and so non-supporting providers warn instead of silently garbling.

Target repo: this repo (`limn`, v0.4.1). Layout under `src/limn/`.

## Goal

Add these generation controls, config- and CLI-settable, plumbed through to the
SwarmUI provider (the only backend that supports them today):

- **`loras`** — list of `(name, weight)` pairs. SwarmUI native params
  `loras` + `loraweights`.
- **`cfg_scale`** (float), **`steps`** (int), **`sampler`** (str),
  **`scheduler`** (str) — common SDXL knobs. Low CFG (~4–5) + a fixed sampler
  measurably help stylized/pixel output; worth exposing.

Keep limn's "thin client, fail loudly, provider-agnostic" ethos: the request
object is generic; only SwarmUI maps the new fields; other providers declare
them unsupported and warn.

## Why not keep the inline `<lora:>` hack

It only works on SwarmUI, isn't discoverable, can't be validated (a typo'd
LoRA name silently no-ops or errors deep in Comfy), and mixing it with a real
`loras` param double-applies. First-class fields are testable and portable.

---

## Change 1 — `src/limn/providers/base.py`

Extend `GenerateRequest` with the new optional fields (all default None/empty
so existing callers are unaffected):

```python
@dataclass
class GenerateRequest:
    prompt: str
    size: tuple[int, int] = (1024, 1024)
    count: int = 1
    seed: int | None = None
    negative: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    timeout: float = 180.0
    # New: advanced generation controls (provider-dependent; see unsupported()).
    loras: list[tuple[str, float]] | None = None   # (name, weight) pairs
    cfg_scale: float | None = None
    steps: int | None = None
    sampler: str | None = None
    scheduler: str | None = None
```

The existing `unsupported()` / `warn_unsupported()` hook is already the right
mechanism — providers list the new fields there when they can't honor them.

## Change 2 — `src/limn/core.py` `build_request`

Map settings → request. Parse `loras` from either a list of `"name:weight"`
strings (CLI/YAML friendly) or a list of `{name, weight}` dicts (YAML friendly).
Add a helper:

```python
def _parse_loras(raw: Any) -> list[tuple[str, float]] | None:
    """Accept ['pixel-art-xl:1.0', ...] or [{'name':..., 'weight':...}, ...]."""
    if not raw:
        return None
    out: list[tuple[str, float]] = []
    for item in raw:
        if isinstance(item, str):
            name, _, w = item.partition(":")
            out.append((name.strip(), float(w) if w.strip() else 1.0))
        elif isinstance(item, dict):
            out.append((str(item["name"]), float(item.get("weight", 1.0))))
        else:
            raise ValueError(f"Bad lora entry: {item!r}")
    return out or None
```

Then in `build_request`, add to the `GenerateRequest(...)` call:

```python
        loras=_parse_loras(settings.get("loras")),
        cfg_scale=_opt_float(settings.get("cfg_scale")),
        steps=_opt_int(settings.get("steps")),
        sampler=settings.get("sampler") or None,
        scheduler=settings.get("scheduler") or None,
```

(`_opt_float`/`_opt_int`: return None when the setting is None, else cast.)

## Change 3 — `src/limn/config.py`

Add keys to `DEFAULT_CONFIG`:

```python
    "loras": None,
    "cfg_scale": None,
    "steps": None,
    "sampler": None,
    "scheduler": None,
```

Document them in `EXAMPLE_CONFIG`, e.g. under the swarmui block:

```yaml
  swarmui:
    base_url: https://image.example.org
    model: juggernautXL_v9
    # loras:                          # SwarmUI only; applied to every generation
    #   - pixel-art-xl:1.0            #   name:weight (weight optional, default 1)
    # cfg_scale: 5                    # lower = looser/more stylized (try 4-6)
    # steps: 30
    # sampler: euler                  # provider-specific sampler name
    # scheduler: normal
```

## Change 4 — `src/limn/cli.py` `generate`

Add options. `--lora` is repeatable (one LoRA per flag):

```python
    lora: list[str] = typer.Option(
        None, "--lora",
        help="LoRA as name[:weight], repeatable (SwarmUI only). "
             "e.g. --lora pixel-art-xl:1.0",
        show_default=False,
    ),
    cfg_scale: float = typer.Option(
        None, "--cfg", help="CFG / guidance scale (if supported).",
        show_default=False,
    ),
    steps: int = typer.Option(
        None, "--steps", help="Sampling steps (if supported).",
        show_default=False,
    ),
    sampler: str = typer.Option(
        None, "--sampler", help="Sampler name (provider-specific).",
        show_default=False,
    ),
```

Then merge into `settings` alongside the existing `if X is not None` block:

```python
        if lora:
            settings["loras"] = list(lora)      # _parse_loras handles name:weight
        if cfg_scale is not None:
            settings["cfg_scale"] = cfg_scale
        if steps is not None:
            settings["steps"] = steps
        if sampler is not None:
            settings["sampler"] = sampler
```

CLI `--lora` (a list of `name:weight` strings) flows through `_parse_loras`
unchanged, so CLI and YAML share one parser.

## Change 5 — `src/limn/providers/swarmui.py`

In `generate()`, after the base payload is built, add the new params. SwarmUI's
`GenerateText2Image` wants **comma-separated** LoRA names and weights:

```python
            if request.loras:
                payload["loras"] = ",".join(n for n, _ in request.loras)
                payload["loraweights"] = ",".join(f"{w:g}" for _, w in request.loras)
            if request.cfg_scale is not None:
                payload["cfgscale"] = request.cfg_scale
            if request.steps is not None:
                payload["steps"] = request.steps
            if request.sampler:
                payload["sampler"] = request.sampler
            if request.scheduler:
                payload["scheduler"] = request.scheduler
```

**Validation (recommended):** SwarmUI silently ignores an unknown LoRA name,
which is a nasty footgun (you think the style applied; it didn't). Before
generating, resolve names against `/API/ListModels` (subtype `LoRA`) — which
this provider already knows how to call for `list_models` — and raise
`ProviderError(f"LoRA not found on server: {name}")` on a miss. The server
registers a LoRA under its filename minus extension (e.g. `pixel-art-xl` for
`pixel-art-xl.safetensors`); match case-insensitively and tolerate an optional
subfolder prefix.

## Change 6 — other providers declare unsupported

In `gemini.py` and `openai_compat.py` (and openai), extend `unsupported()` so
users get the standard yellow "ignoring" note instead of silent drop:

```python
    def unsupported(self, request):
        items = super().unsupported(request)
        if request.loras:
            items.append(("LoRAs", request.loras))
        if request.cfg_scale is not None:
            items.append(("cfg_scale", request.cfg_scale))
        if request.steps is not None:
            items.append(("steps", request.steps))
        if request.sampler:
            items.append(("sampler", request.sampler))
        return items
```

Ensure `warn_unsupported(request)` is actually called on the generate path if
it isn't already (grep for it — base defines it but confirm a caller invokes
it, e.g. in `core.generate` before dispatch, or at the top of each provider's
`generate`).

## Tests (`tests/`)

- `_parse_loras`: `"pixel-art-xl"` → `[("pixel-art-xl", 1.0)]`;
  `"pixel-art-xl:0.8"` → `[("pixel-art-xl", 0.8)]`; dict form; empty → None;
  bad entry raises.
- `build_request`: settings with `loras`/`cfg_scale`/`steps` populate the
  request; absent → None.
- SwarmUI payload: `request.loras` → `payload["loras"]` /
  `payload["loraweights"]` comma-joined and aligned; cfg/steps/sampler mapped.
  (Mock `requests` as existing SwarmUI tests do.)
- Unsupported warning: a non-SwarmUI provider with `loras` set emits the note.

## Manual verification against the live server

```
limn "pixel art, a fox" -p swarmui -m juggernautXL_v9 \
     --lora pixel-art-xl:1.0 --cfg 5 -o /tmp/fox.png
```

Compare with and without `--lora` at a fixed `--seed`: the LoRA build should be
visibly chunky pixel art. (This exact effect is already confirmed on
`swarmui.locopuente.org` via the inline-tag path; this patch makes it a real
param.)

## Notes / decisions left to the implementer

- **Multiple LoRAs**: the comma-join already supports stacking; no extra work.
- **Backward compat**: all new fields optional; the inline `<lora:>` prompt hack
  keeps working, so downstream scripts (retroverse `art.py`) need no change —
  they can migrate to `--lora` at leisure.
- **Serve UI** (`serve.py` / `serve_page.html`): out of scope here; add a LoRA
  field later if wanted. The CLI + config path is the priority.
