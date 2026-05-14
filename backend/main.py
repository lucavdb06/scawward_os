"""FastAPI entry point. Run with: `uvicorn backend.main:app --reload`."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.routes import router
from .api.websocket import ws_router
from .config import get_settings
from .db.session import init_db


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    _configure_logging(cfg.log_level)
    logging.getLogger("scawward").info("Scawward starting v%s", __version__)
    await init_db()
    # Warm up the DI graph so the first /command isn't slow.
    from .api.deps import get_stack
    get_stack()
    yield
    logging.getLogger("scawward").info("Scawward shutting down")


def create_app() -> FastAPI:
    cfg = get_settings()
    app = FastAPI(
        title="Scawward",
        description="AI-piloted operating layer",
        version=__version__,
        lifespan=lifespan,
        debug=cfg.debug,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")
    app.include_router(ws_router)

    @app.get("/")
    async def root() -> dict:
        return {"name": "Scawward", "version": __version__,
                "docs": "/docs", "ws": ["/ws/chat", "/ws/events"]}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    cfg = get_settings()
    uvicorn.run("backend.main:app", host=cfg.host, port=cfg.port, reload=cfg.debug)
