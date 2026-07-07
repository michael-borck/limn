"""Limn web UI: a single page, generate / view / save / delete / regenerate.

Privacy model (SPEC §2/§7): the session gallery lives in this process's
memory only — nothing is written to disk unless the user clicks Save, and
nothing is logged. Binds localhost by default; an optional token gates
hosted instances.

Requires the [serve] extra: pip install 'limn[serve]'
"""

# pyright: reportUnusedFunction=false

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from limn import __version__
from limn.config import ConfigurationError, resolve_settings
from limn.core import (
    generate,
    image_extension,
    parse_size,
    slugify,
    unique_path,
)
from limn.providers import PROVIDERS, ProviderError

MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

# In-memory gallery cap; oldest entries drop off. Keeps a long session from
# eating RAM while staying comfortably above what one sitting produces.
MAX_SESSION_IMAGES = 100

# Demo-mode guardrails (SPEC §3): friction-free (no token) but bounded, and
# truly non-storing — Save is disabled and images evaporate after a while.
DEMO_IMAGES_PER_HOUR = 10  # per client IP
DEMO_MAX_DIMENSION = 1024
DEMO_TTL_SECONDS = 15 * 60


@dataclass
class SessionImage:
    """One generated image, held in memory until saved or deleted."""

    id: str
    prompt: str
    seed: int | None
    provider: str
    data: bytes
    created: float


class GeneratePayload(BaseModel):
    prompt: str = Field(min_length=1)
    provider: str | None = None
    model: str | None = None
    size: str | None = None  # "1024x1024"
    count: int = Field(default=1, ge=1, le=10)
    seed: int | None = None
    negative: str | None = None


class SavePayload(BaseModel):
    filename: str | None = None


def _meta(item: SessionImage) -> dict[str, Any]:
    return {
        "id": item.id,
        "prompt": item.prompt,
        "seed": item.seed,
        "provider": item.provider,
        "created": item.created,
    }


