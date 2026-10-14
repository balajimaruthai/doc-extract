"""
DocExtract Backend — FastAPI application entry point.
Binds to localhost by default. Use DOCEXTRACT_DEMO=1 to open for ngrok sharing.
"""
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Add backend root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import settings
from core.logging_config import setup_logging
from database.connection import init_db
from api import documents, profiles, processing, export, system, chat

# Demo mode: set DOCEXTRACT_DEMO=1 to allow external connections (for ngrok sharing)
DEMO_MODE = os.getenv("DOCEXTRACT_DEMO", "0") == "1"

# Frontend dist directory (built React app)
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("DocExtract backend starting up")
    logger.info(f"Data directory: {settings.DATA_DIR}")
    logger.info(f"Models directory: {settings.MODELS_DIR}")
    logger.info(f"Uploads directory: {settings.UPLOADS_DIR}")
    if DEMO_MODE:
        logger.info("DEMO MODE enabled — accepting connections from all origins")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Perform startup checks (offline capability)
    from core.startup_checks import run_startup_checks
    startup_status = await run_startup_checks()
    app.state.startup_status = startup_status
    logger.info(f"Startup checks complete: {startup_status}")

    yield

    logger.info("DocExtract backend shutting down")


app = FastAPI(
    title="DocExtract API",
    description="Offline Document Intelligence — Local Processing Only",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",   # Always show docs (useful for demo)
    redoc_url=None,
)

# CORS — allow all origins so team on LAN and clients via tunnel can access seamlessly
cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(system.router, prefix="/api/v1/system", tags=["system"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(profiles.router, prefix="/api/v1/profiles", tags=["profiles"])
app.include_router(processing.router, prefix="/api/v1/processing", tags=["processing"])
app.include_router(export.router, prefix="/api/v1/export", tags=["export"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])


@app.get("/health")
async def health_check():
    """Health check — used by Tauri shell to verify backend is ready."""
    return {"status": "ok", "offline": True, "version": "1.0.0"}


# Serve the React frontend if it has been built
if FRONTEND_DIST.exists():
    # Mount static assets (JS/CSS chunks)
    _assets = FRONTEND_DIST / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str = ""):
        """Serve React SPA — all non-API routes return index.html."""
        # Don't intercept API or health routes
        if full_path.startswith("api/") or full_path in ("health", "docs"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse({"detail": "Frontend not built. Run: cd app/frontend && npm run build"}, status_code=404)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger = logging.getLogger(__name__)
    logger.error(f"Unhandled exception: {type(exc).__name__}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


if __name__ == "__main__":
    host = os.getenv("DOCEXTRACT_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", str(settings.BACKEND_PORT)))
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
        access_log=True,
    )
