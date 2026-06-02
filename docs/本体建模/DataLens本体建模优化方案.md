# DataLens 本体建模优化方案

> 对照 [本体建模理论标准](./本体建模理论标准.md)，识别 DataLens 当前实现的差距，按 P0–P3 优先级制定优化路线。

---

## 一、对照标准：差距总览

| 标准产出物 / 能力 | 现状 | 差距等级 | 关键缺口 |
|------------------|------|----------|----------|
| 概念词典 / 词汇表 | ✅ term_extractor + SKOS 三元组 | **P2** | 术语间等价关系未利用（skos:exactMatch 无填充） |
| 类层次结构 | ✅ TBox class hierarchy + disjointWith | **P1** | 无 `owl:Restriction`（someValuesFrom/allValuesFrom）；hierarchy_builder 偏浅 |
| 关系定义 | ✅ 9 种标准 ObjectProperty + property characteristics | **P2** | 关系类型偏固定，缺少领域特定关系扩展机制 |
| 属性定义 | ✅ 30+ DatatypeProperty + schema_extractor | **P1** | DatatypeProperty 未声明 domain/range；与物理列映射混在同一系统 |
| OWL 公理 | ⚠️ disjointWith + FunctionalProperty + TransitiveProperty 等 | **P1** | **零个 `owl:Restriction`**；无 class-level existential/universal 约束 |
| SHACL 校验 | ✅ 11 个 Shape 文件 + 写入门控 | **P1** | 校验以结构检查为主，缺领域级业务规则 Shape |
| SWRL / 规则 | ❌ inference.rules 使用自定义 Datalog 格式 | **P2** | 非标准格式，不兼容 SWRL 生态；执行仅 1 个 property chain 规则 |
| 交叉一致性校验 | ❌ 各 extractor 独立运行，无交叉验证 | **P0** | metric 可引用不存在的 term；term 可 mapsToColumn 到不存在的表 |
| 层级构建 | ⚠️ hierarchy_builder.py 122 行，仅依赖 LLM parent_concept | **P2** | 无循环检测、无层级深度治理 |
| 本体演化 | ⚠️ write_with_version / deprecate_entity 存在但未接入 orchestrator | **P3** | 无 TBox 版本记录、无 ABox 迁移 |
| 可视化 | ⚠️ RelationGraph.tsx 单组件，50 节点硬上限 | **P3** | 无层级视图、无血缘追踪、无导出 |

---

## 二、优化路线总览

```
P0 (本周)   → 交叉一致性校验：消除「脏数据入图」
P1 (2 周)   → TBox 增强 + SHACL 领域约束：补齐标准本体核心能力
P2 (3 周)   → 规则标准化 + 层级增强 + 术语等价：提升推理和语义覆盖
P3 (持续)   → 可视化 + 本体演化 + 跨领域对齐：企业级完善
```

---

## 三、P0 — 交叉一致性校验（✅ 已实现）

> `cross_entity_validator.py` 已接入 orchestrator，每次 pipeline run 后自动执行交叉引用完整性检查。

### 3.1 问题（已解决）

当前 9 个 extractor 在 orchestrator 中分阶段执行（阶段 1 并行，阶段 2 并行，阶段 3 串行），抽取后由 `cross_entity_validator` 做交叉校验：
- metric_extractor 产出的 `dependsOn` 可能引用 term_extractor 尚未产出的术语
- term_extractor 的 `mapsToColumn` 可能引用不存在的物理列
- 无任何跨提取器引用完整性检查

### 3.2 方案

在 orchestrator 的 `_finalize_pipeline_run` 之前新增 `_validate_cross_entity_consistency` 阶段：

```python
async def _validate_cross_entity_consistency(
    db: Session,
    kb_id: int,
    all_triples: list[RawTriple],
) -> CrossEntityReport:
    """After all extractors complete, validate referential integrity."""
    
    # Build index from all triples
    iri_index = _build_iri_index(all_triples)
    
    violations = []
    
    # Rule 1: Every dependsOn target must be a declared entity
    for t in all_triples:
        if t.predicate.endswith("dependsOn") or t.predicate.endswith("derivedFrom"):
            if t.object_is_uri and t.object not in iri_index:
                violations.append(CrossEntityViolation(
                    source=t.subject,
                    predicate=t.predicate,
                    missing_target=t.object,
                    severity="warning",
                    fix_hint=f"Term or metric {t.object} not found in extraction results",
                ))
    
    # Rule 2: Every metricsOver dimension must exist
    for t in all_triples:
        if t.predicate.endswith("aggregatesOver"):
            if t.object_is_uri and t.object not in iri_index:
                violations.append(...)
    
    # Rule 3: Every mapsToColumn should have a corresponding PhysicalColumn
    # (lazy — resolved in stage2_entity_link of cleaner)
    
    # Rule 4: No orphan BusinessRule (appliesTo must exist)
    ...
    
    return CrossEntityReport(
        passed=len(violations) == 0,
        violations=violations,
        suggestion="Run extraction pipeline with full corpus to resolve missing references",
    )
```

