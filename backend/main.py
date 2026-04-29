from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from config import get_settings
from database import init_db
from routers.analyze import router as analyze_router
from routers.business_domains import router as business_domains_router
from routers.connect import router as connect_router
from routers.copilot import router as copilot_router
from routers.datasources import router as datasources_router
from routers.tables import router as tables_router

settings = get_settings()
logger = logging.getLogger(__name__)
app = FastAPI(title="DataLens MVP")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    try:
        init_db()
    except Exception as exc:  # noqa: BLE001
        # Allow service startup even when local DB is unavailable.
        logger.warning("Database init skipped: %s", exc)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


app.include_router(connect_router)
app.include_router(analyze_router)
app.include_router(tables_router)
app.include_router(copilot_router)
app.include_router(datasources_router)
app.include_router(business_domains_router)
