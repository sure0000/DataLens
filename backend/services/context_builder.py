"""Copilot 上下文组装：业务域定位、表选取、知识聚合、优先级上下文构建。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import get_settings
from models import (
    BusinessDomain,
    BusinessDomainDescription,
    BusinessDomainKnowledgeBase,
    BusinessDomainSelection,
    ColumnMeta,
    DataSource,
    KnowledgeBase,
    KnowledgeEntry,
    TableKnowledgeBase,
    TableKnowledgeEntry,
    TableMeta,
    TableSummary,
)
from services.retrieval_service import search_entries_hybrid


def latest_table_summaries(db: Session) -> dict[int, TableSummary]:
    subq = (
        select(
            TableSummary.table_id.label("tid"),
            func.max(TableSummary.generated_at).label("max_at"),
        )
        .group_by(TableSummary.table_id)
        .subquery()
    )
    stmt = (
        select(TableSummary)
        .join(subq, TableSummary.table_id == subq.c.tid)
        .where(TableSummary.generated_at == subq.c.max_at)
    )
    rows = db.execute(stmt).scalars().all()
    return {row.table_id: row for row in rows}


def tables_from_business_domain(db: Session, domain_id: int) -> list[TableMeta]:
    selections = db.execute(
        select(BusinessDomainSelection).where(BusinessDomainSelection.domain_id == domain_id)
    ).scalars().all()
    by_id: dict[int, TableMeta] = {}
    for sel in selections:
        ds_id = sel.datasource_id
        db_name = (sel.database_name or "").strip()
        if not db_name:
            continue
        raw_tn = sel.table_name
        tn = (raw_tn or "").strip() if raw_tn is not None else ""
        if not tn:
            rows = db.execute(
                select(TableMeta).where(TableMeta.datasource_id == ds_id, TableMeta.database_name == db_name)
            ).scalars().all()
            if not rows:
                rows = db.execute(
                    select(TableMeta).where(
                        TableMeta.datasource_id == ds_id,
                        func.lower(TableMeta.database_name) == db_name.lower(),
                    )
                ).scalars().all()
        else:
            rows = db.execute(
                select(TableMeta).where(
                    TableMeta.datasource_id == ds_id,
                    TableMeta.database_name == db_name,
                    TableMeta.table_name == tn,
                )
            ).scalars().all()
            if not rows:
                rows = db.execute(
                    select(TableMeta).where(
                        TableMeta.datasource_id == ds_id,
                        func.lower(TableMeta.database_name) == db_name.lower(),
                        func.lower(TableMeta.table_name) == tn.lower(),
                    )
                ).scalars().all()
        for t in rows:
            by_id[t.id] = t
    return sorted(by_id.values(), key=lambda t: (t.datasource_id or 0, (t.database_name or ""), (t.table_name or "")))


def kb_ids_for_business_domain(db: Session, business_domain_id: int) -> list[int]:
    rows = db.execute(
        select(BusinessDomainKnowledgeBase.knowledge_base_id).where(
            BusinessDomainKnowledgeBase.domain_id == business_domain_id
        )
    ).scalars().all()
    out: list[int] = []
    seen: set[int] = set()
    for kid in rows:
        i = int(kid)
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def candidate_table_ids_from_domain_knowledge(
    db: Session,
    question: str,
    business_domain_id: int,
    domain_tables: list[TableMeta],
    *,
    top_k_per_kb: int = 8,
) -> list[int]:
    allowed = {t.id for t in domain_tables}
    if not allowed or not (question or "").strip():
        return []

    kb_ids = kb_ids_for_business_domain(db, business_domain_id)
    if not kb_ids:
        return []

    merged_hits: dict[int, dict[str, Any]] = {}
    for kb_id in kb_ids:
        for hit in search_entries_hybrid(db, kb_id, question.strip(), top_k=top_k_per_kb):
            eid = int(hit["entry_id"])
            merged_hits.setdefault(eid, hit)

    candidate: list[int] = []
    seen_tid: set[int] = set()

    for eid in merged_hits:
        for tid in db.execute(
            select(TableKnowledgeEntry.table_id).where(TableKnowledgeEntry.knowledge_entry_id == eid)
        ).scalars().all():
            tid = int(tid)
            if tid in allowed and tid not in seen_tid:
                seen_tid.add(tid)
                candidate.append(tid)

    for hit in merged_hits.values():
        blob = f"{hit.get('title') or ''} {hit.get('summary') or ''} {hit.get('snippet') or ''}"
        for t in domain_tables:
            if t.id in seen_tid:
                continue
            tn = (t.table_name or "").strip()
            if not tn:
                continue
            fq = f"{t.database_name}.{t.table_name}"
            if fq in blob or tn in blob:
                if t.id in allowed:
                    seen_tid.add(t.id)
                    candidate.append(t.id)

    return candidate


def all_tables_for_copilot_fallback(
    db: Session, preferred_datasource_id: int | None, max_tables: int
) -> list[TableMeta]:
    table_rows = db.execute(select(TableMeta).order_by(TableMeta.created_at.desc())).scalars().all()
    if preferred_datasource_id is not None:
        table_rows = [t for t in table_rows if t.datasource_id == preferred_datasource_id] + [
            t for t in table_rows if t.datasource_id != preferred_datasource_id
        ]
    seen_tables: set[tuple[int | None, str, str]] = set()
    selected_tables: list[TableMeta] = []
    for t in table_rows:
        key = (t.datasource_id, t.database_name, t.table_name)
        if key in seen_tables:
            continue
        seen_tables.add(key)
        selected_tables.append(t)
        if len(selected_tables) >= max_tables:
            break
    return selected_tables


def resolve_table_meta_for_trace(
    db: Session,
    *,
    datasource_id: int,
    default_database: str | None,
    db_part: str | None,
    table_name: str,
) -> TableMeta | None:
    schema = ((db_part or "").strip() or (default_database or "").strip()) or ""
    tbl = (table_name or "").strip()
    if not datasource_id or not schema or not tbl:
        return None
    row = db.execute(
        select(TableMeta)
        .where(
            TableMeta.datasource_id == datasource_id,
            TableMeta.database_name == schema,
            TableMeta.table_name == tbl,
        )
        .limit(1)
    ).scalars().first()
    if row:
        return row
    return db.execute(
        select(TableMeta)
        .where(
            TableMeta.datasource_id == datasource_id,
            func.lower(TableMeta.database_name) == schema.lower(),
            func.lower(TableMeta.table_name) == tbl.lower(),
        )
        .limit(1)
    ).scalars().first()


def reasoning3_basis_chain(
    db: Session,
    *,
    business_domain_id: int | None,
    tm: TableMeta | None,
    table_narrative: str,
    datasource_fallback: DataSource | None = None,
    database_name_fallback: str | None = None,
) -> str:
    parts: list[str] = []
    if business_domain_id:
        dom = db.get(BusinessDomain, business_domain_id)
        if dom:
            parts.append(f"业务域：会话绑定「{dom.name}」（id={dom.id}），用于关联知识库与域内表策略上下文。")
        else:
            parts.append(f"业务域：请求携带 domain_id={business_domain_id}，元数据中未找到对应业务域。")
    else:
        parts.append("业务域：未选择业务域，本链路未经过域级知识库路由。")

    if tm and tm.datasource_id:
        ds = db.get(DataSource, tm.datasource_id)
        if ds:
            dname = (ds.name or "").strip() or f"id={ds.id}"
            parts.append(f"数据库：数据源「{dname}」（类型 {ds.source_type}），逻辑库/命名空间为「{tm.database_name}」。")
        else:
            parts.append(f"数据库：表记录关联 datasource_id={tm.datasource_id}，但未检索到数据源实体。")
    elif datasource_fallback:
        dname = (datasource_fallback.name or "").strip() or f"id={datasource_fallback.id}"
        ns = (database_name_fallback or "").strip() or (datasource_fallback.database or "") or "默认"
        parts.append(f"数据库：当前解析锚定数据源「{dname}」（类型 {datasource_fallback.source_type}），命名空间「{ns}」。")
    elif tm:
        parts.append("数据库：表元数据缺少 datasource_id，无法下钻到连接配置。")
    else:
        parts.append("数据库：无表元数据锚点，无法解析到具体数据源与库名。")

    if tm:
        fq = f"{tm.database_name}.{tm.table_name}"
        parts.append(f"数据表：元数据登记「{fq}」（table_id={tm.id}）。{table_narrative}")
    else:
        parts.append(f"数据表：{table_narrative}")

    return "‖".join(parts)


def build_priority_context(
    db: Session,
    table_id: int | None,
    business_domain_id: int | None = None,
    question: str | None = None,
) -> tuple[str, str, str, int | None, str]:
    settings = get_settings()
    max_unscoped = settings.copilot_max_tables_without_domain

    latest_summaries = latest_table_summaries(db)
    preferred_table = db.get(TableMeta, table_id) if table_id else None
    preferred_datasource_id = preferred_table.datasource_id if preferred_table else None

    domain_header = ""
    table_scope_note = ""
    selected_tables: list[TableMeta] = []

    if table_id and preferred_table:
        selected_tables = [preferred_table]
        table_scope_note = (
            f"表定位：会话锁定单表 table_id={preferred_table.id}（{preferred_table.database_name}.{preferred_table.table_name}）。"
        )

    if not selected_tables and business_domain_id:
        domain_rows = tables_from_business_domain(db, business_domain_id)
        dom = db.get(BusinessDomain, business_domain_id)
        dom_label = (dom.name.strip() if dom and (dom.name or "").strip() else f"id={business_domain_id}")
        if domain_rows:
            q = (question or "").strip()
            cand_ids = (
                candidate_table_ids_from_domain_knowledge(db, q, business_domain_id, domain_rows) if q else []
            )
            allowed_ids = {t.id for t in domain_rows}
            narrowed_metas: list[TableMeta] = []
            for tid in cand_ids:
                if tid not in allowed_ids:
                    continue
                tm = db.get(TableMeta, tid)
                if tm is not None:
                    narrowed_metas.append(tm)
            if narrowed_metas:
                selected_tables = narrowed_metas
                preview = "、".join(f"{t.database_name}.{t.table_name}" for t in narrowed_metas[:10])
                if len(narrowed_metas) > 10:
                    preview += "…"
                domain_header = (
                    f"[业务域候选表 — 知识检索筛选] 会话绑定业务域「{dom_label}」（domain_id={business_domain_id}）。"
                    "已在业务域关联知识库中按用户问题做语义检索，并结合条目与表的显式关联及知识正文中的表名提及，"
                    f"得到下列 {len(narrowed_metas)} 张候选表的元数据与列语义；请先结合上方业务域知识理解业务，再于候选集合中确认最终使用的表并生成只读 SQL。\n\n"
                )
                table_scope_note = f"表定位（业务域）：知识检索筛得 {len(narrowed_metas)} 张候选表：{preview}。"
            else:
                selected_tables = domain_rows
                domain_header = (
                    f"[业务域候选表 — 知识检索未筛中] 会话绑定业务域「{dom_label}」（domain_id={business_domain_id}）。"
                    "业务域知识检索未从条目关联或正文中锚定到具体表，已加载本域挂载的全部"
                    f" {len(domain_rows)} 张已登记表元数据；请结合业务域知识后再确认表与 SQL。\n\n"
                )
                table_scope_note = (
                    f"表定位（业务域）：知识条目未锚定到单表，已加载域内全部 {len(domain_rows)} 张挂载表元数据。"
                )
        else:
            selected_tables = all_tables_for_copilot_fallback(db, preferred_datasource_id, max_unscoped)
            domain_header = (
                f"[提示] 业务域「{dom_label}」（domain_id={business_domain_id}）下暂无已解析的挂载表，或域不存在；"
                f"已退化为全局最近登记的数据表（至多 {max_unscoped} 张）。\n\n"
            )

    if not selected_tables:
        selected_tables = all_tables_for_copilot_fallback(db, preferred_datasource_id, max_unscoped)
        if not business_domain_id and len(selected_tables) >= max_unscoped:
            domain_header = (
                f"[提示] 未指定业务域；全局已登记表较多，当前上下文仅含最近 {max_unscoped} 张表。"
                "建议在 Copilot 中选择业务域以加载该域内全部挂载表。\n\n"
            )

    datasource_ids = [t.datasource_id for t in selected_tables if t.datasource_id is not None]
    datasource_ids_unique = list(dict.fromkeys(datasource_ids))
    datasources = (
        db.execute(select(DataSource).where(DataSource.id.in_(datasource_ids_unique))).scalars().all()
        if datasource_ids_unique
        else []
    )
    context_lines = ["[优先上下文-数据源采集信息]"]
    if preferred_table:
        context_lines.append(
            f"当前指定表: {preferred_table.database_name}.{preferred_table.table_name} (table_id={preferred_table.id})"
        )
    for d in datasources:
        context_lines.append(
            f"- 数据源[{d.id}] {d.name} ({d.source_type}) 数据库={d.database} | 备注: {d.description or '无'}"
        )

    analysis_lines = ["[优先上下文-AI分析信息]"]
    merged_summary_parts: list[str] = []
    for t in selected_tables:
        summary = latest_summaries.get(t.id)
        use_cases = summary.use_cases if summary and summary.use_cases else ""
        key_cols = summary.key_columns if summary and summary.key_columns else ""
        table_line = f"- {t.database_name}.{t.table_name} 状态={t.status}"
        if summary and summary.summary:
            table_line += f" | 摘要={summary.summary}"
            merged_summary_parts.append(summary.summary)
        if use_cases:
            table_line += f" | 场景={use_cases}"
        if key_cols:
            table_line += f" | 关键字段={key_cols}"
        analysis_lines.append(table_line)

    selected_table_ids = [t.id for t in selected_tables]
    if table_id:
        selected_table_ids = [table_id]
    cols = (
        db.execute(select(ColumnMeta).where(ColumnMeta.table_id.in_(selected_table_ids))).scalars().all()
        if selected_table_ids
        else []
    )
    schema_lines = []
    for c in cols:
        qm = c.quality_metrics if isinstance(c.quality_metrics, dict) else {}
        em = qm.get("enum") if isinstance(qm, dict) else None
        agg_hint = qm.get("aggregation_hint", "") if isinstance(qm, dict) else ""
        enum_tail = ""
        if isinstance(em, dict):
            vals = em.get("values")
            if isinstance(vals, list) and vals:
                joined = ",".join(str(v) for v in vals[:32])
                if len(vals) > 32:
                    joined += ",…"
                enum_tail = f" | enum_values={joined}"
        agg_tail = f" | aggregation={agg_hint}" if agg_hint else ""
        schema_lines.append(
            f"{c.table_id}.{c.column_name} | {c.data_type or ''} | semantic={c.semantic_type or ''} | desc={c.semantic_desc or ''}{enum_tail}{agg_tail}"
        )

    context_text = domain_header + "\n".join(context_lines)
    analysis_text = "\n".join(analysis_lines)
    schema_text = "\n".join(schema_lines)
    summary_text = "；".join(merged_summary_parts[:6])

    resolved_table_id = table_id
    if resolved_table_id is None and preferred_table:
        resolved_table_id = preferred_table.id
    if resolved_table_id is None and selected_tables:
        resolved_table_id = selected_tables[0].id
    return context_text + "\n" + analysis_text, schema_text, summary_text, resolved_table_id, table_scope_note


def collect_knowledge_context_text(
    db: Session, question: str, business_domain_id: int | None, table_id: int | None
) -> str:
    kb_ids: list[int] = []
    seen_kb: set[int] = set()

    def add_kb(kid: int) -> None:
        if kid in seen_kb:
            return
        seen_kb.add(kid)
        kb_ids.append(kid)

    if business_domain_id:
        for kid in db.execute(
            select(BusinessDomainKnowledgeBase.knowledge_base_id).where(
                BusinessDomainKnowledgeBase.domain_id == business_domain_id
            )
        ).scalars().all():
            add_kb(int(kid))

    pinned_ids: list[int] = []
    seen_ent: set[int] = set()
    if table_id:
        for kid in db.execute(
            select(TableKnowledgeBase.knowledge_base_id).where(TableKnowledgeBase.table_id == table_id)
        ).scalars().all():
            add_kb(int(kid))
        for eid in db.execute(
            select(TableKnowledgeEntry.knowledge_entry_id).where(TableKnowledgeEntry.table_id == table_id)
        ).scalars().all():
            eid = int(eid)
            if eid in seen_ent:
                continue
            seen_ent.add(eid)
            pinned_ids.append(eid)

    sections: list[str] = []
    max_total_chars = 120000
    pinned_set = set(pinned_ids)

    if pinned_ids:
        entries = list(db.execute(select(KnowledgeEntry).where(KnowledgeEntry.id.in_(pinned_ids))).scalars().all())
        entry_by_id = {e.id: e for e in entries}
        reserve_for_semantics = min(52000, max(16000, max_total_chars // 3))
        pin_budget = max(12000, max_total_chars - reserve_for_semantics - 900)
        per_pin_cap = min(96000, max(6144, pin_budget // len(pinned_ids)))
        pin_lines = ["[表关联知识条目 — 固定全文]"]
        for eid in pinned_ids:
            e = entry_by_id.get(eid)
            if not e:
                continue
            kb = db.get(KnowledgeBase, e.knowledge_base_id)
            kb_name = kb.name if kb else "?"
            summary = ((e.summary or "").strip()).replace("\r\n", "\n")
            body = ((e.body or "").strip()).replace("\r\n", "\n")
            preamble = ""
            if summary:
                preamble = f"简述：{summary}\n\n"
            room = max(512, per_pin_cap - len(preamble) - len(e.title))
            plain_body = body
            if len(plain_body) > room:
                plain_body = plain_body[: max(256, room)] + "\n…（以上为模型上下文中的截断；知识库条目内仍可查看完整正文。）"
            pin_lines.append(f"## {e.title}（知识库：{kb_name}，entry_id={e.id}）\n{preamble}{plain_body}")
        sections.append("\n".join(pin_lines))

    if kb_ids and question.strip():
        sem_lines = ["[知识库语义检索 — 与问题相关的片段]"]
        merged_hits: dict[int, dict[str, Any]] = {}
        for kb_id in kb_ids:
            for hit in search_entries_hybrid(db, kb_id, question.strip(), top_k=6):
                eid = int(hit["entry_id"])
                if eid in pinned_set:
                    continue
                merged_hits.setdefault(eid, hit)
        for hit in list(merged_hits.values())[:20]:
            title = str(hit.get("title") or "")
            summary_hit = str(hit.get("summary") or "").strip().replace("\r\n", "\n")
            snippet = str(hit.get("snippet") or "").strip().replace("\r\n", "\n")
            if len(snippet) > 1200:
                snippet = snippet[:1200] + "…"
            block = f"- {title} (entry_id={hit['entry_id']})"
            if summary_hit:
                sh = summary_hit if len(summary_hit) <= 480 else summary_hit[:480] + "…"
                block += f"\n  简述：{sh}"
            block += f"\n  {snippet}"
            sem_lines.append(block)
        if len(sem_lines) > 1:
            sections.append("\n".join(sem_lines))

    text = "\n\n".join(sections).strip()
    if len(text) > max_total_chars:
        return f"{text[:max_total_chars]}\n…（知识上下文总长度超限，尾部已省略；可把关键内容拆为多条条目或收窄检索范围）"
    return text