### 3.3 实现步骤

1. 新增 `backend/services/extraction/cross_entity_validator.py`（~200 行）
2. 在 `orchestrator.py:_finalize_pipeline_run` 前调用
3. 违规写入 `pipeline_steps["cross_entity_validation"]`，前端「建模与质量」tab 可查看
4. 非阻断（severity=error 才阻断入图），warning 级记录供人工审查

---

## 四、P1 — TBox 增强 + SHACL 领域约束

### 4.1 补齐 `owl:Restriction`（class-level 约束）

当前 TBox 有 `disjointWith` 和 `FunctionalProperty`，但**零个 `owl:Restriction`**。应在 `core.ttl` 中补充：

```turtle
# P1.1 — Metric 必须有关联表
dl:Metric rdfs:subClassOf [
  owl:onProperty dl:computedFromTable ;
  owl:someValuesFrom dl:PhysicalTable
] .

# P1.2 — BusinessTerm 必须归属某个领域
dl:BusinessTerm rdfs:subClassOf [
  owl:onProperty dl:belongsToDomain ;
  owl:someValuesFrom dl:BusinessDomain
] .

# P1.3 — BusinessRule 必须指定 appliesTo
dl:BusinessRule rdfs:subClassOf [
  owl:onProperty dl:appliesTo ;
  owl:someValuesFrom dl:BusinessConcept
] .

# P1.4 — LineageAssertion 至少有一个 field
dl:LineageAssertion rdfs:subClassOf [
  owl:onProperty dl:sourceField ;
  owl:allValuesFrom xsd:string
] .

# P1.5 — PhysicalColumn 必须属于一个 PhysicalTable
dl:PhysicalColumn rdfs:subClassOf [
  owl:onProperty schema:isPartOf ;
  owl:someValuesFrom dl:PhysicalTable
] .

# P1.6 — DocumentChunk 必须属于一个 Document
dl:DocumentChunk rdfs:subClassOf [
  owl:onProperty dl:partOf ;
  owl:someValuesFrom dl:Document
] .
```

**实施方式：** 直接修改 `backend/ontology/tbox/core.ttl`，重启后 OWL 2 RL 推理机自动拾取。这些约束增强了推理能力——例如，如果一个个体没有 `computedFromTable`，推理机不会推断它是 Metric。

### 4.2 SHACL 领域约束（超越结构校验）

当前 SHACL shape 文件以**结构校验**为主（「必须有 prefLabel」「必须有 formula」）。应新增**领域级业务约束**：

```turtle
# metric.shacl.ttl 增强 — 指标公式可执行性检查
dl:MetricFormulaShape a sh:NodeShape ;
  sh:targetClass dl:Metric ;
  sh:property [
    sh:path dl:formula ;
    sh:minLength 3 ;
    sh:message "指标公式不能为空或过短"@zh ;
  ] ;
  sh:property [
    sh:path dl:confidence ;
    sh:minInclusive 0 ;
    sh:maxInclusive 100 ;
    sh:message "置信度必须在 0-100 之间"@zh ;
  ] .
```

新增 `business_rule.shacl.ttl` 增强：

```turtle
# 规则类型必须在枚举值内（已更新为 shacl_constraint|owl_axiom|swrl_rule|business_rule）
dl:RuleTypeShape a sh:NodeShape ;
  sh:targetClass dl:BusinessRule ;
  sh:property [
    sh:path dl:ruleType ;
    sh:in ("shacl_constraint" "owl_axiom" "swrl_rule" "business_rule") ;
    sh:message "ruleType 必须是 shacl_constraint/owl_axiom/swrl_rule/business_rule 之一"@zh ;
  ] .
```

### 4.3 DatatypeProperty domain/range 声明

```turtle
# core.ttl 中补充
dl:formula rdfs:domain dl:Metric ;
           rdfs:range xsd:string .

dl:caliber rdfs:domain dl:Metric ;
           rdfs:range xsd:string .

dl:confidence rdfs:domain dl:BusinessConcept ;
              rdfs:range xsd:decimal .
```

当前 DataLens 未声明任何 DatatypeProperty 的 `rdfs:domain` 和 `rdfs:range`。这虽不影响推理，但影响本体的**可读性**和**工具互操作性**（Protégé 等工具依赖此信息做 UI 提示）。

---

## 五、P2 — 规则标准化 + 术语等价 + 层级增强

