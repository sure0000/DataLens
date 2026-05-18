"""AI 语义提取服务：从知识库文档中提取业务术语、指标口径和数据血缘。

设计原则：
- 复用现有 LLM 基础设施（_client_and_model_for_ref / resolve_effective_model）
- 提取结果写入 business_terms / metric_definitions / data_lineage 表
- 同 name + kb_id 去重（更新已有记录）
- 支持手动触发和自动触发（Git 同步后 / 文件导入后）
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (
    BusinessTerm,
    DataLineage,
    Document,
    DocumentChunk,
    KnowledgeEntry,
    KnowledgeGitSource,
    MetricDefinition,
    PipelineRun,
)

_logger = logging.getLogger(__name__)

# ── LLM Prompt Templates ──────────────────────────────────────────────

_TERM_EXTRACTION_SYSTEM = """你是数据语义分析专家。从给定的文档内容中提取业务术语（Business Terms）。

业务术语是企业日常使用的、有明确业务含义的词汇，例如：GMV（成交总额）、实收金额、订单状态、客户等级等。

输出严格 JSON 对象，键为 terms（数组），每个元素包含：
- name: 术语名称（简洁，2-8个汉字或英文缩写）
- type: 类型，必须是 metric（度量）/ enum（枚举）/ time（时间）/ dimension（维度）/ other（其他）
- definition: 一句话定义该术语的业务含义（中文，20-120字）
- related_fields: 相关的数据库字段名数组（从文档中推断，无则空数组）
- confidence: AI 置信度 0-100 的整数

规则：
1. 只提取明确的业务术语，不要提取通用词汇或技术术语
2. 置信度根据文档描述的清晰程度判断：清晰定义 80+，间接提及 50-70，不确定则跳过
3. 如果文档中没有可提取的业务术语，返回 {"terms": []}
4. 每个术语必须 unique，不要重复提取同义词（选择最常用的名称）
"""

_METRIC_EXTRACTION_SYSTEM = """你是数据分析专家。从给定的文档内容中提取指标口径定义（Metric Definitions）。

指标口径是「这个数怎么算」的明确定义，包含计算逻辑和统计规则，例如：
- 日GMV = SUM(orders.amount) WHERE orders.status = 'paid' AND date = today
- 付费率 = COUNT(DISTINCT paid_users) / COUNT(DISTINCT active_users) * 100%

输出严格 JSON 对象，键为 metrics（数组），每个元素包含：
- name: 指标名称（简洁，如「日GMV」「月活用户数」）
- formula: 计算公式（SQL/MDX 或文字描述，50-300字）
- caliber: 统计口径说明（包含/不包含的边界条件，30-200字）
- related_terms: 依赖的业务术语名称数组（从文档中推断）
- confidence: AI 置信度 0-100 的整数

规则：
1. 只提取有明确计算逻辑的指标，不要提取仅有名称没有公式的指标
2. 公式优先使用 SQL 风格表达
3. 口径说明要明确「包含」与「不包含」的边界
4. 如果文档中没有可提取的指标定义，返回 {"metrics": []}
"""

_LINEAGE_EXTRACTION_SYSTEM = """你是数据工程专家。从给定的代码文件中提取数据血缘关系（Data Lineage）。

数据血缘描述表之间的依赖关系：哪些表从哪些表派生而来，以及它们的数据分层（ODS/DWD/DWS/ADS）。

分层参考：
- ODS：贴源层，直接从业务系统同步的原始数据
- DWD：明细数据层，经过清洗和标准化的明细数据
- DWS：汇总数据层，按主题/维度汇总的轻度聚合数据
- ADS：应用数据层，面向具体报表/看板的宽表或指标表

输出严格 JSON 对象，键为 edges（数组），每个元素包含：
- source_table: 上游表名
- target_table: 下游表名
- source_field: 上游关联字段（可选）
- target_field: 下游关联字段（可选）
- source_layer: 上游表的层级（ODS/DWD/DWS/ADS，根据命名或上下文推断）
- target_layer: 下游表的层级
- transform_logic: 转换逻辑的简要描述（中文，20-100字）

