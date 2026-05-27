# 业务域知识：零售供应链（本体抽取示例）

> 本文演示如何从企业真实文档中识别「概念实体、关系、规则、属性、词汇」五类本体要素。
> 每个章节标注了对应的 TBox 类和 Object/Datatype Property，便于导入 DataLens 时映射。

---

## 1. 域内核心对象与物理表

| 业务对象 | 物理表 | TBox 类 | 说明 |
|----------|--------|---------|------|
| 商品主数据 | `scm.product` | `dl:PhysicalTable` | SKU 粒度，含品类、品牌、规格 |
| 供应商主数据 | `scm.supplier` | `dl:PhysicalTable` | 供应商编码、等级、合作状态 |
| 采购订单 | `scm.purchase_order` | `dl:PhysicalTable` | 一次采购一张单，含供应商、金额、状态 |
| 采购明细 | `scm.purchase_order_line` | `dl:PhysicalTable` | 订单行项，SKU + 数量 + 单价 |
| 入库记录 | `scm.inbound_receipt` | `dl:PhysicalTable` | 仓库收货确认，关联 PO |
| 库存快照 | `scm.inventory_snapshot` | `dl:PhysicalTable` | 每日零点库存，SKU + 仓库 + 批次 |
| 出库记录 | `scm.outbound_delivery` | `dl:PhysicalTable` | 向门店/客户发货 |
| 门店主数据 | `scm.store` | `dl:PhysicalTable` | 门店编码、类型、城市、面积 |
| 销售订单 | `trade.order_header` | `dl:PhysicalTable` | 交易域订单头 |
| 销售明细 | `trade.order_line` | `dl:PhysicalTable` | 交易域订单行项 |

> **关系提示**：`scm` schema 是供应链域，`trade` schema 是交易域——这是典型的跨域依赖。

---

## 2. 概念实体（Terms, Metrics, Dimensions）

### 2.1 业务术语 (`dl:BusinessTerm`)

| 术语 ID | 首选标签 | 别名 (altLabel) | 语义类型 (`dl:termType`) | 映射物理列 (`dl:mapsToColumn`) |
|---------|----------|-----------------|--------------------------|-------------------------------|
| term.sku | SKU / 商品编码 | 货号、产品编码 | dimension | scm.product.sku_code |
| term.supplier_code | 供应商编码 | 供方编码、vendor_code | dimension | scm.supplier.supplier_code |
| term.store_code | 门店编码 | 店铺编码、POS 门店号 | dimension | scm.store.store_code |
| term.po_status | 采购单状态 | PO 状态 | enum | scm.purchase_order.status |
| term.inventory_qty | 库存数量 | 在库量、可用库存 | metric | scm.inventory_snapshot.on_hand_qty |
| term.unit_price | 采购单价 | 进价、不含税单价 | metric | scm.purchase_order_line.unit_price |
| term.sales_amt | 销售金额 | 实付金额、GMV | metric | trade.order_header.paid_amount |

### 2.2 指标定义 (`dl:Metric`)

| 指标 | 公式 (`dl:formula`) | 口径 (`dl:caliber`) | 来源表 (`dl:computedFromTable`) | 派生自 (`dl:derivedFrom`) |
|------|---------------------|---------------------|-------------------------------|---------------------------|
| metric.daily_gmv | SUM(paid_amount) | 实付金额，含运费不含退款；时间窗口：自然日 | trade.order_header | — |
| metric.inventory_turnover_days | avg(on_hand_qty) / SUM(outbound_qty) * 30 | 月度平均库存 / 月出库量 × 30；按 SKU + 仓库核算 | inventory_snapshot, outbound_delivery | — |
| metric.fill_rate | COUNT(行项 received_qty >= ordered_qty) / COUNT(总行项) | 按时足量交付的 PO 行项占比；时间窗口：自然月 | purchase_order_line, inbound_receipt | — |
| metric.gross_margin_rate | (SUM(paid_amount) - SUM(cost_amt)) / SUM(paid_amount) | 毛利率；cost_amt 取采购加权平均成本 | trade.order_line, scm.purchase_order_line | metric.daily_gmv |
| metric.avg_order_value | SUM(paid_amount) / COUNT(DISTINCT order_id) | 客单价 = GMV / 订单数 | trade.order_header | metric.daily_gmv |

### 2.3 分析维度 (`dl:Dimension`)

| 维度 | 维度类型 (`dl:dimensionType`) | 层级 | 绑定表/列 |
|------|------------------------------|------|-----------|
| dim.time_day | time | 日 → 周 → 月 → 季 → 年 | 各表的 biz_date / created_at |
| dim.geo_city | geo | 城市 → 省份 → 大区 → 全国 | scm.store.city, scm.store.province |
| dim.category | category | SKU → 子类 → 大类 → 品类 | scm.product.category_path |
| dim.supplier_level | category | 供应商等级 S/A/B/C/D | scm.supplier.level |
| dim.store_type | category | 门店类型 旗舰店/标准店/社区店 | scm.store.store_type |

