import os
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, research
from app.memory.conversation_store import init_db

load_dotenv()

log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup, clean up on shutdown."""
    logger.info("Starting up Decision Research Assistant...")

    # Initialize SQLite tables
    await init_db()
    logger.info("SQLite database initialized")

    # Validate critical env vars (warn, don't crash — allows running without all keys)
    for var in ["ANTHROPIC_API_KEY", "TAVILY_API_KEY", "PINECONE_API_KEY"]:
        if not os.getenv(var):
            logger.warning(f"Environment variable {var} is not set")

    yield

    logger.info("Shutting down...")


app = FastAPI(
    title="Decision Research Assistant",
    description="Deep research agent powered by LangGraph",
    version="0.1.0",
    lifespan=lifespan,
)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Conversation-Id"],
)

app.include_router(health.router)
app.include_router(research.router, prefix="/research")
