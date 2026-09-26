"""Static pages and assets: service root, health check, Mini App bundle, legal pages."""
import hashlib
import os
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from services import version

router = APIRouter()


@router.get("/")
async def root():
    return {
        "message": "Bot attivo!",
        "version": version.get_version(),
        "revision": version.get_build_revision(),
    }

@router.head("/ping")
async def ping():
    return {"status": "ok"}


# The repository root: apps/api/static.py -> apps/api -> apps -> root.
WEBAPP_DIR = os.path.join(Path(__file__).resolve().parents[2], "webapp")
_static_files: dict[str, str] = {}


def _static(name):
    """Un file di `webapp/`, letto una volta sola e poi tenuto in memoria.

    Le pagine servite da qui sono tre - la mini app e i due documenti legali - e stanno tutte
    sullo stesso servizio del bot: non serve un altro hosting, ne' un dominio in piu'. Sono
    file che cambiano solo con un deploy, quindi rileggerli ad ogni richiesta sarebbe un
    accesso al disco per niente."""
    if name not in _static_files:
        with open(os.path.join(WEBAPP_DIR, name), encoding="utf-8") as f:
            _static_files[name] = f.read()
    return _static_files[name]


def _static_response(name, request, media_type="text/html"):
    content = _static(name)
    etag = '"' + hashlib.sha256(content.encode()).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=0, must-revalidate"}
    candidates = request.headers.get("if-none-match", "").split(",")
    if any(value.strip().removeprefix("W/") in (etag, "*") for value in candidates):
        return Response(status_code=304, headers=headers)
    return Response(content, media_type=media_type, headers=headers)


@router.get("/terms", response_class=HTMLResponse)
def terms_page(request: Request):
    return _static_response("terms.html", request)


@router.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request):
    return _static_response("privacy.html", request)


@router.get("/legal.css")
def legal_css(request: Request):
    return _static_response("legal.css", request, "text/css")


DIST_DIR = os.path.join(WEBAPP_DIR, "dist")


@router.get("/app", response_class=HTMLResponse)
def webapp_page(request: Request):
    dist_index = os.path.join(DIST_DIR, "index.html")
    if not os.path.exists(dist_index):
        return HTMLResponse(
            "<h2>Mini App non compilata</h2><p>Esegui <code>npm run build</code> per compilare il bundle Vite.</p>",
            status_code=503,
        )
    with open(dist_index, encoding="utf-8") as f:
        content = f.read()
    etag = '"' + hashlib.sha256(content.encode()).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=0, must-revalidate"}
    candidates = request.headers.get("if-none-match", "").split(",")
    if any(value.strip().removeprefix("W/") in (etag, "*") for value in candidates):
        return Response(status_code=304, headers=headers)
    return Response(content, media_type="text/html", headers=headers)


@router.get("/app/assets/{file_path:path}")
def webapp_assets(file_path: str, request: Request):
    base_assets = Path(DIST_DIR).resolve() / "assets"
    try:
        target = (base_assets / file_path).resolve()
    except (ValueError, RuntimeError):
        raise HTTPException(status_code=403, detail="Forbidden")

    if not target.is_relative_to(base_assets) or target == base_assets:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Not Found")

    with open(target, "rb") as f:
        content = f.read()
    suffix = target.suffix.lower()
    media_type = "application/javascript" if suffix == ".js" else (
        "text/css" if suffix == ".css" else (
            "application/json" if suffix == ".map" else "application/octet-stream"
        )
    )
    etag = '"' + hashlib.sha256(content).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=31536000, immutable"}
    candidates = request.headers.get("if-none-match", "").split(",")
    if any(value.strip().removeprefix("W/") in (etag, "*") for value in candidates):
        return Response(status_code=304, headers=headers)
    return Response(content, media_type=media_type, headers=headers)


VERIFICATION_DIR = Path(WEBAPP_DIR) / "site-verification"
TIKTOK_FILENAME = re.compile(r"tiktok[A-Za-z0-9]{1,128}\.txt")


@router.get("/{filename}")
def tiktok_site_verification(filename: str):
    if not TIKTOK_FILENAME.fullmatch(filename):
        raise HTTPException(status_code=404, detail="Not Found")

    base = VERIFICATION_DIR.resolve()
    target = (base / filename).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        raise HTTPException(status_code=404, detail="Not Found")

    return Response(target.read_bytes(), media_type="text/plain; charset=utf-8")
