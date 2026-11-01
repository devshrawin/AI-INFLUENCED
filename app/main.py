"""FastAPI application factory."""

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import pages
from app.config import BASE_DIR, get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title=settings.app_name, docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
    app.include_router(pages.router)
    return app


app = create_app()
