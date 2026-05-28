from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from config import get_settings
from database import init_db
from services.git_schedule import start_git_sync_scheduler, stop_git_sync_scheduler
from services.ontology_loader import init_ontology
from security import enforce_request_auth
from routers.analyze import router as analyze_router
from routers.business_domains import router as business_domains_router
from routers.connect import router as connect_router
from routers.copilot import router as copilot_router
from routers.datasources import router as datasources_router
from routers.knowledge_bases import router as knowledge_bases_router
from routers.knowledge_git_sources import router as knowledge_git_sources_router
from routers.knowledge_api_sources import router as knowledge_api_sources_router
from routers.knowledge_database_imports import router as knowledge_database_imports_router
from routers.knowledge_ingestion import router as knowledge_ingestion_router
from routers.api_sources import router as api_sources_router

from routers.diagnostics import router as diagnostics_router
from routers.knowledge_semantic import router as knowledge_semantic_router
from routers.llm_settings import router as llm_settings_router
from routers.ontology import router as ontology_router
from routers.tables import router as tables_router

settings = get_settings()
logger = logging.getLogger(__name__)
app = FastAPI(title="DataLens MVP")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.cors_origins.split(",")],
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    # 前端会携带业务域隔离头，需在 CORS 预检中显式放行。
    allow_headers=["Content-Type", "Authorization", "Accept", "X-Business-Domain-Id"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    try:
        enforce_request_auth(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return await call_next(request)


@app.on_event("startup")
def on_startup() -> None:
    try:
        init_db()
    except Exception as exc:  # noqa: BLE001
        # Allow service startup even when local DB is unavailable.
        logger.warning("Database init skipped: %s", exc)
    if get_settings().ontology_enabled:
        try:
            init_ontology()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ontology init skipped: %s", exc)
    try:
        start_git_sync_scheduler()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Git 同步调度器未启动: %s", exc)


@app.on_event("shutdown")
def on_shutdown() -> None:
    try:
        stop_git_sync_scheduler()
    except Exception as exc:  # noqa: BLE001
        logger.warning("停止 Git 同步调度器时出错: %s", exc)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


app.include_router(connect_router)
app.include_router(analyze_router)
app.include_router(tables_router)
app.include_router(copilot_router)
app.include_router(datasources_router)
app.include_router(business_domains_router)
app.include_router(knowledge_bases_router)
app.include_router(knowledge_git_sources_router)
app.include_router(knowledge_api_sources_router)
app.include_router(knowledge_database_imports_router)
app.include_router(knowledge_ingestion_router)
app.include_router(api_sources_router)

app.include_router(diagnostics_router)
app.include_router(knowledge_semantic_router)
app.include_router(ontology_router)
app.include_router(llm_settings_router)
