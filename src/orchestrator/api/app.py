"""FastAPI application for the AI orchestrator."""

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from orchestrator.api.routes import router as api_router
from orchestrator.api.streaming_routes import router as streaming_router
from orchestrator.config import settings
from orchestrator.streaming import default_connection_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan events."""
    # Startup
    logger.info("Starting AI Orchestrator API...")
    await default_connection_manager.start()
    logger.info("WebSocket connection manager started")
    yield
    # Shutdown
    logger.info("Shutting down AI Orchestrator API...")
    await default_connection_manager.stop()
    logger.info("WebSocket connection manager stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Local AI Orchestrator",
        description="Dynamic AI model routing with benchmark-driven selection",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API key authentication middleware (optional)
    if settings.api_key:
        from orchestrator.security import ApiKeyMiddleware
        app.add_middleware(ApiKeyMiddleware, api_key=settings.api_key)
        logger.info("API key authentication enabled")

    # Request timing middleware
    @app.middleware("http")
    async def add_timing_header(request: Request, call_next):
        start_time = time.perf_counter()
        response = await call_next(request)
        process_time = (time.perf_counter() - start_time) * 1000
        response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"
        return response

    # Include API routes
    app.include_router(api_router, prefix="/v1")
    app.include_router(streaming_router, prefix="/v1", tags=["streaming"])

    # Health check
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": "0.1.0"}

    # Root redirect
    @app.get("/")
    async def root():
        return {
            "name": "Local AI Orchestrator",
            "version": "0.1.0",
            "docs": "/docs",
            "openapi": "/openapi.json",
        }

    return app


# Create app instance
app = create_app()
