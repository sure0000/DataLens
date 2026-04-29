from fastapi import APIRouter
from pydantic import BaseModel

from services.schema_extractor import get_tables

router = APIRouter(prefix="/api", tags=["connect"])


class ConnectBody(BaseModel):
    source_type: str
    host: str
    port: int
    database: str
    username: str
    password: str


@router.post("/connect")
def connect(body: ConnectBody) -> dict:
    tables = get_tables(body.model_dump())
    return {"success": True, "tables": tables}
