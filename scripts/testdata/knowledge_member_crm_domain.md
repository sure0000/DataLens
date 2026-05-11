# 业务域知识：零售会员与积分（第二阶段导入用）

> 导入顺序建议：先在 MySQL 执行 `member_crm_mysql.sql`，在 DataLens 完成数据源接入与**表分析**并验证选表效果后，再将本文拆成 1～3 条「知识库条目」录入同一业务域绑定的知识库，用于测试 **RAG 筛表 + 口径** 准确度。

---

## 1. 域内核心对象（与物理表对应）

| 业务对象 | 物理表 | 说明 |
|----------|--------|------|
| 会员主数据 | `retail_ops.crm_member` | 一人一行；等级字段 `current_level`；生命周期 `lifecycle_status`；活跃看 `last_active_at`，下单看 `last_order_at`。 |
| 积分台账 | `retail_ops.crm_points_ledger` | 每次积分增减一行；`event_type` 区分来源；`biz_date` 为**对账归属日**，可与 `created_at` 跨日；`ref_biz_id` 常存订单号 `ORD-…` 或活动批次 `CMP-…`。 |
| 券核销事实 | `retail_ops.crm_coupon_redemption` | 一次核销一行；`campaign_code` 标识大促（如 `618_2025`）；`discount_amt` 为**实际抵扣**，可与面额不同（满减未满额时）。 |

若连接配置里默认库不是 `retail_ops`，分析后表名仍为 `crm_*`，SQL 中写库表时需与 DataLens 登记的 `database_name.table_name` 一致。

---

## 2. 等级与生命周期（问「高价值会员」「流失」时常用）

- **等级编码**：`NORMAL` < `SILVER` < `GOLD` < `PLATINUM`；数值比较需自行映射或按 CASE 排序，表中未存数值等级。
- **`lifecycle_status`**：
  - `active`：正常可运营。
  - `dormant`：未注销但近期无下单；可与 `last_order_at` 距今天数结合看沉睡。
  - `churned`：已标记流失；历史积分可能已被 `EXPIRE` 清零策略冲掉。
  - `blocked`：风控冻结；**默认不参与**拉新/发券活动统计，若题目未说明「含冻结」，应用 `lifecycle_status <> 'blocked'` 过滤。
- **活跃**：`last_active_at` 来自端埋点汇总，**不等于**付费；看付费转化应使用 `last_order_at` 或订单事实（本域可用积分流水中 `ORDER_PAY` + `ref_biz_id` 关联思路）。

---

## 3. 积分与订单、大促的口径

- **下单得积分**：`crm_points_ledger.event_type = 'ORDER_PAY'`，`points_delta` 为正；`ref_biz_id` 多为 `ORD-YYYYMMDD-会员ID` 形式（测试数据约定，非生产强约束）。
- **签到**：`SIGN_IN`，单笔积分小、频次可高。
- **过期扣减**：`EXPIRE`，`points_delta` 为负；`remark` 可能含「季度末积分过期」等说明。
- **退款扣回**：`REFUND_DEDUCT`，避免在「实付 GMV」与「积分成本」混算时双计。
- **大促奖励**：`CAMPAIGN_BONUS`，`ref_biz_id` 可出现 `CMP-618-2025-PRE` 等；与 `crm_coupon_redemption.campaign_code = '618_2025'` 同属 618 活动簇，多表分析时可按活动维度对齐。

---

## 4. 优惠券核销

- **渠道** `channel`：`app` / `wechat_mp` / `offline_pos`；做「线下门店核销占比」时按该字段分组。
- **金额**：分析「券带来的优惠成本」用 `discount_amt`；`face_value` 仅表示券面设计值。
- **与订单对齐**：`order_id` 与积分流水中 `ORDER_PAY` 的 `ref_biz_id` 在测试数据中有意做成一致，便于验证 JOIN。

---

## 5. 常见陷阱（用于测模型是否「读知识」）

1. **问「总积分余额」**：余额为时点概念，应取各会员**最新一条** `crm_points_ledger`（按 `created_at` 或 `ledger_id`）的 `balance_after`，不可对历史行求和 `points_delta`。
2. **问「618 活动带来的订单积分」**：应用 `biz_date` 落在活动期 + `event_type='ORDER_PAY'` + `ref_biz_id` 或活动侧表关联；若仅筛 `campaign_code` 需在核销表或知识中明确是否包含「仅券」路径。
3. **`churned` 是否算会员数**：题目说「当前可运营会员」时应排除 `churned` / `blocked`；仅说「历史注册」则可包含。
4. **城市线级**：`city_tier` 为 `T1/T2/T3`，与会员是否高等级无必然对应，避免在 SQL 中错误写死关联。

---

## 6. 示例分析问法（可自行在 Copilot 复测）

1. 「最近 7 天仍活跃、且等级为 GOLD 及以上的会员有多少人？」（`last_active_at` + `current_level` + `lifecycle_status`）
2. 「618_2025 活动下，各渠道核销券的实际优惠总额是多少？」（`crm_coupon_redemption`，按 `channel` 分组 sum `discount_amt`）
3. 「会员 100001 当前可用积分余额是多少？」（最新 `balance_after`）
4. 「有多少会员因退款被扣过积分？」（`event_type='REFUND_DEDUCT'`，去重 `member_id`）
