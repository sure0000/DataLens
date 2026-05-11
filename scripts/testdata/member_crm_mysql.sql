-- =============================================================================
-- DataLens 测试数据：会员与积分域（MySQL 8+ / utf8mb4）
-- 用途：先导入 → 在 DataLens 中接入数据源并做表分析 → 测「仅表结构+画像」的选表准确度
-- 库名可按需修改：下文默认 retail_ops（也可全局替换为 ecommerce 等已有库名）
--
-- 说明：crm_points_ledger.balance_after 为「写入时快照」演示值，用于展示列语义；
--       不要求按 ledger_id 或日期跨行严格单调递推，分析侧以 event_type / points_delta 为主。
-- =============================================================================

CREATE DATABASE IF NOT EXISTS retail_ops DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE retail_ops;

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------------
-- 1. 会员主档：一人一行，含等级与生命周期状态（常见电商/零售 CRM）
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS crm_points_ledger;
DROP TABLE IF EXISTS crm_coupon_redemption;
DROP TABLE IF EXISTS crm_member;

CREATE TABLE crm_member (
  member_id BIGINT NOT NULL COMMENT '会员内部主键，全局唯一',
  mobile_masked VARCHAR(20) NOT NULL COMMENT '脱敏手机号，末4位保留，用于客服核对',
  display_name VARCHAR(64) NOT NULL COMMENT '会员展示昵称',
  register_channel VARCHAR(32) NOT NULL COMMENT '注册渠道：app / wechat_mp / alipay_mp / offline_pos / web',
  current_level VARCHAR(16) NOT NULL COMMENT '当前等级编码：NORMAL / SILVER / GOLD / PLATINUM',
  lifecycle_status VARCHAR(16) NOT NULL COMMENT '生命周期：active / dormant / churned / blocked',
  city_tier VARCHAR(8) NOT NULL COMMENT '城市线级：T1 / T2 / T3 / unknown',
  register_at DATETIME NOT NULL COMMENT '注册时间（UTC+8 业务库写入）',
  last_order_at DATETIME DEFAULT NULL COMMENT '最近一笔有效订单支付时间，无订单为 NULL',
  last_active_at DATETIME NOT NULL COMMENT '最近一次端上活跃（埋点汇总），用于流失预警',
  PRIMARY KEY (member_id),
  KEY idx_member_level (current_level),
  KEY idx_member_lifecycle (lifecycle_status),
  KEY idx_member_last_active (last_active_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会员主档：等级与活跃由离线任务日更';

-- ---------------------------------------------------------------------------
-- 2. 积分流水：一行一次积分变动，可关联订单号（文本，避免强外键便于造数）
-- ---------------------------------------------------------------------------
CREATE TABLE crm_points_ledger (
  ledger_id BIGINT NOT NULL COMMENT '流水主键',
  member_id BIGINT NOT NULL COMMENT '对应 crm_member.member_id',
  biz_date DATE NOT NULL COMMENT '业务归属日（与结算/对账对齐，非必然等于 created_at 日期）',
  event_type VARCHAR(32) NOT NULL COMMENT '事件：ORDER_PAY / SIGN_IN / ADMIN_ADJ / EXPIRE / REFUND_DEDUCT / CAMPAIGN_BONUS',
  points_delta INT NOT NULL COMMENT '变动积分，可正可负',
  balance_after INT NOT NULL COMMENT '变动后可用积分余额（冗余快照，以本行写入时为准）',
  ref_biz_id VARCHAR(48) DEFAULT NULL COMMENT '关联业务单号：订单号/活动批次/手工单号等',
  remark VARCHAR(128) DEFAULT NULL COMMENT '备注：风控拦截、客服补偿说明等',
  created_at DATETIME NOT NULL COMMENT '流水写入时间',
  PRIMARY KEY (ledger_id),
  KEY idx_ledger_member_date (member_id, biz_date),
  KEY idx_ledger_event (event_type),
  KEY idx_ledger_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='积分台账：对账以 biz_date + event_type 聚合为主';

-- ---------------------------------------------------------------------------
-- 3. 优惠券核销：与会员、大促活动关联，便于测多表 JOIN 与渠道口径
-- ---------------------------------------------------------------------------
CREATE TABLE crm_coupon_redemption (
  redemption_id BIGINT NOT NULL COMMENT '核销主键',
  member_id BIGINT NOT NULL COMMENT '核销会员',
  coupon_template_code VARCHAR(32) NOT NULL COMMENT '券模板编码，如 FULLCUT_300_30',
  campaign_code VARCHAR(32) NOT NULL COMMENT '活动编码，如 618_2025 / NEW_USER_7D',
  channel VARCHAR(24) NOT NULL COMMENT '核销渠道：app / wechat_mp / offline_pos',
  order_id VARCHAR(32) NOT NULL COMMENT '关联订单号（本测试库内可与积分流水中 ref_biz_id 对齐）',
  face_value DECIMAL(10,2) NOT NULL COMMENT '券面额（元）',
  discount_amt DECIMAL(10,2) NOT NULL COMMENT '实际抵扣金额（元），满减场景可能小于面额',
  redeemed_at DATETIME NOT NULL COMMENT '核销时间',
  PRIMARY KEY (redemption_id),
  KEY idx_red_member (member_id),
  KEY idx_red_campaign (campaign_code),
  KEY idx_red_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='优惠券核销事实表';

-- ---------------------------------------------------------------------------
-- 数据：规模适中，分布接近真实（等级、流失、大促核销）
-- ---------------------------------------------------------------------------

INSERT INTO crm_member (member_id, mobile_masked, display_name, register_channel, current_level, lifecycle_status, city_tier, register_at, last_order_at, last_active_at) VALUES
(100001, '138****1001', '林晨', 'app', 'GOLD', 'active', 'T1', '2023-03-12 10:21:00', '2025-05-08 21:03:11', '2025-05-10 09:15:00'),
(100002, '159****2208', '周雨桐', 'wechat_mp', 'SILVER', 'active', 'T1', '2024-01-05 14:08:33', '2025-04-28 19:44:02', '2025-05-09 20:01:00'),
(100003, '186****5512', '王磊-企业采购', 'web', 'PLATINUM', 'active', 'T1', '2022-11-20 09:00:00', '2025-05-09 11:22:00', '2025-05-10 08:40:00'),
(100004, '137****8833', '陈潇', 'app', 'NORMAL', 'dormant', 'T2', '2024-06-18 16:40:00', '2024-12-01 12:00:00', '2025-02-14 13:20:00'),
(100005, '188****0099', '赵敏', 'offline_pos', 'SILVER', 'active', 'T2', '2023-08-01 11:11:00', '2025-05-07 18:30:00', '2025-05-10 10:00:00'),
(100006, '135****7766', '刘洋', 'alipay_mp', 'NORMAL', 'churned', 'T3', '2023-01-10 08:00:00', '2024-03-20 10:00:00', '2024-05-01 09:00:00'),
(100007, '136****3344', '黄佳佳', 'wechat_mp', 'GOLD', 'active', 'T1', '2023-09-09 19:19:00', '2025-05-10 07:45:00', '2025-05-10 09:50:00'),
(100008, '139****6677', '吴昊', 'app', 'SILVER', 'blocked', 'T2', '2024-02-28 12:34:00', '2025-01-15 15:00:00', '2025-03-01 10:00:00'),
(100009, '158****1122', '孙莉', 'app', 'NORMAL', 'active', 'T2', '2024-11-11 00:05:00', '2025-05-01 22:18:00', '2025-05-09 23:59:00'),
(100010, '177****4455', '郑凯', 'web', 'GOLD', 'active', 'T1', '2022-05-05 05:05:00', '2025-05-10 06:12:00', '2025-05-10 09:05:00'),
(100011, '133****9988', '钱多多', 'wechat_mp', 'SILVER', 'dormant', 'T3', '2024-04-04 04:04:00', '2024-10-10 10:10:00', '2025-01-20 12:00:00'),
(100012, '150****6670', '冯娜', 'app', 'PLATINUM', 'active', 'T1', '2021-12-12 12:12:00', '2025-05-09 20:20:00', '2025-05-10 09:30:00'),
(100013, '151****3210', '韩雪', 'offline_pos', 'NORMAL', 'active', 'T2', '2024-07-07 07:07:00', '2025-04-30 17:00:00', '2025-05-08 21:00:00'),
(100014, '152****6543', '曹阳', 'app', 'SILVER', 'active', 'T2', '2023-10-01 10:10:00', '2025-05-06 09:30:00', '2025-05-10 08:55:00'),
(100015, '153****9876', '袁圆', 'wechat_mp', 'GOLD', 'active', 'T1', '2022-08-18 18:18:00', '2025-05-10 08:08:00', '2025-05-10 09:18:00'),
(100016, '155****2468', '蒋毅', 'app', 'NORMAL', 'dormant', 'T2', '2024-03-03 03:03:00', '2024-11-11 11:11:00', '2025-02-02 14:00:00'),
(100017, '156****1357', '沈冰', 'alipay_mp', 'SILVER', 'active', 'T3', '2024-09-09 09:09:00', '2025-05-05 20:00:00', '2025-05-09 22:10:00'),
(100018, '157****8642', '韩梅梅', 'app', 'GOLD', 'active', 'T1', '2023-05-20 20:20:00', '2025-05-10 07:00:00', '2025-05-10 09:25:00'),
(100019, '180****7410', '魏强', 'web', 'PLATINUM', 'active', 'T1', '2020-01-01 00:00:00', '2025-05-10 09:00:00', '2025-05-10 09:28:00'),
(100020, '181****8520', '邓莎', 'wechat_mp', 'NORMAL', 'active', 'T2', '2024-12-25 10:00:00', '2025-05-03 16:40:00', '2025-05-09 18:00:00');

INSERT INTO crm_points_ledger (ledger_id, member_id, biz_date, event_type, points_delta, balance_after, ref_biz_id, remark, created_at) VALUES
(9000001, 100001, '2025-05-10', 'ORDER_PAY', 120, 5680, 'ORD-20250510-100001', NULL, '2025-05-10 09:20:01'),
(9000002, 100001, '2025-05-08', 'ORDER_PAY', 80, 5560, 'ORD-20250508-100001', NULL, '2025-05-08 21:05:00'),
(9000003, 100001, '2025-05-01', 'SIGN_IN', 5, 5480, 'SIG-20250501-100001', NULL, '2025-05-01 08:00:10'),
(9000004, 100002, '2025-05-09', 'ORDER_PAY', 45, 920, 'ORD-20250509-100002', NULL, '2025-05-09 20:02:00'),
(9000005, 100002, '2025-04-20', 'EXPIRE', -30, 875, 'EXP-202504-BATCH01', '季度末积分过期', '2025-04-30 23:59:59'),
(9000006, 100003, '2025-05-10', 'ORDER_PAY', 600, 42000, 'ORD-20250510-100003', NULL, '2025-05-10 09:10:00'),
(9000007, 100003, '2025-05-09', 'CAMPAIGN_BONUS', 500, 41400, 'CMP-618-2025-PRE', '大促预售任务奖励', '2025-05-09 10:00:00'),
(9000008, 100004, '2024-12-01', 'ORDER_PAY', 22, 210, 'ORD-20241201-100004', NULL, '2024-12-01 12:05:00'),
(9000009, 100005, '2025-05-07', 'ORDER_PAY', 36, 1320, 'ORD-20250507-100005', NULL, '2025-05-07 18:35:00'),
(9000010, 100006, '2024-03-20', 'ORDER_PAY', 10, 50, 'ORD-20240320-100006', NULL, '2024-03-20 10:01:00'),
(9000011, 100006, '2024-05-01', 'EXPIRE', -50, 0, 'EXP-202405-BATCH02', '账户长期未活跃清零策略', '2024-05-01 01:00:00'),
(9000012, 100007, '2025-05-10', 'ORDER_PAY', 200, 8900, 'ORD-20250510-100007', NULL, '2025-05-10 07:50:00'),
(9000013, 100008, '2025-01-15', 'REFUND_DEDUCT', -150, 0, 'ORD-20250115-100008', '售后退款扣回积分', '2025-01-16 11:00:00'),
(9000014, 100009, '2025-05-01', 'ORDER_PAY', 15, 340, 'ORD-20250501-100009', NULL, '2025-05-01 22:20:00'),
(9000015, 100010, '2025-05-10', 'ORDER_PAY', 88, 12000, 'ORD-20250510-100010', NULL, '2025-05-10 06:30:00'),
(9000016, 100012, '2025-05-09', 'ORDER_PAY', 300, 80000, 'ORD-20250509-100012', NULL, '2025-05-09 20:25:00'),
(9000017, 100015, '2025-05-10', 'SIGN_IN', 10, 15200, 'SIG-20250510-100015', NULL, '2025-05-10 08:18:00'),
(9000018, 100018, '2025-05-10', 'ORDER_PAY', 150, 22100, 'ORD-20250510-100018', NULL, '2025-05-10 07:12:00'),
(9000019, 100019, '2025-05-10', 'ORDER_PAY', 40, 99000, 'ORD-20250510-100019', NULL, '2025-05-10 09:02:00');

INSERT INTO crm_coupon_redemption (redemption_id, member_id, coupon_template_code, campaign_code, channel, order_id, face_value, discount_amt, redeemed_at) VALUES
(700001, 100001, 'FULLCUT_300_30', '618_2025', 'app', 'ORD-20250510-100001', 30.00, 30.00, '2025-05-10 09:19:50'),
(700002, 100002, 'NEWUSER_10', 'NEW_USER_7D', 'wechat_mp', 'ORD-20250509-100002', 10.00, 10.00, '2025-05-09 20:01:40'),
(700003, 100003, 'B2B_REBATE_500', '618_2025', 'web', 'ORD-20250510-100003', 500.00, 500.00, '2025-05-10 09:09:30'),
(700004, 100005, 'STORE_5OFF', 'STORE_Q2', 'offline_pos', 'ORD-20250507-100005', 5.00, 5.00, '2025-05-07 18:32:00'),
(700005, 100007, 'FULLCUT_300_30', '618_2025', 'app', 'ORD-20250510-100007', 30.00, 28.00, '2025-05-10 07:48:00'),
(700006, 100010, 'VIP_EXTRA_20', '618_2025', 'app', 'ORD-20250510-100010', 20.00, 20.00, '2025-05-10 06:28:00'),
(700007, 100012, 'PLAT_FREE_SHIP', '618_2025', 'app', 'ORD-20250509-100012', 15.00, 15.00, '2025-05-09 20:24:00'),
(700008, 100018, 'FULLCUT_300_30', '618_2025', 'app', 'ORD-20250510-100018', 30.00, 30.00, '2025-05-10 07:10:00'),
(700009, 100019, 'B2B_REBATE_500', '618_2025', 'web', 'ORD-20250510-100019', 500.00, 400.00, '2025-05-10 09:01:00'),
(700010, 100020, 'NEWUSER_10', 'NEW_USER_7D', 'wechat_mp', 'ORD-20250503-100020', 10.00, 10.00, '2025-05-03 16:42:00');