### 5.1 规则格式标准化（SWRL / DL-Safe）

当前 `inference.rules` 使用自定义 Datalog 格式：

```
[transitive-derivedFrom] (?a dl:derivedFrom ?b) (?b dl:derivedFrom ?c) -> (?a dl:derivedFrom ?c)
```

**优化：** 在保留 reasoner.py 当前执行引擎的同时，新增标准 SWRL 语法支持：

```xml
<!-- inference.swrl -->
<ruleml:imp>
  <ruleml:_body>
    <swrlx:classAtom>
      <owlx:Class IRI="dl:Metric"/>
      <ruleml:var>x</ruleml:var>
    </swrlx:classAtom>
    <swrlx:individualPropertyAtom swrlx:property="dl:computedFromTable">
      <ruleml:var>x</ruleml:var>
      <ruleml:var>t</ruleml:var>
    </swrlx:individualPropertyAtom>
  </ruleml:_body>
  <ruleml:_head>
    <swrlx:individualPropertyAtom swrlx:property="dl:dependsOn">
      <ruleml:var>x</ruleml:var>
      <ruleml:var>t</ruleml:var>
    </swrlx:individualPropertyAtom>
  </ruleml:_head>
</ruleml:imp>
```

**实施方式：**
1. 选取 3–5 条最有价值的推理规则（派生链传递、新增 VIP 识别、维度自动聚合）
2. 在 `backend/ontology/rules/` 下新增 `inference.swrl`
3. reasoner.py 新增 `load_swrl_rules()` 方法，解析为内部规则格式
4. 管线：写入 ABox → SHACL 校验 → SWRL 规则执行 → 写入推理图

### 5.2 术语等价关系填充

当前 term_extractor 能提取 `synonyms`（存为 `skos:altLabel`），但缺少跨知识库的**等价术语识别**：

**方案：** 在 relation_extractor 之后新增 `_resolve_cross_kb_equivalences`：

```python
async def _resolve_cross_kb_equivalences(
    db: Session,
    kb_id: int,
    new_terms: list[RawTriple],
) -> list[RawTriple]:
    """Use SBERT to find skos:exactMatch across knowledge bases."""
    new_labels = {t.object: t.subject for t in new_terms if t.predicate == SKOS_PREF}
    existing = _load_all_terms_from_domain(db, domain_id)
    
    for label, iri in new_labels.items():
        # SBERT cosine similarity against existing term labels
        matches = _sbert_match(label, existing, threshold=0.92)
        for match_iri, score in matches:
            triples.append(RawTriple(
                iri, SKOS_EXACT_MATCH, match_iri, True,
                confidence=score * 100,
                graph=graph,
            ))
    
    return equivalence_triples
```

### 5.3 层级构建增强

`hierarchy_builder.py` 当前 122 行仅依赖 LLM `parent_concept` 字段。应增强：

```python
class HierarchyBuilder:
    def build(self, triples: list[RawTriple]) -> list[RawTriple]:
        hierarchy = []
        
        # 1. Collect parent_concept from term extraction
        parents = self._collect_parent_refs(triples)
        
        # 2. Cycle detection via DFS
        cycles = self._detect_cycles(parents)
        if cycles:
            self._quarantine_cycles(cycles)
            self._log_warning(f"Detected {len(cycles)} cycles in hierarchy")
        
        # 3. Depth enforcement (max 6 levels, per SHACL)
        deep_paths = self._find_deep_paths(parents, max_depth=6)
        for path in deep_paths:
            self._log_warning(f"Hierarchy depth exceeds 6: {' → '.join(path)}")
        
        # 4. Generate broader/narrower triples
        for child, parent in parents.items():
            if (child, parent) not in cycles:
                hierarchy.append(RawTriple(child, SKOS_BROADER, parent, True))
                hierarchy.append(RawTriple(parent, SKOS_NARROWER, child, True))
        
        return hierarchy
```

---

## 六、P3 — 可视化 + 本体演化 + 跨领域对齐

### 6.1 知识图谱可视化增强

当前 `RelationGraph.tsx`：50 节点硬上限 + 基本力导向布局。

**增强计划：**

| 能力 | 实现方式 |
|------|----------|
| 层级视图 | 用 Tree 组件展示 `skos:broader/narrower` 树，替代纯图 |
| 血缘追踪 DAG | 用 Dagre + D3 展示 `transformsFrom` 链 |
| 节点过滤/搜索 | 按实体类型、置信度、审批状态筛选 |
| 导出 | SVG/PNG 导出；Turtle/SPARQL 结果导出 |
| 大图性能 | > 500 节点时的虚拟化渲染（WebGL / Canvas） |

**实施：** 拆分为 3 个子组件：

