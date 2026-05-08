import asyncio
import json
from typing import Any

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
    """auto / 空 表示自动选模型；否则为 catalog 中的 id，如 deepseek:deepseek-chat"""
    chat_model: str | None = None


@router.post("/ask")
async def ask(body: AskBody, db: Session = Depends(get_db)) -> dict:
    return await answer(
        db,
        body.question,
        body.table_id,
        body.business_domain_id,
        chat_model=body.chat_model,
    )


@router.post("/ask/stream")
async def ask_stream(body: AskBody, db: Session = Depends(get_db)) -> StreamingResponse:
    async def event_stream():
        event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def emit_status(stage: str):
            await event_queue.put({"kind": "stage", "stage": stage})

        async def emit_trace(row: dict):
            await event_queue.put({"kind": "trace", "trace": row})

        answer_task = asyncio.create_task(
            answer(
                db,
                body.question,
                body.table_id,
                body.business_domain_id,
                stage_callback=emit_status,
                trace_callback=emit_trace,
                chat_model=body.chat_model,
            )
        )

        while not answer_task.done() or not event_queue.empty():
            try:
                item = await asyncio.wait_for(event_queue.get(), timeout=0.12)
            except asyncio.TimeoutError:
                continue
            if item.get("kind") == "stage":
                yield f"event: status\ndata: {json.dumps({'stage': item['stage']}, ensure_ascii=False)}\n\n"
            elif item.get("kind") == "trace":
                yield f"event: trace\ndata: {json.dumps(item['trace'], ensure_ascii=False)}\n\n"

        result = await answer_task
        payload = json.dumps(result, ensure_ascii=False)
        for i in range(0, len(payload), 80):
            chunk = payload[i : i + 80]
            yield f"event: chunk\ndata: {json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.01)
        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