---

## 3. 关系 (`ObjectProperty`)

### 3.1 表间 JOIN 关系 (`dl:joinableWith`)

```
scm.purchase_order  ──[left: po_id, right: po_id, type: inner]──  scm.purchase_order_line
scm.purchase_order  ──[left: supplier_code, right: supplier_code, type: left]──  scm.supplier
scm.purchase_order_line ──[left: sku_code, right: sku_code, type: inner]──  scm.product
scm.inbound_receipt ──[left: po_id, right: po_id, type: left]──  scm.purchase_order
scm.inventory_snapshot ──[left: sku_code, right: sku_code, type: inner]──  scm.product
scm.outbound_delivery ──[left: store_code, right: store_code, type: left]──  scm.store
trade.order_line ──[left: sku_code, right: sku_code, type: left]──  scm.product
trade.order_header ──[left: order_id, right: order_id, type: inner]──  trade.order_line
```

> **跨域 JOIN**：`trade.order_line → scm.product`，需要企业层 `concept_id` 对齐 `sku_code`。

### 3.2 数据血缘 (`dl:transformsFrom`)

```
ODS.erp_purchase_order ──[transformsFrom]── DWD.fact_purchase_order
ODS.wms_inbound        ──[transformsFrom]── DWD.fact_inbound
DWD.fact_purchase_order ──[transformsFrom]── DWS.agg_supplier_performance
DWD.fact_inbound       ──[transformsFrom]── DWS.agg_supplier_performance
DWS.agg_supplier_performance ──[transformsFrom]── ADS.supplier_dashboard
```

### 3.3 指标派生链 (`dl:derivedFrom`)

```
metric.gross_margin_rate ──[derivedFrom]── metric.daily_gmv
metric.avg_order_value  ──[derivedFrom]── metric.daily_gmv
metric.inventory_turnover_days ──[dependsOn]── term.inventory_qty
```

### 3.4 术语依赖 (`dl:dependsOn`)

```
term.inventory_qty ──[dependsOn]── term.sku
term.sales_amt     ──[dependsOn]── term.store_code
term.fill_rate     ──[dependsOn]── term.po_status
```

---

## 4. 业务规则 (`dl:BusinessRule`)

### 4.1 校验规则 (`ruleType: validation`)

| 规则 | 表达式 (`dl:ruleExpression`) | 所属域 | 置信度 |
|------|------------------------------|--------|--------|
| rule.po_amount_positive | `purchase_order.total_amount > 0` | 供应链 | 100 |
| rule.inventory_non_negative | `inventory_snapshot.on_hand_qty >= 0` | 供应链 | 100 |
| rule.order_has_lines | `order_header.order_id EXISTS IN order_line.order_id` | 交易 | 95 |
| rule.sku_unique_per_supplier | `(supplier_code, sku_code) UNIQUE IN product` | 供应链 | 90 |

### 4.2 派生规则 (`ruleType: derivation`)

| 规则 | 表达式 | 说明 |
|------|--------|------|
| rule.cost_amt_calc | `cost_amt = ordered_qty × unit_price` | 采购行金额 = 数量 × 单价 |
| rule.gross_margin_calc | `gross_margin = (paid_amount - cost_amt) / paid_amount` | 毛利率计算 |
| rule.days_sales_outstanding | `DSO = avg(AR_balance) / daily_avg_revenue` | 应收账款周转天数 |

### 4.3 约束规则 (`ruleType: constraint`)

| 规则 | 表达式 | 说明 |
|------|--------|------|
| rule.po_status_flow | `status: draft → submitted → approved → received → closed` | PO 状态机 |
| rule.inventory_reserved | `reserved_qty ≤ on_hand_qty` | 预留库存不超在库量 |
| rule.supplier_active_only | `supplier.status = 'active' 方可创建 PO` | 仅活跃供应商可下单 |

---

## 5. 属性 (`DatatypeProperty`)

### 5.1 物理表属性

| 表 | 敏感等级 (`dl:sensitivityLevel`) | 行数 (`dl:rowCount`) | 业务摘要 (`dl:businessSummary`) |
|----|----------------------------------|---------------------|--------------------------------|
| scm.product | internal | 250,000 | 商品主数据，含 SKU、品类树、品牌、规格 |
| scm.supplier | confidential | 8,500 | 供应商编码、等级、结算方式、合同信息 |
| scm.purchase_order | internal | 1,200,000 | 采购订单，含供应商、金额、状态、审批人 |
| scm.inventory_snapshot | confidential | 30,000,000 | 每日零点库存快照，SKU+仓库+批次粒度 |
| trade.order_header | restricted | 50,000,000 | 销售订单头，含用户、金额、时间、渠道 |

