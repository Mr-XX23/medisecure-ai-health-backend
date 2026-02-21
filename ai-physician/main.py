from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config.database import Database
from app.config.settings import settings
from app.api.vaidya import router as vaidya_router
from app.middleware import JWTAuthMiddleware
import logging

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    logger.info("Starting Vaidya AI Health Assistant Service...")
    logger.info(f"Environment: {settings.environment}")

    try:
        await Database.connect_db()
        logger.info("MongoDB connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise

    yield

    logger.info("Shutting down Vaidya AI Health Assistant Service...")
    await Database.close_db()
    logger.info("MongoDB connection closed")


app = FastAPI(
    title="Vaidya - AI Health Assistant",
    description="Vaidya is an intelligent AI supervisor that orchestrates specialized healthcare agents for symptom checking, medical history, drug interactions, provider search, and preventive care.",
    version="1.0.0",
    lifespan=lifespan,
)

# Middleware registration order matters in Starlette – add_middleware stacks LIFO,
# so the LAST one added becomes the OUTERMOST and runs first on every request.
#
# Desired execution order (outermost → innermost):
#   CORSMiddleware → JWTAuthMiddleware → route handler
#
# This ensures ALL responses (including 401 from JWT) carry CORS headers.

# JWT (inner) — runs after CORS
app.add_middleware(JWTAuthMiddleware)

# CORS (outer) — runs first on every request
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vaidya_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        db = Database.get_database()
        await db.command("ping")
        mongodb_status = "connected"
    except Exception as e:
        logger.error(f"MongoDB health check failed: {e}")
        mongodb_status = f"error: {str(e)}"

    return {
        "status": "ok",
        "service": "vaidya",
        "version": "1.0.0",
        "dependencies": {
            "mongodb": mongodb_status,
            "github_models": (
                "configured" if settings.github_token else "not configured"
            ),
        },
    }


@app.get("/")
async def root():
    return {
        "message": "Vaidya - AI Health Assistant Service",
        "description": "Intelligent multi-agent healthcare orchestration system",
        "version": "1.0.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.ai_physician_port,
        reload=settings.environment == "development",
    )
