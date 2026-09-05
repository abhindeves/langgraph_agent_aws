from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langfuse import get_client

from app.api.v1.routes import router as v1_router
from app.core.config import get_settings
from app.core.middleware import CorrelationIdMiddleware
from app.core.errors import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"Starting {settings.PROJECT_NAME} (v{settings.VERSION})...")
    # Verify Langfuse connection if configured
    try:
        client = get_client()
        if client.auth_check():
            print("Langfuse client authenticated successfully.")
        else:
            print("Warning: Langfuse authentication failed.")
    except Exception as e:
        print(f"Warning: Could not connect to Langfuse: {e}")
    yield
    print("Shutting down agent service...")
    try:
        get_client().flush()
    except Exception:
        pass


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        lifespan=lifespan,
    )

    # 1. Correlation ID Middleware (must be first to wrap all requests & errors)
    app.add_middleware(CorrelationIdMiddleware)

    # 2. Allow CORS for web frontends
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 3. Register Centralized Exception Handlers
    register_exception_handlers(app)

    # 4. Root health probe (for AWS ECS / load balancers)
    @app.get("/health", tags=["Health"])
    async def health():
        return {
            "status": "healthy",
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
        }

    # 5. Versioned API routes (v1)
    app.include_router(v1_router, prefix="/api/v1", tags=["v1"])
    return app


app = create_app()
