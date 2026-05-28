import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from database import get_db
from models import BusinessDomain
from services.business_domain_scope import resolve_scope_domain
from services.rag_service import answer

router = APIRouter(prefix="/api", tags=["copilot"])


class AskBody(BaseModel):
    question: str
    table_id: int | None = None
    business_domain_id: int | None = None
    """auto / 空 表示自动选模型；否则为 catalog 中的 id，如 deepseek:deepseek-chat"""
    chat_model: str | None = None


@router.post("/ask")
async def ask(
    body: AskBody,
    db: Session = Depends(get_db),
    scope_domain: BusinessDomain = Depends(resolve_scope_domain),
) -> dict:
    domain_id = body.business_domain_id if body.business_domain_id is not None else scope_domain.id
    return await answer(
        db,
        body.question,
        body.table_id,
        domain_id,
        chat_model=body.chat_model,
    )


@router.get("/ask/ontology-trace")
async def ask_ontology_trace(
    question: str = Query(..., description="User question for ontology routing"),
    domain_id: int | None = Query(None, description="Business domain ID"),
    db: Session = Depends(get_db),
    scope_domain: BusinessDomain = Depends(resolve_scope_domain),
) -> dict[str, Any]:
    """Return the ontology routing trace for a question.

    Shows which concepts, tables, and lineage expansions would be used
    without generating SQL or executing against a database.
    """
    from services.copilot.pipeline import route_question

    try:
        resolved_domain_id = domain_id if domain_id is not None else scope_domain.id
        result = route_question(db, question, domain_id=resolved_domain_id)
        return {"status": "ok", **result}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@router.post("/ask/stream")
async def ask_stream(
    body: AskBody,
    db: Session = Depends(get_db),
    scope_domain: BusinessDomain = Depends(resolve_scope_domain),
) -> StreamingResponse:
    domain_id = body.business_domain_id if body.business_domain_id is not None else scope_domain.id

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
                domain_id,
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
                await asyncio.sleep(0)
            elif item.get("kind") == "trace":
                yield f"event: trace\ndata: {json.dumps(item['trace'], ensure_ascii=False)}\n\n"
                # 让出事件循环，便于 ASGI/代理尽快把分块刷到客户端，推理步骤逐条可见
                await asyncio.sleep(0)

        result = await answer_task
        answer_text = str(result.get("answer") or "")
        explanation_text = str(result.get("explanation") or "")
        piece = 160
        for i in range(0, len(answer_text), piece):
            chunk = answer_text[i : i + piece]
            yield f"event: delta\ndata: {json.dumps({'field': 'answer', 'delta': chunk}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
        for i in range(0, len(explanation_text), piece):
            chunk = explanation_text[i : i + piece]
            yield f"event: delta\ndata: {json.dumps({'field': 'explanation', 'delta': chunk}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
        yield f"event: result\ndata: {json.dumps(result, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
