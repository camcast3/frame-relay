"""FastAPI application: JSON API + server-rendered UI + artifact serving."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, db, service
from .routers import analysis, ingest, sessions

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    db.init_db()
    yield


app = FastAPI(title="Apollo Streaming Lab", version="0.1.0", lifespan=lifespan)

app.include_router(sessions.router)
app.include_router(ingest.router)
app.include_router(analysis.router)

app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
app.mount("/artifacts", StaticFiles(directory=str(config.ARTIFACTS_DIR), check_dir=False), name="artifacts")


@app.get("/health")
def health():
    return {"status": "ok", "copilot_backend": config.COPILOT_BACKEND}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"sessions": service.list_sessions()})


@app.get("/sessions/new", response_class=HTMLResponse)
def new_session_form(request: Request):
    return templates.TemplateResponse(request, "new.html", {})


@app.get("/sessions/{session_id}", response_class=HTMLResponse)
def session_detail(request: Request, session_id: str):
    bundle = service.get_bundle(session_id)
    if bundle is None:
        raise HTTPException(404, "session not found")
    return templates.TemplateResponse(
        request, "session.html",
        {"b": bundle, "related": service.get_related_sessions(session_id)},
    )
