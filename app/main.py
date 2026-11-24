from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .routers import api, pages


def create_app() -> FastAPI:
    init_db()
    app = FastAPI(title="CrediVerbi", version="0.1.0")
    app.include_router(api.router, prefix="/api")
    app.include_router(pages.router)
    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return app


app = create_app()
