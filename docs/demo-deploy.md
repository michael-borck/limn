# Hosting the Limn demo

The demo (SPEC §3) is a shared, rate-limited, non-storing instance of
`limn serve`. Try a few images in the browser, then install locally for real
use.

## What `--demo` changes

- No token. The demo is friction-free, guarded by limits instead.
- Rate limit of 10 images per hour per client IP (X-Forwarded-For aware).
- Locked spend: provider and model come from the server config only, with one
  image per request and a max of 1024px.
- Non-storing: server-side Save is disabled (403) and the UI offers Download
  instead. Gallery entries live in RAM and expire after 15 minutes.
- A banner tells visitors it's a demo and how to install.

## Run it with Docker Compose (recommended for a VPS)

Everything lives in [`deploy/`](../deploy): a compose file that builds the
image from this repo, plus templates for config and secrets. On the VPS:

```bash
mkdir limn && cd limn
base=https://raw.githubusercontent.com/michael-borck/limn/main/deploy
curl -O $base/docker-compose.yml
curl -o limn.yaml $base/limn.yaml.example
curl -o .env $base/.env.example

$EDITOR limn.yaml   # provider + base_url (SwarmUI: free, your GPU)
$EDITOR .env        # SWARMUI_TOKEN / cloud keys; LIMN_DEMO=1 is preset

docker compose up -d
```

Remove `LIMN_DEMO` from `.env` to run a private (non-demo) instance instead.
Binding 0.0.0.0 inside the container auto-generates an access token; read it
with `docker compose logs limn`.

Plain `docker run` works too:

```bash
docker build -t limn https://github.com/michael-borck/limn.git
docker run -d --name limn-demo --restart unless-stopped \
  -p 127.0.0.1:5466:5466 \
  -v ./limn.yaml:/config/limn.yaml:ro \
  -e SWARMUI_TOKEN=... \
  -e LIMN_DEMO=1 \
  limn
```

## Run it bare (pip and systemd)

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

Put a reverse proxy (nginx, Nginx Proxy Manager or Caddy) in front for TLS,
for example `demo.limn.borck.dev` pointing at `127.0.0.1:5466`. The rate
limiter reads the first `X-Forwarded-For` entry, which every mainstream proxy
sets.

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

Worst case per IP is 10 images per hour.

- SwarmUI (self-hosted): no dollar cost. The limit protects your GPU queue
  instead, and each demo image is one ≤1024px job on your server.
- Cloud (Imagen Fast at ~$0.02 per image): about $0.20 per hour per abusive IP.
  Watch the provider's billing dashboard.

Drop `DEMO_IMAGES_PER_HOUR` in `limn/serve.py` (or add proxy-level rate
limits) if needed.