```
components/ontology/
├── RelationGraph.tsx        → 保留（概念关系力导向图）
├── HierarchyTree.tsx        → 新增（SKOS 层级树）
├── LineageDagView.tsx       → 复用 datasource/LineageDagView.tsx
└── OntologyExport.tsx       → 新增（导出工具栏）
```

### 6.2 本体演化管理接入

当前 `writer.py:write_with_version()` 和 `deprecate_entity()` 已实现但 orchestrator 未调用。

**接入方案：**

```python
# orchestrator.py: 在 SHACL 校验通过后
if existing_entity := _find_existing_entity(db, new_triple.subject):
    if _has_semantic_change(existing_entity, new_triple):
        writer.write_with_version(
            entity_iri=new_triple.subject,
            triples=[new_triple],
            change_note=_generate_change_note(existing_entity, new_triple),
        )
    else:
        writer.update_entity(new_triple)
else:
    writer.create_entity(new_triple)
```

**记录信息：**
- `dl:version` → 版本号（日期时间戳）
- `dl:changeNote` → 变更说明（LLM 生成的 diff 摘要）
- `dl:deprecated` → 旧版本标记（`owl:deprecated true`）
- `prov:wasRevisionOf` → 指向前一版本

### 6.3 跨领域本体对齐

当前 `belongsToDomain` 提供了领域归属，但缺少**跨域概念映射**。

```turtle
# 交易域的「订单金额」和财务域的「收入确认金额」可能是同一概念
ex:trade/order_amount  skos:exactMatch  ex:finance/revenue_amount .
ex:trade/order_amount  skos:closeMatch  ex:marketing/gmv .
```

**方案：** 利用已有的 SBERT 消歧基础设施（`stage2a_entity_disambiguate`），扩展为跨域等价检测：

```python
async def suggest_cross_domain_mappings(
    db: Session,
    source_domain_id: int,
) -> list[CrossDomainMapping]:
    """Identify potential skos:exactMatch / skos:closeMatch across domains."""
    source_terms = db.query(BusinessTerm).filter_by(domain_id=source_domain_id).all()
    other_terms = db.query(BusinessTerm).filter(BusinessTerm.domain_id != source_domain_id).all()
    
    matches = []
    for st in source_terms:
        # SBERT cosine similarity against other domain terms
        candidates = _sbert_cross_domain_match(st, other_terms, threshold=0.88)
        matches.extend(candidates)
    
    return matches
```

---

## 七、实施阶段总览

| 阶段 | 优先级 | 内容 | 预计工期 | 依赖 |
|------|--------|------|----------|------|
| Phase 0 | **P0** | 交叉一致性校验 | 3 天 | ✅ 已完成（`cross_entity_validator.py`） |
| Phase 1 | **P1** | TBox `owl:Restriction` 补充 | 1 天 | 无 |
| Phase 1 | **P1** | DatatypeProperty domain/range | 0.5 天 | 无 |
| Phase 1 | **P1** | SHACL 领域约束增强 | 2 天 | 无 |
| Phase 2 | **P2** | SWRL 规则标准化 | 3 天 | Phase 1 |
| Phase 2 | **P2** | 术语等价关系填充 | 2 天 | Phase 1 |
| Phase 2 | **P2** | 层级构建增强 | 2 天 | 无 |
| Phase 3 | **P3** | 可视化增强（三组件拆分） | 5 天 | 无 |
| Phase 3 | **P3** | 本体演化管理接入 | 2 天 | Phase 1 |
| Phase 3 | **P3** | 跨领域本体对齐 | 3 天 | Phase 2 术语等价 |

---

## 八、验收标准

| 阶段 | 验收条件 |
|------|----------|
| P0 | `cross_entity_validator` 在每次 pipeline run 后自动执行；违规在前端「建模与质量」tab 可见 |
| P1 | `core.ttl` 新增 ≥6 条 `owl:Restriction`；DatatypeProperty 全部声明 domain/range；新增 ≥3 个领域级 SHACL shape |
| P2 | ≥3 条 SWRL 规则可被 reasoner.py 解析并执行；跨 KB 等价术语自动建议（置信度 > 0.88）；层级循环检测覆盖 |
| P3 | 关系图 + 层级树 + 血缘图三视图；TBox 变更自动版本记录；跨域映射建议 |

---

## 参考

- [本体建模理论标准](./本体建模理论标准.md)
- [本体驱动重构方案](./本体驱动重构方案.md)
- [本体三层架构与 UI 优化](./本体三层架构与UI优化.md)
- W3C OWL 2 RL Profile: https://www.w3.org/TR/owl2-profiles/#OWL_2_RL
- W3C SHACL: https://www.w3.org/TR/shacl/
- Noy & McGuinness (2001). Ontology Development 101. Stanford KSL.
