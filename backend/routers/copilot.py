import asyncio
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from database import get_db
from services.rag_service import answer

router = APIRouter(prefix="/api", tags=["copilot"])


class AskBody(BaseModel):
    question: str
    table_id: int | None = None
    business_domain_id: int | None = None


@router.post("/ask")
async def ask(body: AskBody, db: Session = Depends(get_db)) -> dict:
    return await answer(db, body.question, body.table_id, body.business_domain_id)


@router.post("/ask/stream")
async def ask_stream(body: AskBody, db: Session = Depends(get_db)) -> StreamingResponse:
    async def event_stream():
        status_queue: asyncio.Queue[str] = asyncio.Queue()

        async def emit_status(stage: str):
            await status_queue.put(stage)

        answer_task = asyncio.create_task(
            answer(db, body.question, body.table_id, body.business_domain_id, stage_callback=emit_status)
        )

        while not answer_task.done() or not status_queue.empty():
            try:
                stage = await asyncio.wait_for(status_queue.get(), timeout=0.15)
                yield f"event: status\ndata: {json.dumps({'stage': stage}, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                continue

        result = await answer_task
        payload = json.dumps(result, ensure_ascii=False)
        for i in range(0, len(payload), 80):
            chunk = payload[i : i + 80]
            yield f"event: chunk\ndata: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.01)
        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
