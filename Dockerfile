# Limn web UI / demo container.
#
# Provider config comes from a limn.yaml mounted at /config, secrets from env:
#
#   docker build -t limn .
#   docker run -d -p 5466:5466 \
#     -v ./limn.yaml:/config/limn.yaml:ro \
#     -e SWARMUI_TOKEN=... \
#     -e LIMN_DEMO=1 \
#     limn
#
# LIMN_DEMO=1 -> shared demo (no token, rate-limited, non-storing).
# Without it, binding 0.0.0.0 auto-generates an access token (see logs),
# or pass your own:  docker run ... limn --token <token>
FROM python:3.12-slim

ARG LIMN_VERSION=0.4.0
RUN pip install --no-cache-dir "limn[serve]==${LIMN_VERSION}"

RUN useradd --create-home limn
USER limn
WORKDIR /config

EXPOSE 5466
ENTRYPOINT ["limn", "serve", "--host", "0.0.0.0", "--no-browser"]
