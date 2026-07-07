# Hosting the Limn demo

The demo (SPEC §3) is a shared, rate-limited, non-storing instance of
`limn serve` — try a few images in the browser, install locally for real use.

## What `--demo` changes

- **No token** — friction-free, guarded by limits instead.
- **Rate limit** — 10 images/hour per client IP (X-Forwarded-For aware).
- **Locked spend** — provider and model come from the server config only;
  one image per request, max 1024px.
- **Non-storing** — server-side Save is disabled (403); the UI offers
  Download instead. Gallery entries live in RAM and expire after 15 min.
- **Banner** — the page tells visitors it's a demo and how to install.

## Run it — Docker (recommended for a VPS)

The repo's `Dockerfile` installs limn from PyPI; config is a mounted
`limn.yaml`, secrets come from env:

```bash
# limn.yaml — self-hosted SwarmUI (free, your GPU):
#   provider: swarmui
#   providers:
#     swarmui:
#       base_url: https://image.example.org
#       model: juggernautXL_v9
#       api_key: "${SWARMUI_TOKEN}"    # only if fronted by auth
#
# ...or a cloud provider instead:
#   provider: gemini                   # imagen-4.0-fast-*: ~$0.02/image

docker build -t limn https://github.com/michael-borck/limn.git
docker run -d --name limn-demo --restart unless-stopped \
  -p 127.0.0.1:5466:5466 \
  -v ./limn.yaml:/config/limn.yaml:ro \
  -e SWARMUI_TOKEN=... \
  -e LIMN_DEMO=1 \
  limn
```

Or docker-compose:

```yaml
services:
  limn-demo:
    build: https://github.com/michael-borck/limn.git
    restart: unless-stopped
    ports:
      - "127.0.0.1:5466:5466"
    volumes:
      - ./limn.yaml:/config/limn.yaml:ro
    environment:
      LIMN_DEMO: "1"
      SWARMUI_TOKEN: ${SWARMUI_TOKEN}   # or GEMINI_API_KEY / OPENAI_API_KEY
```

Omit `LIMN_DEMO` to run a private (non-demo) instance instead: binding
0.0.0.0 inside the container auto-generates an access token — read it with
`docker logs limn-demo` — or pass your own by appending `--token <token>`
to the run command.

## Run it — bare (pip + systemd)

```bash
pip install "limn[serve]"

# limn.yaml next to the working dir (or ~/.limn.yaml):
#   provider: swarmui
#   providers:
#     swarmui:
#       base_url: https://image.example.org
#       model: juggernautXL_v9

limn serve --demo --host 127.0.0.1 --port 5466
# or: LIMN_DEMO=1 limn serve ...
```

Put a reverse proxy (nginx / Nginx Proxy Manager / Caddy) in front for TLS,
e.g. `app.limn.example.org` → `127.0.0.1:5466`. The rate limiter reads the
first `X-Forwarded-For` entry, which every mainstream proxy sets.

### systemd unit

```ini
[Unit]
Description=Limn demo
After=network.target

[Service]
ExecStart=/opt/limn/.venv/bin/limn serve --demo --no-browser --port 5466
WorkingDirectory=/opt/limn
Environment=GEMINI_API_KEY=...
Restart=on-failure
# The demo writes nothing, so lock it down:
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

## Cost / load ceiling

Worst case per IP: 10 images/hour.

- **SwarmUI (self-hosted):** no dollar cost — the limit protects your GPU
  queue instead. Each demo image is one ≤1024px job on your server.
- **Cloud (Imagen Fast ~$0.02/image):** ~$0.20/hour per abusive IP; watch
  the provider's billing dashboard.

Drop `DEMO_IMAGES_PER_HOUR` in `limn/serve.py` (or add proxy-level rate
limits) if needed.