def create_app(
    config: dict[str, Any],
    token: str | None = None,
    out_dir: Path | None = None,
    demo: bool = False,
    demo_images_per_hour: int = DEMO_IMAGES_PER_HOUR,
    demo_ttl_seconds: float = DEMO_TTL_SECONDS,
) -> FastAPI:
    """Build the Limn web app around a loaded config.

    Demo mode is friction-free (no token) but bounded: provider/model locked
    to the server's config, one image per request capped at 1024px, a per-IP
    hourly budget, Save disabled, and gallery entries expire.
    """
    auth_token = "" if demo else (token or "")
    save_dir = (out_dir or Path.cwd()).resolve()
    index_html = (
        resources.files("limn").joinpath("serve_page.html").read_text("utf-8")
    )

    store: dict[str, SessionImage] = {}
    generation_log: dict[str, list[float]] = {}  # demo: client ip -> times
    lock = threading.Lock()

    def client_ip(request: Request) -> str:
        # Behind a reverse proxy the real IP is in X-Forwarded-For.
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def check_demo_budget(request: Request) -> None:
        ip = client_ip(request)
        now = time.time()
        with lock:
            recent = [t for t in generation_log.get(ip, []) if now - t < 3600]
            if len(recent) >= demo_images_per_hour:
                minutes = int((3600 - (now - recent[0])) // 60) + 1
                raise HTTPException(
                    status_code=429,
                    detail=f"Demo limit reached ({demo_images_per_hour} "
                    f"images/hour). Try again in ~{minutes} min — or run "
                    "Limn yourself, free and private: pip install limn",
                )
            recent.append(now)
            generation_log[ip] = recent

    def evict_expired() -> None:
        if not demo:
            return
        cutoff = time.time() - demo_ttl_seconds
        with lock:
            for key in [k for k, v in store.items() if v.created < cutoff]:
                del store[key]

    # No docs/openapi endpoints: this is an app page, not a public API.
    app = FastAPI(title="Limn", docs_url=None, redoc_url=None, openapi_url=None)

    def _supplied_token(request: Request) -> str | None:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return request.cookies.get("limn_token") or request.query_params.get(
            "token"
        )

    def require_token(request: Request) -> None:
        if auth_token and _supplied_token(request) != auth_token:
            raise HTTPException(status_code=401, detail="Invalid or missing token")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> Response:
        if auth_token and _supplied_token(request) != auth_token:
            return HTMLResponse(
                "<h1>401</h1><p>This Limn instance needs a token: "
                "open /?token=&lt;token&gt;</p>",
                status_code=401,
            )
        response = HTMLResponse(index_html)
        # Move a URL token into a cookie so later /api calls carry it.
        if auth_token and request.query_params.get("token") == auth_token:
            response.set_cookie(
                "limn_token", auth_token, httponly=True, samesite="strict"
            )
        return response

    @app.get("/api/config", dependencies=[Depends(require_token)])
    def api_config() -> dict[str, Any]:
        info: dict[str, Any] = {
            "version": __version__,
            "provider": config.get("provider"),
            "providers": sorted(set(PROVIDERS)),
            "size": config.get("size") or [1024, 1024],
            "demo": demo,
        }
        if demo:
            info["limits"] = {
                "images_per_hour": demo_images_per_hour,
                "ttl_minutes": int(demo_ttl_seconds // 60),
            }
        return info

    @app.get("/api/images", dependencies=[Depends(require_token)])
    def api_list() -> dict[str, Any]:
        evict_expired()
        with lock:
            return {"images": [_meta(item) for item in store.values()]}

    @app.post("/api/generate", dependencies=[Depends(require_token)])
    def api_generate(payload: GeneratePayload, request: Request) -> dict[str, Any]:
        evict_expired()
        # Demo locks provider and model to the server's config so visitors
        # can't route spend to other backends the host has keys for.
        provider_name = (
            config.get("provider")
            if demo
            else payload.provider or config.get("provider")
        )
        if not provider_name:
            raise HTTPException(
                status_code=400,
                detail="No provider configured. Set 'provider:' in "
                "~/.limn.yaml or pick one in Options.",
            )

        settings = resolve_settings(config, str(provider_name))
        if payload.model and not demo:
            settings["model"] = payload.model
        if payload.size:
            try:
                settings["size"] = list(parse_size(payload.size))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
        settings["count"] = payload.count
        if payload.seed is not None:
            settings["seed"] = payload.seed
        if payload.negative:
            settings["negative"] = payload.negative

        if demo:
            settings["count"] = 1
            width, height = settings.get("size") or [1024, 1024]
            settings["size"] = [
                min(int(width), DEMO_MAX_DIMENSION),
                min(int(height), DEMO_MAX_DIMENSION),
            ]
            check_demo_budget(request)

        try:
            images = generate(payload.prompt, settings)
        except (ProviderError, ConfigurationError, ValueError) as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

        items: list[dict[str, Any]] = []
        with lock:
            for image in images:
                item = SessionImage(
                    id=secrets.token_urlsafe(8),
                    prompt=payload.prompt,
                    seed=image.seed,
                    provider=str(provider_name),
                    data=image.data,
                    created=time.time(),
                )
                store[item.id] = item
                items.append(_meta(item))
            while len(store) > MAX_SESSION_IMAGES:
                del store[next(iter(store))]
        return {"images": items}

    @app.get("/api/images/{image_id}", dependencies=[Depends(require_token)])
    def api_image(image_id: str, download: bool = False) -> Response:
        evict_expired()
        with lock:
            item = store.get(image_id)
        if item is None:
            raise HTTPException(status_code=404, detail="No such image")
        ext = image_extension(item.data)
        headers = {}
        if download:
            headers["Content-Disposition"] = (
                f'attachment; filename="{slugify(item.prompt)}{ext}"'
            )
        return Response(
            content=item.data,
            media_type=MEDIA_TYPES.get(ext, "image/png"),
            headers=headers,
        )

    @app.delete("/api/images/{image_id}", dependencies=[Depends(require_token)])
    def api_delete(image_id: str) -> dict[str, Any]:
        with lock:
            if image_id not in store:
                raise HTTPException(status_code=404, detail="No such image")
            del store[image_id]
        return {"deleted": image_id}

    @app.post(
        "/api/images/{image_id}/save", dependencies=[Depends(require_token)]
    )
    def api_save(image_id: str, payload: SavePayload | None = None) -> dict[str, Any]:
        if demo:
            raise HTTPException(
                status_code=403,
                detail="The demo stores nothing server-side — use Download, "
                "or run Limn locally: pip install limn",
            )
        with lock:
            item = store.get(image_id)
        if item is None:
            raise HTTPException(status_code=404, detail="No such image")

        ext = image_extension(item.data)
        requested = (payload.filename or "").strip() if payload else ""
        if requested:
            # Basename only — the browser must not choose directories.
            name = Path(requested).name
            if not name or name.startswith("."):
                raise HTTPException(status_code=400, detail="Bad filename")
            if not Path(name).suffix:
                name += ext
        else:
            name = slugify(item.prompt) + ext

        save_dir.mkdir(parents=True, exist_ok=True)
        target = unique_path(save_dir / name)
        target.write_bytes(item.data)
        return {"path": str(target)}

    return app