### 5.2 指标属性

| 指标 | 审批状态 (`dl:approvalStatus`) | 置信度 (`dl:confidence`) | 最新版本 |
|------|-------------------------------|--------------------------|---------|
| metric.daily_gmv | approved | 100 | v2.1 (2026-03-15) |
| metric.gross_margin_rate | approved | 95 | v1.0 (2026-01-10) |
| metric.inventory_turnover_days | pending_review | 80 | v0.9 (2026-05-20) |
| metric.fill_rate | draft | 60 | v0.5 (2026-05-25) |

---

## 6. 词汇对齐 (`skos:ConceptScheme` + `concept_id`)

### 6.1 跨系统同义词映射

| concept_id | 首选标签 | 别名 (altLabel) | 来源系统 | 对齐关系 (`skos:exactMatch`) |
|------------|----------|-----------------|----------|------------------------------|
| product.sku | SKU 编码 | 货号、商品 ID、item_id、product_code | scm(货号) / trade(商品ID) / WMS(item_id) | skos:exactMatch {wms.item_id, trade.product_code} |
| order.purchase | 采购订单号 | PO号、采购单号、purchase_order_no | scm(PO号) / ERP(采购单号) | skos:exactMatch {erp.purchase_order_no} |
| org.store | 门店编码 | 店铺编码、POS 门店号、零售门店 | scm(门店编码) / trade(店铺编码) / POS(POS门店号) | skos:exactMatch {trade.store_code, pos.retailer_id} |
| finance.cost_price | 采购成本价 | 进价、加权成本、移动平均成本 | scm(unit_price) / finance(加权成本) | skos:closeMatch {finance.moving_avg_cost} |
| customer.order_id | 销售订单号 | 订单号、交易单号 | trade(order_id) / CRM(receipt_no) | skos:exactMatch {crm.receipt_no} |

### 6.2 度量单位对齐

| 概念 | 单位 | 跨域差异 |
|------|------|---------|
| metric.inventory_qty | 件 / 箱 / 托盘 | WMS 用"箱"，scm 用"件"；需在跨域查询时指定换算系数（1 箱 = 12 件） |
| metric.order_amount | 元（CNY） | 统一为人民币元，外币订单在 ODS 层完成汇率换算 |

### 6.3 枚举值对齐

| 概念 | 域内值 | 跨域等价值 | 域 |
|------|--------|-----------|-----|
| po.status = 'received' | 已收货 | inbound.status = 'done' | scm.po ↔ scm.inbound |
| order.status = 'paid' | 已支付 | payment.status = 'success' | trade.order ↔ fin.payment |
| supplier.level = 'A' | A 级供应商 | supplier.rating >= 90 | scm ↔ ERP |

---

## 7. 常见陷阱（验证模型是否正确理解语义）

1. **"库存金额"有两种口径**：
   - 财务口径：`on_hand_qty × 加权移动平均成本`（来自 finance）
   - 业务口径：`on_hand_qty × 最近一次采购价`（来自 scm）
   - 两个口径可能差异显著，问"库存金额"时必须明确是财务口径还是业务口径。

2. **"交付率"容易双计**：
   - `fill_rate` 按 PO 行项计算，一笔采购订单的多个行项独立评价
   - 若有人问"按供应商的交付率"，需先按 PO 行项算 fill_rate，再按供应商聚合 average，不是直接 count 行项

3. **跨域 GMV 对齐**：
   - 交易域的 `daily_gmv = SUM(paid_amount)` 含运费
   - 财务域的 `net_revenue = SUM(paid_amount - freight - refund)`
   - 两个概念不能直接用 `skos:exactMatch`，应该是 `skos:closeMatch`

4. **时间维度口径差异**：
   - 采购域用 `biz_date`（业务归属日）
   - 交易域用 `created_at`（系统时间戳）
   - 跨域分析时需先对齐时间维度

---

## 附录：从本文档可抽取的本体要素统计

| 本体要素 | TBox 类 | 数量 |
|----------|---------|------|
| 物理表 | `dl:PhysicalTable` | 10 |
| 业务术语 | `dl:BusinessTerm` | 7 |
| 指标 | `dl:Metric` | 5 |
| 维度 | `dl:Dimension` | 5 |
| JOIN 关系 | `dl:JoinRelation` | 8 |
| 血缘关系 | `dl:LineageAssertion` | 5 |
| 业务规则 | `dl:BusinessRule` | 9 |
| 跨域词汇对齐 | `skos:exactMatch` / `skos:closeMatch` | 7 |