规则：
1. 从 SQL 的 FROM/JOIN、dbt 的 ref()/source()、ORM 的 relationship 等模式识别表依赖
2. 如果文件不包含表间依赖关系，返回 {"edges": []}
3. 表名只保留名称部分，去掉 schema 前缀
"""

# ── Pipeline orchestration ────────────────────────────────────────────


async def _call_llm_json(client: Any, model_name: str, system_prompt: str, user_message: str, temperature: float = 0.1) -> dict[str, Any]:
    """调用 LLM 并解析 JSON 响应。"""
    resp = await client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        _logger.warning("Failed to parse LLM JSON response: %s", raw[:200])
        return {}


def _get_llm_client(db: Session) -> tuple[Any, str] | None:
    """获取 LLM 客户端和模型名；不可用时返回 None。"""
    try:
        from services.llm_models import has_any_llm_key, resolve_effective_model
        if not has_any_llm_key(db):
            return None
        from config import get_settings
        settings = get_settings()
        semantic_ref = getattr(settings, "semantic_model_ref", None)
        model_ref = resolve_effective_model(semantic_ref, db)
        if not model_ref:
            return None
        from services.llm_service import _client_and_model_for_ref
        return _client_and_model_for_ref(model_ref, db)
    except Exception:
        _logger.warning("Failed to get LLM client", exc_info=True)
        return None


def _start_pipeline_run(db: Session, kb_id: int, source_type: str | None = None) -> PipelineRun:
    run = PipelineRun(
        knowledge_base_id=kb_id,
        status="running",
        source_type=source_type,
        steps={"term_extraction": "pending", "metric_caliber": "pending", "data_lineage": "pending"},
    )
    db.add(run)
    db.commit()
    return run


def _finish_pipeline_run(db: Session, run: PipelineRun, success: bool = True) -> None:
    run.status = "completed" if success else "failed"
    run.completed_at = datetime.now(timezone.utc)
    db.commit()


# ── Term Extraction ────────────────────────────────────────────────────


async def extract_terms_from_kb(db: Session, kb_id: int) -> int:
    """从知识库中已索引的文档分块提取业务术语。

    返回提取到的术语数量（含更新）。
    """
    client_info = _get_llm_client(db)
    if client_info is None:
        _logger.warning("No LLM available for term extraction, kb=%s", kb_id)
        return 0

    client, model_name = client_info

    # 获取已索引的文档分块（采样：最多取 50 个高分块）
    chunks_query = (
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.knowledge_base_id == kb_id,
            Document.status == "indexed",
            DocumentChunk.quality_score >= 0.4,
        )
        .order_by(DocumentChunk.quality_score.desc().nulls_last())
        .limit(50)
    )
    chunks = db.execute(chunks_query).scalars().all()

    if not chunks:
        _logger.info("No eligible chunks for term extraction in kb=%s", kb_id)
        return 0

    total_extracted = 0
    existing_names: set[str] = set()

    for chunk in chunks:
        try:
            result = await _call_llm_json(client, model_name, _TERM_EXTRACTION_SYSTEM, chunk.content)
            terms_data = result.get("terms", [])
        except Exception:
            _logger.warning("LLM term extraction failed for chunk %s", chunk.id, exc_info=True)
            continue

        for item in terms_data:
            name = (item.get("name") or "").strip()
            if not name or name in existing_names:
                continue
            try:
                confidence = float(item.get("confidence", 50))
            except (ValueError, TypeError):
                confidence = 50.0

            # 去重检查
            existing = db.execute(
                select(BusinessTerm).where(
                    BusinessTerm.knowledge_base_id == kb_id,
                    BusinessTerm.name == name,
                )
            ).scalar_one_or_none()

            if existing:
                existing.type = item.get("type", existing.type) or "other"
                existing.definition = item.get("definition") or existing.definition
                existing.related_fields = item.get("related_fields", existing.related_fields) or []
                existing.confidence = round(confidence, 1)
                existing.updated_at = datetime.now(timezone.utc)
            else:
                term = BusinessTerm(
                    knowledge_base_id=kb_id,
                    name=name,
                    type=item.get("type") or "other",
                    definition=item.get("definition") or "",
                    source_entry_id=chunk.document.knowledge_entry_id if chunk.document else None,
                    related_fields=item.get("related_fields") or [],
                    confidence=round(confidence, 1),
                    status="pending_review",
                )
                db.add(term)

            existing_names.add(name)
            total_extracted += 1

    db.commit()
    _logger.info("Term extraction completed for kb=%s: %s terms", kb_id, total_extracted)
    return total_extracted


# ── Metric Extraction ──────────────────────────────────────────────────


async def extract_metrics_from_kb(db: Session, kb_id: int) -> int:
    """从知识库文档中提取指标口径定义。"""
    client_info = _get_llm_client(db)
    if client_info is None:
        _logger.warning("No LLM available for metric extraction, kb=%s", kb_id)
        return 0

    client, model_name = client_info

    # 获取文档（优先取 semantic_role 为 business_metric 的条目，其次取已索引文档）
    chunks_query = (
        select(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.knowledge_base_id == kb_id,
            Document.status == "indexed",
            DocumentChunk.quality_score >= 0.4,
        )
        .order_by(DocumentChunk.quality_score.desc().nulls_last())
        .limit(50)
    )
    chunks = db.execute(chunks_query).scalars().all()

    if not chunks:
        return 0

    total_extracted = 0
    existing_names: set[str] = set()

    for chunk in chunks:
        try:
            result = await _call_llm_json(client, model_name, _METRIC_EXTRACTION_SYSTEM, chunk.content)
            metrics_data = result.get("metrics", [])
        except Exception:
            _logger.warning("LLM metric extraction failed for chunk %s", chunk.id, exc_info=True)
            continue

        for item in metrics_data:
            name = (item.get("name") or "").strip()
            if not name or name in existing_names:
                continue
            try:
                confidence = float(item.get("confidence", 50))
            except (ValueError, TypeError):
                confidence = 50.0

            existing = db.execute(
                select(MetricDefinition).where(
                    MetricDefinition.knowledge_base_id == kb_id,
                    MetricDefinition.name == name,
                )
            ).scalar_one_or_none()

            if existing:
                existing.formula = item.get("formula") or existing.formula
                existing.caliber = item.get("caliber", existing.caliber)
                existing.related_terms = item.get("related_terms", existing.related_terms) or []
                existing.confidence = round(confidence, 1)
                existing.updated_at = datetime.now(timezone.utc)
            else:
                metric = MetricDefinition(
                    knowledge_base_id=kb_id,
                    name=name,
                    formula=item.get("formula") or "",
                    caliber=item.get("caliber"),
                    source_entry_id=chunk.document.knowledge_entry_id if chunk.document else None,
                    related_terms=item.get("related_terms") or [],
                    confidence=round(confidence, 1),
                    status="pending_review",
                )
                db.add(metric)

            existing_names.add(name)
            total_extracted += 1

    db.commit()
    _logger.info("Metric extraction completed for kb=%s: %s metrics", kb_id, total_extracted)
    return total_extracted


# ── Lineage Extraction ─────────────────────────────────────────────────


async def extract_lineage_from_kb(db: Session, kb_id: int) -> int:
    """从知识库的 Git 源代码文件中提取数据血缘关系。"""
    client_info = _get_llm_client(db)
    if client_info is None:
        _logger.warning("No LLM available for lineage extraction, kb=%s", kb_id)
        return 0

    client, model_name = client_info

    # 获取 Git 来源的已索引文档条目
    entries_query = (
        select(KnowledgeEntry)
        .where(
            KnowledgeEntry.knowledge_base_id == kb_id,
            KnowledgeEntry.source_meta["kind"].astext == "git_file",
        )
        .limit(80)
    )
    entries = db.execute(entries_query).scalars().all()

    if not entries:
        _logger.info("No git-sourced entries for lineage extraction in kb=%s", kb_id)
        return 0

    # 获取 Git 源 id
    git_sources = db.execute(
        select(KnowledgeGitSource).where(KnowledgeGitSource.knowledge_base_id == kb_id)
    ).scalars().all()
    git_source_id = git_sources[0].id if git_sources else None

    total_extracted = 0
    existing_pairs: set[tuple[str, str]] = set()

    for entry in entries:
        body = (entry.body or "").strip()
        if not body or len(body) < 50:
            continue

        # 限制发送给 LLM 的文本长度
        text = body[:8000]

        try:
            result = await _call_llm_json(client, model_name, _LINEAGE_EXTRACTION_SYSTEM, text)
            edges_data = result.get("edges", [])
        except Exception:
            _logger.warning("LLM lineage extraction failed for entry %s", entry.id, exc_info=True)
            continue

        for item in edges_data:
            source_table = (item.get("source_table") or "").strip()
            target_table = (item.get("target_table") or "").strip()
            if not source_table or not target_table:
                continue
            pair = (source_table, target_table)
            if pair in existing_pairs:
                continue

            lineage = DataLineage(
                knowledge_base_id=kb_id,
                git_source_id=git_source_id,
                source_table=source_table,
                target_table=target_table,
                source_field=item.get("source_field"),
                target_field=item.get("target_field"),
                layer=item.get("target_layer") or item.get("source_layer") or "DWD",
                transform_logic=item.get("transform_logic"),
                status="done",
            )
            db.add(lineage)
            existing_pairs.add(pair)
            total_extracted += 1

    db.commit()
    _logger.info("Lineage extraction completed for kb=%s: %s edges", kb_id, total_extracted)
    return total_extracted


# ── Pipeline Orchestration ─────────────────────────────────────────────


async def run_semantic_pipeline(db: Session, kb_id: int, source_type: str | None = None) -> dict[str, Any]:
    """编排执行完整的语义清洗流水线。"""
    run = _start_pipeline_run(db, kb_id, source_type)

    steps_status: dict[str, Any] = {}

    try:
        # Step 1: 术语提取
        term_count = await extract_terms_from_kb(db, kb_id)
        steps_status["term_extraction"] = {"status": "done", "count": term_count}
        run.steps = steps_status
        db.commit()
    except Exception:
        _logger.warning("Term extraction failed for kb=%s", kb_id, exc_info=True)
        steps_status["term_extraction"] = {"status": "failed", "count": 0}

    try:
        # Step 2: 指标口径提取
        metric_count = await extract_metrics_from_kb(db, kb_id)
        steps_status["metric_caliber"] = {"status": "done", "count": metric_count}
        run.steps = steps_status
        db.commit()
    except Exception:
        _logger.warning("Metric extraction failed for kb=%s", kb_id, exc_info=True)
        steps_status["metric_caliber"] = {"status": "failed", "count": 0}

    try:
        # Step 3: 数据血缘（仅 Git 源知识库）
        has_git = db.execute(
            select(KnowledgeGitSource).where(KnowledgeGitSource.knowledge_base_id == kb_id).limit(1)
        ).first()
        if has_git:
            lineage_count = await extract_lineage_from_kb(db, kb_id)
            steps_status["data_lineage"] = {"status": "done", "count": lineage_count}
        else:
            steps_status["data_lineage"] = {"status": "skipped", "reason": "非代码库知识库"}
        run.steps = steps_status
        db.commit()
    except Exception:
        _logger.warning("Lineage extraction failed for kb=%s", kb_id, exc_info=True)
        steps_status["data_lineage"] = {"status": "failed", "count": 0}

    success = not any(s.get("status") == "failed" for s in steps_status.values())
    _finish_pipeline_run(db, run, success)

    return {
        "status": "completed" if success else "completed_with_errors",
        "steps": steps_status,
        "run_id": run.id,
    }
