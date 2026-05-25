# Cutover checklist — Formal OWL ontology migration

## 本地 Fuseki 启动

**默认无需 Docker。** 本体三元组写入项目内 Trig 文件（`.run/ontology-store/datalens.trig`），由 rdflib 提供 SPARQL，后端启动即可用。

```bash
./scripts/service.sh start   # 不依赖 Docker
```

可选：若需要独立 Fuseki 服务（Docker）：

```bash
# .env 中设置 FUSEKI_URL=http://localhost:3030 且 FUSEKI_AUTO_START=true
./scripts/fuseki.sh start
docker compose up -d fuseki
```

`.env` 关键配置：

```env
ONTOLOGY_LOCAL_STORE_PATH=.run/ontology-store/datalens.trig
# FUSEKI_URL=              留空 = 本地文件（推荐无 Docker）
# FUSEKI_AUTO_START=false
ONTOLOGY_ENABLED=true
```

验证：

```bash
curl http://localhost:3030/$/ping          # OK
curl http://localhost:8000/api/ontology/health
./scripts/fuseki.sh status
```

数据持久化目录：`.run/fuseki-data/`

---

## Cutover 步骤

1. Run: `python scripts/migrate_to_ontology.py`
2. Verify: `pytest backend/tests/test_ontology.py`
3. POST `/api/ontology/knowledge-bases/{kb_id}/sync-from-legacy` per KB
4. Copilot golden set smoke (10 questions)
5. Legacy tables remain read-only for 30 days; new writes go to Fuseki.

Deprecated modules: `semantic_extraction` (step 4 → ontology), `semantic_relation_sync`, `semantic_grounding`, `knowledge_semantic` CRUD → `ontology` router.
