# DataLens 制造业演示测试方案

> 本文档为 DataLens ChatBI 产品的全方位路演测试方案，基于**高端电子制造/半导体**垂直领域构建生产级仿真数据。  
> 用途：投资人路演、产品能力对标、售前 PoC。  
> **自动化方式**：除数据生成脚本外，全部浏览器操作通过 **Playwright** 自动化执行，一键回放、效果一致，适合反复彩排。

---

## 目录

1. [测试目标](#1-测试目标)
2. [场景设定：模拟企业](#2-场景设定模拟企业)
3. [技术环境](#3-技术环境)
4. [测试数据总览](#4-测试数据总览)
5. [测试场景与用例](#5-测试场景与用例)
6. [执行计划](#6-执行计划)
7. [你需要准备的](#7-你需要准备的)
8. [成功标准](#8-成功标准)
9. [附录](#9-附录)

---

## 1. 测试目标

| 维度 | 目标 |
|------|------|
| **核心功能** | 验证 ChatBI 全链路：数据源接入 → 表分析 → 知识库注入 → 自然语言问答 |
| **复杂查询** | 多表 JOIN、聚合、条件过滤、时间窗口、口径正确性 |
| **RAG 效果** | 知识库对业务术语/口径/SQL 优化的提升作用 |
| **边界能力** | 模糊问法、长文本、多条件、口径矛盾检测 |
| **演示效果** | 流畅的用户体验，展示制造业真实场景，让投资人直观感受价值 |

---

## 2. 场景设定：模拟企业

**企业名称**：华芯半导体集成制造有限公司 (Huaxin Semiconductor Manufacturing Co., Ltd.)

**企业简介**：一家中型 Fabless+Fab 混合模式的高端电子制造企业，主营：
- 车规级 MCU 芯片设计 & 封装测试
- 消费电子 SoC 晶圆代工（28nm/45nm 工艺）
- 传感器模组（MEMS）批量生产

**年度规模**：
- 年营收约 **￥28.5 亿**
- 产线 **12 条**（晶圆前道 5 条 + 封装后道 7 条）
- 员工 **3,200+** 人
- 客户 **150+** 家（包括 Tier1 汽车零部件厂商、消费电子品牌商）
- 供应商 **400+** 家
- 月产晶圆约 **1.2 万片**（等效 8 英寸）

---

## 3. 技术环境

### 3.1 本地运行架构

```
┌───────────────────────────────────────────────────┐
│                  本地开发机 (Mac)                    │
│                                                       │
│  ┌────────────┐    ┌────────────┐    ┌──────────┐   │
│  │ PostgreSQL │◄──►│  Backend   │◄──►│ Frontend │   │
│  │  (主存储)   │    │  FastAPI   │    │  Next.js │   │
│  │  +pgvector  │    │  :8000     │    │  :3000   │   │
│  └────────────┘    └─────┬──────┘    └──────────┘   │
│                          │                           │
│                 ┌────────▼────────┐                  │
│                 │  MySQL (测试数据源) │                  │
│                 │  :3306           │                  │
│                 └─────────────────┘                  │
└───────────────────────────────────────────────────┘
```

### 3.2 软件需求

| 组件 | 版本要求 | 用途 |
|------|---------|------|
| PostgreSQL | 15+ | DataLens 主存储（元数据、向量、知识库） |
| pgvector | 0.5+ | 向量嵌入支持 |
| MySQL | 8.0+ | 模拟制造业业务数据库（演示的数据源） |
| Python | 3.11+ | 后端运行 + 数据生成脚本 |
| Node.js | 18+ | 前端运行 |

### 3.3 硬件需求

| 资源 | 最低要求 | 推荐 |
|------|---------|------|
| CPU | 4 核 | 8 核+ |
| 内存 | 8 GB | 16 GB+ |
| 磁盘 | 20 GB | 50 GB+ |
| 网络 | 无（纯本地） | 纯本地 |

---

## 4. 测试数据总览

### 4.1 数据库：`manufacturing_demo`

一个数据库，**9 张表**，覆盖制造业四大主题域：

```
manufacturing_demo  (MySQL 8.0)
│
├── ██ 生产制造域 ██
│   ├── wip_lots             晶圆批次在制品 (50,000 行)
│   ├── production_orders    工单 (20,000 行)
│   ├── equipment_metrics    设备运行指标 (300,000 行)
│   └── quality_inspections   质量检验记录 (80,000 行)
│
├── ██ 供应链域 ██
│   ├── suppliers             供应商主数据 (400 行)
│   └── purchase_orders       采购订单 (30,000 行)
│
├── ██ 财务成本域 ██
│   └── cost_transactions     成本交易明细 (100,000 行)
│
├── ██ 客户与销售域 ██
│   ├── customers             客户主数据 (150 行)
│   └── sales_orders          销售订单 (25,000 行)
```

### 4.2 各表详情

#### 4.2.1 wip_lots（在制晶圆批次）

跟踪每一批晶圆在生产线的流转状态。

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| lot_id | BIGINT PK | 批次唯一号 | 1000001 |
| lot_code | VARCHAR(32) | 批次编码 | WLP-20260420-A001 |
| product_code | VARCHAR(32) | 产品型号 | MCU-C2003-QFN |
| route_code | VARCHAR(32) | 工艺流程路线 | ROUTE_C2003_A |
| current_stage | VARCHAR(32) | 当前工序 | STAGE_ETCH_01 |
| stage_seq | INT | 工序序号 | 15 |
| total_stages | INT | 总工序数 | 28 |
| qty_input | INT | 投入晶圆数 | 25 |
| qty_output | INT | 产出晶圆数 | 23 |
| qty_hold | INT | 挂起数 | 0 |
| qty_scrap | INT | 报废数 | 2 |
| lot_status | VARCHAR(16) | 批次状态 | active / hold / completed / scrapped |
| fab_id | VARCHAR(8) | 产线编号 | FAB_A01 |
| operator | VARCHAR(32) | 当前负责操作员 | ZHANG_WEI |
| start_time | DATETIME | 投产时间 | 2026-04-20 08:30:00 |
| est_end_time | DATETIME | 预计完工时间 | 2026-04-28 14:00:00 |
| actual_end_time | DATETIME | 实际完工时间 | NULL |
| updated_at | DATETIME | 最后更新时间 | 2026-04-25 10:15:00 |

#### 4.2.2 production_orders（工单）

每个工单是一次生产指令。

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| order_id | BIGINT PK | 工单号 | 5000001 |
| order_code | VARCHAR(32) | 工单编号 | PO-202604-00001 |
| product_code | VARCHAR(32) | 产品型号 | MCU-C2003-QFN |
| order_qty | INT | 计划数量 | 1000 |
| completed_qty | INT | 已完成数量 | 850 |
| defect_qty | INT | 缺陷数量 | 12 |
| rework_qty | INT | 返工数量 | 5 |
| order_type | VARCHAR(16) | 工单类型 | normal / pilot / rework |
| priority | VARCHAR(8) | 优先级 | P1 / P2 / P3 |
| plan_start | DATETIME | 计划开始 | 2026-04-10 |
| plan_end | DATETIME | 计划结束 | 2026-04-20 |
| actual_start | DATETIME | 实际开始 | 2026-04-10 08:00 |
| actual_end | DATETIME | 实际结束 | NULL |
| status | VARCHAR(16) | 工单状态 | pending / running / completed / delayed / cancelled |
| cost_center | VARCHAR(16) | 成本中心 | CC_FAB_A_01 |
| created_by | VARCHAR(32) | 创建人 | WANG_MING |
| created_at | DATETIME | 创建时间 | 2026-04-08 |
| notes | TEXT | 备注 | — |

#### 4.2.3 equipment_metrics（设备运行指标）

设备每小时的运行数据采集。

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| metric_id | BIGINT PK | 记录ID | 10000001 |
| equipment_code | VARCHAR(32) | 设备编号 | ETCH_001 |
| equipment_type | VARCHAR(32) | 设备类型 | etcher / lithography / deposition / cmp / test |
| fab_id | VARCHAR(8) | 所属产线 | FAB_A01 |
| collect_time | DATETIME | 采集时间 | 2026-04-25 10:00:00 |
| status | VARCHAR(16) | 设备状态 | running / idle / maintenance / downtime / setup |
| temperature | DECIMAL(5,2) | 腔体温度(℃) | 150.25 |
| pressure | DECIMAL(6,2) | 腔体压力(mTorr) | 25.50 |
| power | DECIMAL(8,2) | 射频功率(W) | 850.00 |
| gas_flow | DECIMAL(8,2) | 气体流量(sccm) | 120.00 |
| vibration | DECIMAL(4,2) | 振动值(mm/s) | 1.25 |
| oee_percent | DECIMAL(5,2) | OEE 百分比 | 87.50 |
| throughput | INT | 本时产出 | 45 |
| downtime_minutes | INT | 本时停机分钟 | 0 |
| operator | VARCHAR(32) | 操作员 | LI_QIANG |
| notes | VARCHAR(256) | 备注 | — |

#### 4.2.4 quality_inspections（质量检验）

每批次的检验记录（含良率数据）。

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| inspect_id | BIGINT PK | 检验ID | 2000001 |
| lot_id | BIGINT FK | 关联批次 | 1000001 |
| inspect_stage | VARCHAR(32) | 检验工序 | INSPECT_AFTER_ETCH |
| sample_size | INT | 抽样数 | 10 |
| pass_qty | INT | 通过数 | 9 |
| fail_qty | INT | 失效数 | 1 |
| defect_type | VARCHAR(32) | 缺陷类型 | particle / scratch / thickness_err / electrical / none |
| defect_detail | VARCHAR(256) | 缺陷描述 | Particle contamination at edge |
| yield_rate | DECIMAL(5,2) | 良率(%) | 90.00 |
| inspector | VARCHAR(32) | 检验员 | ZHAO_LIN |
| inspect_time | DATETIME | 检验时间 | 2026-04-25 10:30:00 |
| is_final | TINYINT(1) | 是否终检 | 0 |

#### 4.2.5 suppliers（供应商主数据）

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| supplier_id | INT PK | 供应商ID | 5001 |
| supplier_code | VARCHAR(16) | 供应商编码 | S_WEILI |
| supplier_name | VARCHAR(64) | 供应商名称 | 微利电子材料有限公司 |
| category | VARCHAR(32) | 供应品类 | Silicon Wafer / Photoresist / Gas / Parts / Packaging |
| tier | VARCHAR(8) | 等级 | A / B / C |
| province | VARCHAR(16) | 省份 | 上海 |
| city | VARCHAR(16) | 城市 | 上海 |
| contact_person | VARCHAR(32) | 联系人 | 陈立 |
| contact_phone | VARCHAR(16) | 联系电话 | 138****6789 |
| coop_start | DATE | 合作起始 | 2022-03-15 |
| status | VARCHAR(8) | 状态 | active / suspended / terminated |
| last_audit_score | DECIMAL(4,2) | 最近审核分 | 92.50 |

#### 4.2.6 purchase_orders（采购订单）

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| po_id | BIGINT PK | 采购单ID | 3000001 |
| po_code | VARCHAR(32) | 采购单号 | PO-2026-04-00001 |
| supplier_id | INT FK | 供应商ID | 5001 |
| material_code | VARCHAR(32) | 物料编码 | SW-8INCH-P100 |
| material_name | VARCHAR(64) | 物料名称 | 8英寸抛光硅片 |
| category | VARCHAR(32) | 品类 | Silicon Wafer |
| unit_price | DECIMAL(10,2) | 单价 | 850.00 |
| order_qty | DECIMAL(10,2) | 采购数量 | 1000 |
| received_qty | DECIMAL(10,2) | 已收货数量 | 750 |
| defect_qty | DECIMAL(10,2) | 来料不良数 | 3 |
| total_amount | DECIMAL(12,2) | 总金额 | 850000.00 |
| order_date | DATE | 下单日期 | 2026-04-01 |
| expected_date | DATE | 预计到货 | 2026-04-15 |
| actual_receive_date | DATE | 实际到货 | 2026-04-16 |
| payment_terms | VARCHAR(32) | 付款条件 | Net 60 |
| status | VARCHAR(16) | 状态 | pending / partial / received / closed / cancelled |
| purchaser | VARCHAR(32) | 采购员 | LIU_FANG |

#### 4.2.7 cost_transactions（成本交易明细）

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| txn_id | BIGINT PK | 交易ID | 4000001 |
| cost_center | VARCHAR(16) | 成本中心 | CC_FAB_A_01 |
| product_code | VARCHAR(32) | 产品型号 | MCU-C2003-QFN |
| txn_date | DATE | 交易日期 | 2026-04-25 |
| cost_category | VARCHAR(32) | 成本类别 | material / labor / depreciation / utilities / maintenance |
| amount | DECIMAL(12,2) | 金额 | 125000.00 |
| currency | VARCHAR(8) | 币种 | CNY |
| source_type | VARCHAR(16) | 来源 | po_allocation / labor_actual / depreciation_schedule |
| reference_id | VARCHAR(32) | 参考单据 | PO-2026-04-00001 |
| description | VARCHAR(256) | 描述 | Silicon wafer material cost allocation |
| created_at | DATETIME | 创建时间 | 2026-04-25 18:00:00 |

#### 4.2.8 customers（客户主数据）

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| customer_id | INT PK | 客户ID | 8001 |
| customer_code | VARCHAR(16) | 客户编码 | C_BYD_AUTO |
| customer_name | VARCHAR(64) | 客户名称 | 比亚迪汽车工业有限公司 |
| industry | VARCHAR(32) | 客户行业 | Automotive / ConsumerElectronics / Industrial / Medical |
| province | VARCHAR(16) | 省份 | 广东 |
| city | VARCHAR(16) | 城市 | 深圳 |
| credit_rating | VARCHAR(8) | 信用评级 | AA / A / B / C |
| sales_person | VARCHAR(32) | 负责销售 | ZHOU_JIE |
| coop_start | DATE | 合作起始 | 2021-06-01 |
| status | VARCHAR(8) | 状态 | active / suspended / lost |

#### 4.2.9 sales_orders（销售订单）

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| order_id | BIGINT PK | 订单号 | 7000001 |
| order_code | VARCHAR(32) | 订单编号 | SO-2026-04-00001 |
| customer_id | INT FK | 客户ID | 8001 |
| product_code | VARCHAR(32) | 产品型号 | MCU-C2003-QFN |
| order_qty | INT | 订购数量 | 5000 |
| unit_price | DECIMAL(12,2) | 单价 | 45.00 |
| total_amount | DECIMAL(14,2) | 总金额 | 225000.00 |
| order_date | DATE | 下单日期 | 2026-04-10 |
| delivery_date | DATE | 交货日期 | 2026-05-10 |
| actual_delivery_date | DATE | 实际交货 | NULL |
| delivery_status | VARCHAR(16) | 交货状态 | pending / partial / delivered / delayed |
| payment_status | VARCHAR(16) | 付款状态 | unpaid / partial / paid |
| sales_channel | VARCHAR(16) | 销售渠道 | direct / agent / oem |
| priority | VARCHAR(8) | 优先级 | P1 / P2 / P3 |
| notes | TEXT | 备注 | — |

### 4.3 数据量级

| 表 | 行数 | 时间跨度 | 数据大小(估) |
|----|------|---------|-------------|
| wip_lots | 50,000 | 12 个月 | ~25 MB |
| production_orders | 20,000 | 12 个月 | ~10 MB |
| equipment_metrics | 300,000 | 3 个月（小时级） | ~60 MB |
| quality_inspections | 80,000 | 12 个月 | ~20 MB |
| suppliers | 400 | 静态 | <1 MB |
| purchase_orders | 30,000 | 12 个月 | ~12 MB |
| cost_transactions | 100,000 | 12 个月 | ~25 MB |
| customers | 150 | 静态 | <1 MB |
| sales_orders | 25,000 | 12 个月 | ~10 MB |
| **总计** | **~605,000** | — | **~160 MB** |

### 4.4 知识库内容

在 DataLens 知识库中准备以下条目（**200+ 条**），分为 10 个章节（A-J）：

#### 章节结构总览

| 章节 | 内容 | 条目数 |
|------|------|-------|
| A. 生产制造知识 | 工艺流程、产线能力、Cycle Time、WIP 管理、急单处理等 | 15 |
| B. 质量体系与术语 | 良率体系、缺陷分类、SPC、FMEA、8D、PPAP 等 | 12 |
| C. 设备工程知识 | OEE 详解、MTBF/MTTR、维护计划、能耗管理、设备验收等 | 10 |
| D. 供应链管理 | 物料策略、供应商评级、采购流程、安全库存、风险管控等 | 10 |
| E. 财务与成本 | 成本中心、成本结构、分摊方法、毛利率、折旧政策、投资分析等 | 10 |
| F. 销售与客户 | 客户行业分类、渠道、信用评级、回款管理、投诉处理等 | 7 |
| G. 制造业指标体系（98 条） | **完整分析框架**，三层架构（战略/战术/运营），7 大域： | **98** |
| | G1 生产制造（产出达成率、Cycle Time、WIP Days、报废率等 18 项） | |
| | G2 质量指标（工序良率、DPPM、CPK、Defect Pareto、质量成本率等 16 项） | |
| | G3 设备工程（OEE 三要素、MTBF/MTTR、利用率、能耗效率等 14 项） | |
| | G4 供应链（供应商 OTD、来料不良率、采购周期、集中度等 14 项） | |
| | G5 财务成本（单晶圆成本、成本结构、毛利率、预算达成率等 14 项） | |
| | G6 销售与客户（营收、新签订单、客户贡献度、回款率等 12 项） | |
| | G7 综合经营（增长率、利润率、EVA、盈亏平衡、预警规则等 10 项） | |
| H. 业务规则与审批流 | 报废审批、工单关闭、供应商准入、ECN、数据安全等 | 10 |
| I. 行业标准与认证 | ISO 9001、IATF 16949、AEC-Q100、JEDEC、RoHS、ESG | 6 |
| J. 常见分析场景与 SQL（30 条） | 完整覆盖所有域的实用分析 SQL | 30 |
| **合计** | | **~208** |

#### 详细指标框架（G 节）

指标体系采用 **三层架构**：
- **战略层**（月/季/年）：面向总经理/董事会，关注利润率、增长、EVA
- **战术层**（周/月）：面向部门总监，关注 OEE、良率、OTD、预算达成
- **运营层**（日/周）：面向工程师/主管，关注产出、缺陷、停机、WIP

每个指标包含完整定义、公式、数据来源（映射到 MySQL 表字段）、维度标签和行业基准值。

---

## 5. 测试场景与用例

### 测试流程

```
场景 0: 环境搭建
  │
  ▼
场景 1: 新建数据源 → 测试连接 → 分析库表
  │
  ▼
场景 2: 创建业务域 → 挂载表 → 对话选表验证
  │
  ▼
场景 3: 创建知识库 → 导入知识 → 验证 RAG 效果
  │
  ▼
场景 4: ChatBI 问答（无知识库 vs 有知识库 对比）
  │
  ▼
场景 5: 问答覆盖度验证（20+ 问题，含模糊/复杂/边界）
  │
  ▼
场景 6: 知识库文件导入（批量文档上传）
  │
  ▼
场景 7: 知识库搜索（混合搜索验证）
```

### 场景 1：数据源接入

| 用例 | 操作 | 预期结果 |
|------|------|---------|
| 1.1 创建 MySQL 数据源 | 填写 manufacturing_demo 连接信息 | 创建成功 |
| 1.2 测试连接 | 点击"测试连接" | 返回成功，显示「9 张表」 |
| 1.3 浏览库表 | 展开目录树 | 显示 9 张表及字段 |
| 1.4 分析单表 | 选择 wip_lots 分析 | 字段描述、枚举值、样本数据生成 |
| 1.5 分析全部表 | 执行全库分析 | 9 张表全部分析完成，字段描述完整 |
| 1.6 查看表详情 | 查看 wip_lots 详情 | 显示列信息、样本、统计 |

### 场景 2：业务域与选表

| 用例 | 操作 | 预期结果 |
|------|------|---------|
| 2.1 创建业务域「制造业生产分析」 | 填写名称描述 | 创建成功 |
| 2.2 挂载全部 9 张表到业务域 | 选择表挂载 | 挂载成功 |
| 2.3 Copilot 选择业务域 | 切换到该域 | 上下文提示已切换 |
| 2.4 问简单选表问题 | "查看最近一周的在制批次" | 自动选中 wip_lots，生成正确 SQL |

### 场景 3：知识库导入

| 用例 | 操作 | 预期结果 |
|------|------|---------|
| 3.1 创建知识库「华芯制造知识库」 | 创建并绑定到业务域 | 创建成功 |
| 3.2 逐个添加 10 条业务术语知识 | 填写标题和正文 | 10 条导入成功 |
| 3.3 添加 12 条指标口径 | 同上 | 12 条导入成功 |
| 3.4 添加 8 条业务规则 | 同上 | 8 条导入成功 |
| 3.5 搜索验证 | 搜索"OEE" | 返回相关条目 |

### 场景 4：ChatBI 问答验证（核心场景）

#### 4.1 基础查询（简单单表）

| 编号 | 问题 | 验证点 |
|------|------|--------|
| Q01 | "目前在制的活跃批次有哪些？" | WHERE lot_status='active'，查 wip_lots |
| Q02 | "FAB_A01 产线今天的 OEE 平均值是多少？" | AVG(oee_percent)，equipment_metrics |
| Q03 | "列出所有 A 级供应商" | WHERE tier='A'，查 suppliers |
| Q04 | "本月工单总数和完成数" | COUNT + status 过滤 |

#### 4.2 聚合统计

| 编号 | 问题 | 验证点 |
|------|------|--------|
| Q05 | "各产线的设备 OEE 平均值对比" | GROUP BY fab_id |
| Q06 | "不同类型缺陷的数量分布" | GROUP BY defect_type |
| Q07 | "本月各成本中心的费用占比" | GROUP BY cost_center + 占比计算 |
| Q08 | "月度采购金额趋势" | 按月的 GROUP BY + 时间窗口 |

#### 4.3 多表 JOIN

| 编号 | 问题 | 验证点 |
|------|------|--------|
| Q09 | "每个供应商的采购总额是多少？列出名称和金额" | suppliers JOIN purchase_orders |
| Q10 | "良率最高的前 5 批次对应的产品型号" | wip_lots JOIN quality_inspections |
| Q11 | "每个客户的销售额及回款状态" | customers JOIN sales_orders |
| Q12 | "分析各产品的毛利率（销售-成本）" | sales_orders 与 cost_transactions JOIN |

#### 4.4 业务口径理解（依赖知识库 RAG）

| 编号 | 问题 | 验证点 |
|------|------|--------|
| Q13 | "整体制造良率是多少？" | 知识库中的良率定义，区分终检 vs 各工序 |
| Q14 | "本月工单准时交付率如何？" | 依赖知识库中 OTD 口径 |
| Q15 | "TOP 5 缺陷类型的 DPPM 是多少？" | 依赖知识库 DPPM 公式 |
| Q16 | "前五大客户的贡献度如何？" | 依赖客户贡献度口径 |
| Q17 | "FAB_A01 线的整体 OEE 和瓶颈在哪里？" | OEE 口径 + 工序分析 |

#### 4.5 模糊/复杂问法

| 编号 | 问题 | 验证点 |
|------|------|--------|
| Q18 | "哪些批次质量有问题？" | 模糊问法，需推理为 defect_qty>0 或 qc 不合格 |
| Q19 | "最近的物料供应情况怎么样？" | 模糊问法，理解为采购到货及时率或采购单状态分布 |
| Q20 | "产线最近是不是不太稳定？" | 模糊问法，需推理为 OEE 或良率趋势 |
| Q21 | "我们最赚钱的产品是哪个？" | 多步推理：销售额-成本，按产品分组 |
| Q22 | "对比一下有知识库和没有知识库的回答差异" | 清空知识库 vs 启用知识库，问同一道口径题 |

---

## 6. 执行计划

### 阶段划分

```
Stage 0: 环境准备（你操作）                          ─ 约 30 分钟
Stage 1: 生成测试数据（我准备好你先确认）              ─ 约 15 分钟
Stage 2: 数据导入 & 验证（你执行）                     ─ 约 15 分钟
Stage 3: 启动 DataLens 服务（你执行）                  ─ 约 10 分钟
Stage 4: 执行测试（我配合你完成）                      ─ 约 60~90 分钟
Stage 5: 演示截图/录屏整理（你或我）                   ─ 约 20 分钟
```

### 详细步骤

#### Stage 0：环境准备（预计 30 分钟）

1. 确认本地 PostgreSQL 15+ 已安装且运行，pgvector 扩展可用
2. 确认 MySQL 8.0+ 已安装且运行
3. 确认 Python 3.11+ / Node.js 18+ 已安装
4. 创建 PostgreSQL 数据库 datalens（如需）
5. 配置 `.env` 文件（见 [7. 需要你准备的](#7-你需要准备的)）
6. 准备 LLM API Key

#### Stage 1：生成测试物料（我完成，你审查）

我编写以下文件到 `scripts/` 目录：

| 文件 | 说明 |
|------|------|
| `manufacturing_seed_data.py` | MySQL 数据生成脚本（~60 万行） |
| `testdata/knowledge_manufacturing_domain.md` | 知识库内容（200+ 条，含 98 项指标体系 + 30 个 SQL 场景） |
| `e2e/config.ts` | Playwright 全局配置 |
| `e2e/pages/datasources.ts` | 数据源页 POM |
| `e2e/pages/copilot.ts` | Copilot 页 POM |
| `e2e/pages/knowledgebases.ts` | 知识库页 POM |
| `e2e/pages/domains.ts` | 业务域页 POM |
| `e2e/scenario-1-datasource.spec.ts` | 场景1：数据源接入 |
| `e2e/scenario-2-domain.spec.ts` | 场景2：业务域选表 |
| `e2e/scenario-3-knowledgebase.spec.ts` | 场景3：知识库导入 |
| `e2e/scenario-4-copilot.spec.ts` | 场景4-5：ChatBI 问答（22 题，覆盖全部指标域） |
| `e2e/scenario-5-search.spec.ts` | 场景6-7：文件导入 + 知识搜索 |
| `run-all.sh` | 一键执行脚本（数据导入 → 服务启动 → E2E 测试） |

#### Stage 2：物料审查（你审查）

你审查所有脚本文件，确认数据合理性、测试覆盖度，没问题后进入 Stage 3。

#### Stage 3：执行（你运行 `run-all.sh` 或分步执行）

```bash
# 方式一：全自动一键执行
./scripts/run-all.sh

# 方式二：分步执行
# Step 1: 生成并导入 MySQL 数据
python3 scripts/manufacturing_seed_data.py --host 127.0.0.1 --port 3306 --user root --password yourpassword

# Step 2: 启动 DataLens 服务
./scripts/service.sh start

# Step 3: 安装 Playwright 依赖
pip install playwright
npx playwright install chromium

# Step 4: 运行 E2E 测试
npx playwright test scripts/e2e/ --config scripts/e2e/playwright.config.ts
```

#### Stage 4：查看报告

Playwright 会自动生成：
- **HTML 测试报告**：`scripts/e2e/test-results/report.html`
- **截图归档**：`scripts/e2e/screenshots/`（每步操作的截图）
- **视频录制**：`scripts/e2e/videos/`（可选）
- **测试日志**：`scripts/e2e/test-results/logs/`

这些素材可以直接用于投资人路演材料。

---

## 7. 你需要准备的

### 7.1 本地软件

| 软件 | 确认情况 | 备注 |
|------|---------|------|
| PostgreSQL 15+ | ⬜ 未确认 | `postgres --version` |
| pgvector 扩展 | ⬜ 未确认 | `SELECT * FROM pg_extension WHERE extname='vector'` |
| MySQL 8.0+ | ⬜ 未确认 | `mysql --version` |
| Python 3.11+ | ⬜ 未确认 | `python3 --version` |
| Node.js 18+ | ⬜ 未确认 | `node --version` |
| npm | ⬜ 未确认 | `npm --version` |

### 7.2 账号与 API Key

| 项目 | 说明 | 是否必需 |
|------|------|---------|
| **LLM API Key** | DeepSeek 或 OpenAI 的 API Key | **必需** — 问答核心引擎 |
| 建议：DeepSeek 成本更低，适合大量问答测试；如果都没有，本地有 fallback 但效果有限 | |

> 如果没有 API Key，系统会使用基于规则的 fallback 模式，SQL 生成能力会显著下降，**路演效果打折扣**。建议至少准备一个 DeepSeek Key。

### 7.3 配置文件 `.env`

确认 `.env` 文件内容（位于项目根目录）：

```bash
DATABASE_URL=postgresql://postgres:password@localhost:5432/datalens
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# 或
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
BACKEND_PORT=8000
FRONTEND_PORT=3000
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 7.4 可选但推荐的

- **截屏/录屏工具** — 用于投资人演示材料
- **OBS Studio** — 录制整个测试流程视频
- **终端多路复用** (tmux/iterm2 panes) — 同时展示 SQL 查询和前端回答

---

## 8. 成功标准

| 等级 | 标准 | 判定 |
|------|------|------|
| 🟢 P0 通过 | 数据源接入 → 表分析 → 业务域 → 知识库 → 问答，端到端走通 | 全部 |
| 🟢 P0 通过 | 22 问题中 80% SQL 语法正确、业务逻辑合理 | ≥ 18 题 |
| 🟡 P1 良好 | 知识库加持下口径问题（Q13-Q17）回答正确率 ≥ 80% | ≥ 4 题 |
| 🟡 P1 良好 | 多表 JOIN 类问题 SQL 正确 | ≥ 3 题 |
| 🔵 P2 优秀 | 模糊问法能正确理解意图 | ≥ 2 题 |
| 🔵 P2 优秀 | 演示流程流畅、无重大 UI/UX 问题 | — |

---

## 9. 附录

### A. LLM 配置建议

在路演前，在 DataLens 的「LLM 设置」页面配置好模型：

- **Copilot 对话模型**：DeepSeek Chat / GPT-4o-mini（平衡速度与效果）
- **语义分析模型**：DeepSeek Chat / GPT-4o-mini

### B. 演示话术要点

略（后续可根据你的需求定制路演脚本）。

### C. 问题反馈记录

略（测试执行中记录）。
