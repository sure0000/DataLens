#!/usr/bin/env python3
"""
华芯半导体制造业演示数据生成脚本

为 DataLens 路演生成 9 张生产级仿真数据表（~60 万行）。
使用方式：
  python3 scripts/manufacturing_seed_data.py --host 127.0.0.1 --port 3306 --user root --password yourpassword

依赖：pymysql (pip install pymysql)
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from collections.abc import Iterable
from contextlib import contextmanager
from datetime import date, datetime, timedelta

import pymysql
from pymysql.cursors import DictCursor

# ──────────────────────────────────────────────
# 常量定义
# ──────────────────────────────────────────────

# 7 个产品线
PRODUCTS = [
    {"code": "MCU-C2003-QFN", "name": "车规级 MCU", "tech": "28nm", "desc": "用于汽车电子控制单元，AEC-Q100 认证"},
    {"code": "MCU-C2010-LQFP", "name": "工控 MCU", "tech": "45nm", "desc": "工业控制与物联网网关"},
    {"code": "SOC-A5000-BGA", "name": "高性能 SoC", "tech": "28nm", "desc": "消费电子主控芯片，4K 视频处理"},
    {"code": "SOC-A3200-BGA", "name": "入门 SoC", "tech": "45nm", "desc": "物联网设备与智能家居"},
    {"code": "MEMS-S1000-LGA", "name": "压力传感器", "tech": "MEMS", "desc": "汽车/工业压力传感"},
    {"code": "MEMS-S2000-LGA", "name": "加速度传感器", "tech": "MEMS", "desc": "消费电子运动检测"},
    {"code": "PMIC-P100-QFN", "name": "电源管理芯片", "tech": "45nm", "desc": "便携设备电源管理"},
]

# 工艺流程路线（每个产品对应的工序数不同）
PROCESS_ROUTES: dict[str, list[str]] = {
    "MCU-C2003-QFN": [
        "STAGE_DEP_01", "STAGE_DEP_02", "STAGE_PHOTO_01", "STAGE_ETCH_01", "STAGE_DEP_03",
        "STAGE_PHOTO_02", "STAGE_ETCH_02", "STAGE_CMP_01", "STAGE_DEP_04", "STAGE_PHOTO_03",
        "STAGE_ETCH_03", "STAGE_IMP_01", "STAGE_DEP_05", "STAGE_PHOTO_04", "STAGE_ETCH_04",
        "STAGE_CMP_02", "STAGE_PASS_01", "STAGE_PROBE_01", "STAGE_DICING_01",
        "STAGE_PACKAGE_01", "STAGE_PACKAGE_02", "STAGE_TEST_01", "STAGE_TEST_02",
    ],
    "MCU-C2010-LQFP": [
        "STAGE_DEP_01", "STAGE_PHOTO_01", "STAGE_ETCH_01", "STAGE_DEP_02",
        "STAGE_PHOTO_02", "STAGE_ETCH_02", "STAGE_CMP_01", "STAGE_DEP_03",
        "STAGE_PHOTO_03", "STAGE_ETCH_03", "STAGE_IMP_01",
        "STAGE_PROBE_01", "STAGE_DICING_01",
        "STAGE_PACKAGE_01", "STAGE_TEST_01",
    ],
    "SOC-A5000-BGA": [
        "STAGE_DEP_01", "STAGE_DEP_02", "STAGE_PHOTO_01", "STAGE_ETCH_01", "STAGE_DEP_03",
        "STAGE_PHOTO_02", "STAGE_ETCH_02", "STAGE_CMP_01", "STAGE_DEP_04", "STAGE_PHOTO_03",
        "STAGE_ETCH_03", "STAGE_IMP_01", "STAGE_DEP_05", "STAGE_PHOTO_04", "STAGE_ETCH_04",
        "STAGE_CMP_02", "STAGE_PASS_01", "STAGE_PROBE_01", "STAGE_DICING_01",
        "STAGE_PACKAGE_01", "STAGE_PACKAGE_02", "STAGE_TEST_01", "STAGE_TEST_02",
    ],
    "SOC-A3200-BGA": [
        "STAGE_DEP_01", "STAGE_PHOTO_01", "STAGE_ETCH_01", "STAGE_DEP_02",
        "STAGE_PHOTO_02", "STAGE_ETCH_02", "STAGE_CMP_01",
        "STAGE_PROBE_01", "STAGE_DICING_01",
        "STAGE_PACKAGE_01", "STAGE_TEST_01",
    ],
    "MEMS-S1000-LGA": [
        "STAGE_DEP_01", "STAGE_PHOTO_01", "STAGE_ETCH_01",
        "STAGE_DEP_02", "STAGE_PHOTO_02", "STAGE_ETCH_02",
        "STAGE_DICING_01", "STAGE_PACKAGE_01", "STAGE_TEST_01",
    ],
    "MEMS-S2000-LGA": [
        "STAGE_DEP_01", "STAGE_PHOTO_01", "STAGE_ETCH_01",
        "STAGE_DEP_02", "STAGE_PHOTO_02", "STAGE_ETCH_02",
        "STAGE_DICING_01", "STAGE_PACKAGE_01", "STAGE_TEST_01",
    ],
    "PMIC-P100-QFN": [
        "STAGE_DEP_01", "STAGE_PHOTO_01", "STAGE_ETCH_01", "STAGE_DEP_02",
        "STAGE_PHOTO_02", "STAGE_ETCH_02", "STAGE_CMP_01",
        "STAGE_PROBE_01", "STAGE_DICING_01",
        "STAGE_PACKAGE_01", "STAGE_TEST_01",
    ],
}

PRODUCT_CODE_LIST = [p["code"] for p in PRODUCTS]

# 前道产线（晶圆制造）
FAB_FE = ["FAB_A01", "FAB_A02"]
# 后道产线（封装测试）
FAB_BE = ["FAB_B01", "FAB_B02", "FAB_B03"]
ALL_FABS = FAB_FE + FAB_BE

# 设备列表（按类型分组）
EQUIPMENT = {
    "etcher":       [f"ETCH_{i:03d}" for i in range(1, 9)],
    "lithography":  [f"LITHO_{i:03d}" for i in range(1, 7)],
    "deposition":   [f"DEP_{i:03d}" for i in range(1, 6)],
    "cmp":          [f"CMP_{i:03d}" for i in range(1, 5)],
    "test":         [f"TEST_{i:03d}" for i in range(1, 7)],
    "implant":      [f"IMP_{i:03d}" for i in range(1, 3)],
}

ALL_EQUIPMENT: list[tuple[str, str, str]] = []
for etype, codes in EQUIPMENT.items():
    for code in codes:
        # 前道产线设备
        if etype in ("etcher", "lithography", "deposition", "cmp", "implant"):
            fab = random.choice(FAB_FE)
        else:
            fab = random.choice(ALL_FABS)
        ALL_EQUIPMENT.append((code, etype, fab))

# 中国供应商
SUPPLIER_DATA = [
    # (name, category, tier, province, city)
    ("上海硅产业集团股份有限公司", "Silicon Wafer", "A", "上海", "上海"),
    ("中环半导体材料有限公司", "Silicon Wafer", "A", "天津", "天津"),
    ("沪硅产业（上海）有限公司", "Silicon Wafer", "A", "上海", "上海"),
    ("浙江晶盛机电股份有限公司", "Silicon Wafer", "B", "浙江", "杭州"),
    ("上海新阳半导体材料股份有限公司", "Photoresist", "A", "上海", "上海"),
    ("北京科华微电子材料有限公司", "Photoresist", "A", "北京", "北京"),
    ("苏州晶瑞化学股份有限公司", "Photoresist", "B", "江苏", "苏州"),
    ("华特气体股份有限公司", "Gas", "A", "广东", "佛山"),
    ("金宏气体股份有限公司", "Gas", "A", "江苏", "苏州"),
    ("广东华特气体有限公司", "Gas", "B", "广东", "广州"),
    ("北方华创科技集团股份有限公司", "Parts", "A", "北京", "北京"),
    ("中微半导体设备（上海）股份有限公司", "Parts", "A", "上海", "上海"),
    ("盛美半导体设备（上海）股份有限公司", "Parts", "B", "上海", "上海"),
    ("长电科技股份有限公司", "Packaging", "A", "江苏", "江阴"),
    ("华天科技股份有限公司", "Packaging", "A", "甘肃", "天水"),
    ("通富微电子股份有限公司", "Packaging", "B", "江苏", "南通"),
    ("宁波康强电子股份有限公司", "Packaging", "B", "浙江", "宁波"),
    ("日本信越化学工业株式会社", "Silicon Wafer", "A", "上海", "上海"),
    ("SUMCO 株式会社", "Silicon Wafer", "A", "上海", "上海"),
    ("陶氏化学（中国）有限公司", "Photoresist", "A", "上海", "上海"),
    ("液化空气（中国）投资有限公司", "Gas", "A", "上海", "上海"),
    ("林德气体（中国）有限公司", "Gas", "B", "上海", "上海"),
    ("应用材料（中国）有限公司", "Parts", "A", "上海", "上海"),
    ("泛林半导体设备（中国）有限公司", "Parts", "A", "北京", "北京"),
    ("科天国际贸易（上海）有限公司", "Parts", "B", "上海", "上海"),
    ("江苏南大光电材料股份有限公司", "Photoresist", "B", "江苏", "苏州"),
    ("湖北兴福电子材料股份有限公司", "Gas", "B", "湖北", "宜昌"),
    ("上海飞凯材料科技股份有限公司", "Photoresist", "B", "上海", "上海"),
    ("深圳华海达科技有限公司", "Parts", "C", "广东", "深圳"),
    ("浙江众合科技股份有限公司", "Parts", "C", "浙江", "杭州"),
]

# 中国客户
CUSTOMER_DATA = [
    # (name, industry, province, city, credit_rating)
    ("比亚迪汽车工业有限公司", "Automotive", "广东", "深圳", "AA"),
    ("联合汽车电子有限公司", "Automotive", "上海", "上海", "AA"),
    ("博世（中国）投资有限公司", "Automotive", "上海", "上海", "AA"),
    ("华为终端有限公司", "ConsumerElectronics", "广东", "深圳", "AA"),
    ("小米通讯技术有限公司", "ConsumerElectronics", "北京", "北京", "AA"),
    ("OPPO 广东移动通信有限公司", "ConsumerElectronics", "广东", "东莞", "A"),
    ("维沃移动通信有限公司", "ConsumerElectronics", "广东", "东莞", "A"),
    ("珠海格力电器股份有限公司", "ConsumerElectronics", "广东", "珠海", "A"),
    ("美的集团股份有限公司", "ConsumerElectronics", "广东", "佛山", "A"),
    ("汇川技术股份有限公司", "Industrial", "广东", "深圳", "A"),
    ("海康威视数字技术股份有限公司", "Industrial", "浙江", "杭州", "A"),
    ("深圳市大疆创新科技有限公司", "Industrial", "广东", "深圳", "A"),
    ("迈瑞医疗国际有限公司", "Medical", "广东", "深圳", "AA"),
    ("联影医疗技术集团有限公司", "Medical", "上海", "上海", "A"),
    ("中兴通讯股份有限公司", "ConsumerElectronics", "广东", "深圳", "A"),
    ("烽火通信科技股份有限公司", "Industrial", "湖北", "武汉", "B"),
    ("中科曙光信息产业股份有限公司", "Industrial", "北京", "北京", "A"),
    ("浪潮电子信息产业股份有限公司", "Industrial", "山东", "济南", "A"),
    ("中国中车股份有限公司", "Automotive", "北京", "北京", "AA"),
    ("浙江吉利控股集团有限公司", "Automotive", "浙江", "杭州", "A"),
    ("长城汽车股份有限公司", "Automotive", "河北", "保定", "A"),
    ("广州汽车集团股份有限公司", "Automotive", "广东", "广州", "A"),
    ("蔚来汽车科技有限公司", "Automotive", "上海", "上海", "B"),
    ("小鹏汽车股份有限公司", "Automotive", "广东", "广州", "B"),
    ("理想汽车有限公司", "Automotive", "北京", "北京", "B"),
    ("深圳市兆驰股份有限公司", "ConsumerElectronics", "广东", "深圳", "B"),
    ("TCL 科技集团股份有限公司", "ConsumerElectronics", "广东", "惠州", "B"),
    ("创维集团有限公司", "ConsumerElectronics", "广东", "深圳", "B"),
    ("北京经纬恒润科技股份有限公司", "Automotive", "北京", "北京", "A"),
    ("德赛西威汽车电子股份有限公司", "Automotive", "广东", "惠州", "A"),
]

SALES_REPS = [
    "周杰", "王芳", "李明", "张强", "刘洋", "陈静", "赵敏", "黄伟",
    "吴涛", "孙丽", "徐峰", "马超", "林小红", "郑鑫", "何琳",
]

# 成本中心
COST_CENTERS = [
    ("CC_FAB_A01", "前道产线 A01", "FAB_A01"),
    ("CC_FAB_A02", "前道产线 A02", "FAB_A02"),
    ("CC_FAB_B01", "封装产线 B01", "FAB_B01"),
    ("CC_FAB_B02", "封装产线 B02", "FAB_B02"),
    ("CC_FAB_B03", "封装产线 B03", "FAB_B03"),
]

COST_CATEGORIES = ["material", "labor", "depreciation", "utilities", "maintenance"]

OPERATORS = [
    "张伟", "李强", "王磊", "刘超", "陈明", "杨帆", "赵磊", "黄鑫",
    "周文", "吴刚", "徐磊", "孙超", "马杰", "朱涛", "胡亮",
    "郭鹏", "林斌", "何俊", "高峰", "罗军", "梁强", "宋涛",
    "唐亮", "韩冰", "曹杰", "邓超", "彭飞", "蒋勇", "余强", "潘磊",
]

INSPECTORS = [
    "赵琳", "钱华", "孙燕", "李红", "周梅", "吴玲", "郑洁", "王秀",
    "冯静", "陈琴", "褚敏", "卫芳",
]

PURCHASERS = [
    "刘芳", "陈娟", "王霞", "李娜", "张丽", "周婷", "吴琼", "郑敏",
]

DEFECT_TYPES = ["particle", "scratch", "thickness_err", "electrical", "none"]


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate manufacturing demo data for DataLens")
    p.add_argument("--host", default="127.0.0.1", help="MySQL host")
    p.add_argument("--port", type=int, default=3306, help="MySQL port")
    p.add_argument("--user", default="root", help="MySQL user")
    p.add_argument("--password", default="", help="MySQL password")
    p.add_argument("--database", default="manufacturing_demo", help="Target database name")
    p.add_argument("--seed", type=int, default=20260501, help="Random seed")
    # 数据量控制（可微调）
    p.add_argument("--wip-lots", type=int, default=50000, help="WIP lots count")
    p.add_argument("--prod-orders", type=int, default=20000, help="Production orders count")
    p.add_argument("--eqp-metrics", type=int, default=300000, help="Equipment metrics count")
    p.add_argument("--quality", type=int, default=80000, help="Quality inspections count")
    p.add_argument("--suppliers", type=int, default=400, help="Suppliers count (base + auto-generated)")
    p.add_argument("--purchase-orders", type=int, default=30000, help="Purchase orders count")
    p.add_argument("--cost-txns", type=int, default=100000, help="Cost transactions count")
    p.add_argument("--sales-orders", type=int, default=25000, help="Sales orders count")
    return p.parse_args()


def random_date_365(rng: random.Random) -> date:
    """过去 365 天内的随机日期"""
    return date.today() - timedelta(days=rng.randint(0, 364))


def random_datetime_365(rng: random.Random) -> datetime:
    """过去 365 天内的随机 datetime"""
    d = random_date_365(rng)
    return datetime(d.year, d.month, d.day,
                    rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59))


def random_datetime_range(rng: random.Random, start_days_ago: int, end_days_ago: int) -> datetime:
    """在 [end_days_ago, start_days_ago] 天前范围内随机 datetime"""
    days = rng.randint(end_days_ago, start_days_ago)
    d = date.today() - timedelta(days=days)
    return datetime(d.year, d.month, d.day,
                    rng.randint(0, 23), rng.randint(0, 59), rng.randint(0, 59))


@contextmanager
def get_conn(args: argparse.Namespace) -> Iterable[pymysql.connections.Connection]:
    conn = pymysql.connect(
        host=args.host, port=args.port, user=args.user, password=args.password,
        charset="utf8mb4", cursorclass=DictCursor, autocommit=False,
    )
    try:
        yield conn
    finally:
        conn.close()


def create_database(conn: pymysql.connections.Connection, db_name: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` DEFAULT CHARSET utf8mb4")
    conn.commit()


def drop_database(conn: pymysql.connections.Connection, db_name: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
    conn.commit()


def next_id(cur: DictCursor, table: str, col: str) -> int:
    cur.execute(f"SELECT COALESCE(MAX({col}), 0) + 1 AS n FROM {table}")
    return int(cur.fetchone()["n"])


# ──────────────────────────────────────────────
# 建表 DDL
# ──────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS wip_lots (
  lot_id BIGINT PRIMARY KEY,
  lot_code VARCHAR(32) NOT NULL,
  product_code VARCHAR(32) NOT NULL,
  route_code VARCHAR(32) NOT NULL,
  current_stage VARCHAR(32) NOT NULL,
  stage_seq INT NOT NULL,
  total_stages INT NOT NULL,
  qty_input INT NOT NULL,
  qty_output INT NOT NULL,
  qty_hold INT NOT NULL DEFAULT 0,
  qty_scrap INT NOT NULL DEFAULT 0,
  lot_status VARCHAR(16) NOT NULL DEFAULT 'active',
  fab_id VARCHAR(8) NOT NULL,
  operator VARCHAR(32) NOT NULL,
  start_time DATETIME NOT NULL,
  est_end_time DATETIME NOT NULL,
  actual_end_time DATETIME DEFAULT NULL,
  updated_at DATETIME NOT NULL,
  INDEX idx_wip_status (lot_status),
  INDEX idx_wip_product (product_code),
  INDEX idx_wip_fab (fab_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS production_orders (
  order_id BIGINT PRIMARY KEY,
  order_code VARCHAR(32) NOT NULL,
  product_code VARCHAR(32) NOT NULL,
  order_qty INT NOT NULL,
  completed_qty INT NOT NULL DEFAULT 0,
  defect_qty INT NOT NULL DEFAULT 0,
  rework_qty INT NOT NULL DEFAULT 0,
  order_type VARCHAR(16) NOT NULL DEFAULT 'normal',
  priority VARCHAR(8) NOT NULL DEFAULT 'P3',
  plan_start DATETIME NOT NULL,
  plan_end DATETIME NOT NULL,
  actual_start DATETIME DEFAULT NULL,
  actual_end DATETIME DEFAULT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'pending',
  cost_center VARCHAR(16) NOT NULL,
  created_by VARCHAR(32) NOT NULL,
  created_at DATETIME NOT NULL,
  notes TEXT DEFAULT NULL,
  INDEX idx_po_status (status),
  INDEX idx_po_product (product_code),
  INDEX idx_po_priority (priority)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS equipment_metrics (
  metric_id BIGINT PRIMARY KEY,
  equipment_code VARCHAR(32) NOT NULL,
  equipment_type VARCHAR(32) NOT NULL,
  fab_id VARCHAR(8) NOT NULL,
  collect_time DATETIME NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'running',
  temperature DECIMAL(5,2) DEFAULT NULL,
  pressure DECIMAL(6,2) DEFAULT NULL,
  power DECIMAL(8,2) DEFAULT NULL,
  gas_flow DECIMAL(8,2) DEFAULT NULL,
  vibration DECIMAL(4,2) DEFAULT NULL,
  oee_percent DECIMAL(5,2) DEFAULT NULL,
  throughput INT DEFAULT NULL,
  downtime_minutes INT DEFAULT 0,
  operator VARCHAR(32) DEFAULT NULL,
  notes VARCHAR(256) DEFAULT NULL,
  INDEX idx_eqp_code (equipment_code),
  INDEX idx_eqp_fab (fab_id),
  INDEX idx_eqp_time (collect_time),
  INDEX idx_eqp_type (equipment_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS quality_inspections (
  inspect_id BIGINT PRIMARY KEY,
  lot_id BIGINT NOT NULL,
  inspect_stage VARCHAR(32) NOT NULL,
  sample_size INT NOT NULL,
  pass_qty INT NOT NULL,
  fail_qty INT NOT NULL,
  defect_type VARCHAR(32) NOT NULL DEFAULT 'none',
  defect_detail VARCHAR(256) DEFAULT NULL,
  yield_rate DECIMAL(5,2) NOT NULL,
  inspector VARCHAR(32) NOT NULL,
  inspect_time DATETIME NOT NULL,
  is_final TINYINT(1) NOT NULL DEFAULT 0,
  INDEX idx_qi_lot (lot_id),
  INDEX idx_qi_defect (defect_type),
  INDEX idx_qi_yield (yield_rate)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS suppliers (
  supplier_id INT PRIMARY KEY,
  supplier_code VARCHAR(16) NOT NULL,
  supplier_name VARCHAR(64) NOT NULL,
  category VARCHAR(32) NOT NULL,
  tier VARCHAR(8) NOT NULL DEFAULT 'B',
  province VARCHAR(16) NOT NULL,
  city VARCHAR(16) NOT NULL,
  contact_person VARCHAR(32) NOT NULL,
  contact_phone VARCHAR(16) NOT NULL,
  coop_start DATE NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  last_audit_score DECIMAL(4,2) DEFAULT NULL,
  INDEX idx_supplier_tier (tier),
  INDEX idx_supplier_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS purchase_orders (
  po_id BIGINT PRIMARY KEY,
  po_code VARCHAR(32) NOT NULL,
  supplier_id INT NOT NULL,
  material_code VARCHAR(32) NOT NULL,
  material_name VARCHAR(64) NOT NULL,
  category VARCHAR(32) NOT NULL,
  unit_price DECIMAL(10,2) NOT NULL,
  order_qty DECIMAL(10,2) NOT NULL,
  received_qty DECIMAL(10,2) NOT NULL DEFAULT 0,
  defect_qty DECIMAL(10,2) NOT NULL DEFAULT 0,
  total_amount DECIMAL(14,2) NOT NULL,
  order_date DATE NOT NULL,
  expected_date DATE NOT NULL,
  actual_receive_date DATE DEFAULT NULL,
  payment_terms VARCHAR(32) NOT NULL DEFAULT 'Net 60',
  status VARCHAR(16) NOT NULL DEFAULT 'pending',
  purchaser VARCHAR(32) NOT NULL,
  INDEX idx_po_supplier (supplier_id),
  INDEX idx_po_status (status),
  INDEX idx_po_category (category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS cost_transactions (
  txn_id BIGINT PRIMARY KEY,
  cost_center VARCHAR(16) NOT NULL,
  product_code VARCHAR(32) NOT NULL,
  txn_date DATE NOT NULL,
  cost_category VARCHAR(32) NOT NULL,
  amount DECIMAL(14,2) NOT NULL,
  currency VARCHAR(8) NOT NULL DEFAULT 'CNY',
  source_type VARCHAR(32) NOT NULL,
  reference_id VARCHAR(32) DEFAULT NULL,
  description VARCHAR(256) DEFAULT NULL,
  created_at DATETIME NOT NULL,
  INDEX idx_cost_cc (cost_center),
  INDEX idx_cost_product (product_code),
  INDEX idx_cost_date (txn_date),
  INDEX idx_cost_cat (cost_category)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS customers (
  customer_id INT PRIMARY KEY,
  customer_code VARCHAR(16) NOT NULL,
  customer_name VARCHAR(64) NOT NULL,
  industry VARCHAR(32) NOT NULL,
  province VARCHAR(16) NOT NULL,
  city VARCHAR(16) NOT NULL,
  credit_rating VARCHAR(8) NOT NULL DEFAULT 'A',
  sales_person VARCHAR(32) NOT NULL,
  coop_start DATE NOT NULL,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  INDEX idx_customer_industry (industry),
  INDEX idx_customer_rating (credit_rating)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sales_orders (
  order_id BIGINT PRIMARY KEY,
  order_code VARCHAR(32) NOT NULL,
  customer_id INT NOT NULL,
  product_code VARCHAR(32) NOT NULL,
  order_qty INT NOT NULL,
  unit_price DECIMAL(12,2) NOT NULL,
  total_amount DECIMAL(14,2) NOT NULL,
  order_date DATE NOT NULL,
  delivery_date DATE NOT NULL,
  actual_delivery_date DATE DEFAULT NULL,
  delivery_status VARCHAR(16) NOT NULL DEFAULT 'pending',
  payment_status VARCHAR(16) NOT NULL DEFAULT 'unpaid',
  sales_channel VARCHAR(16) NOT NULL DEFAULT 'direct',
  priority VARCHAR(8) NOT NULL DEFAULT 'P3',
  notes TEXT DEFAULT NULL,
  INDEX idx_so_customer (customer_id),
  INDEX idx_so_product (product_code),
  INDEX idx_so_date (order_date),
  INDEX idx_so_status (delivery_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
""".strip()


# ──────────────────────────────────────────────
# 数据生成函数
# ──────────────────────────────────────────────

def seed_suppliers(conn: pymysql.connections.Connection, rng: random.Random, target_count: int) -> int:
    """生成供应商数据"""
    with conn.cursor() as cur:
        start_id = next_id(cur, "suppliers", "supplier_id")
        names_provinces = [
            ("苏州晶方半导体科技有限公司", "Silicon Wafer", "B", "江苏", "苏州"),
            ("上海先进半导体制造有限公司", "Silicon Wafer", "B", "上海", "上海"),
            ("杭州士兰微电子股份有限公司", "Parts", "B", "浙江", "杭州"),
            ("上海贝岭股份有限公司", "Parts", "B", "上海", "上海"),
            ("北京华大九天科技股份有限公司", "Parts", "A", "北京", "北京"),
            ("深圳市长盈精密技术股份有限公司", "Packaging", "B", "广东", "深圳"),
            ("深圳市兴森快捷电路科技有限公司", "Packaging", "B", "广东", "深圳"),
            ("上海华虹半导体有限公司", "Silicon Wafer", "A", "上海", "上海"),
            ("无锡华润微电子有限公司", "Silicon Wafer", "A", "江苏", "无锡"),
            ("上海韦尔半导体股份有限公司", "Parts", "A", "上海", "上海"),
            ("江苏长电科技（宿迁）有限公司", "Packaging", "B", "江苏", "宿迁"),
            ("天水华天科技（西安）有限公司", "Packaging", "B", "陕西", "西安"),
            ("宁波江丰电子材料股份有限公司", "Parts", "A", "浙江", "宁波"),
            ("上海合晶硅材料股份有限公司", "Silicon Wafer", "A", "上海", "上海"),
            ("重庆超硅半导体有限公司", "Silicon Wafer", "B", "重庆", "重庆"),
            ("有研半导体材料股份有限公司", "Silicon Wafer", "B", "北京", "北京"),
            ("上海天岳半导体材料有限公司", "Silicon Wafer", "B", "上海", "上海"),
            ("中国石油化工股份有限公司", "Gas", "B", "北京", "北京"),
            ("空气化工产品（中国）投资有限公司", "Gas", "A", "上海", "上海"),
            ("美国气体（中国）有限公司", "Gas", "B", "上海", "上海"),
        ]
        all_names_etc = SUPPLIER_DATA + names_provinces

        categories = ["Silicon Wafer", "Photoresist", "Gas", "Parts", "Packaging"]
        tiers = ["A", "B", "C"]

        rows = []
        for i, (sname, cat, tier, prov, cty) in enumerate(all_names_etc):
            sid = start_id + i
            code = f"S_{''.join(c for c in sname if c.isascii())[:8] or f'SUP{sid}'}"
            contact = rng.choice(["张经理", "李经理", "王经理", "陈经理", "刘经理"])
            phone = f"1{rng.choice(['38','39','58','59','86','87'])}{rng.randint(10000000,99999999)}"
            coop_start = date.today() - timedelta(days=rng.randint(365, 2000))
            score = round(rng.uniform(65, 99), 2)
            rows.append((sid, code, sname, cat, tier, prov, cty, contact, phone, coop_start, "active", score))

        # 生成更多到 target_count
        while start_id + len(rows) < target_count:
            sid = start_id + len(rows)
            cat = rng.choice(categories)
            tier = rng.choices(tiers, weights=[0.3, 0.5, 0.2])[0]
            prov = rng.choice(["广东", "江苏", "浙江", "上海", "北京", "四川", "湖北", "安徽", "福建", "山东"])
            cty = prov  # simplified
            name = f"{cty}半导体材料供应商{sid}"
            code = f"SUP{sid}"
            contact = rng.choice(["张经理", "李经理", "王经理", "陈经理", "刘经理"])
            phone = f"1{rng.choice(['38','39','58','59','86','87'])}{rng.randint(10000000,99999999)}"
            coop_start = date.today() - timedelta(days=rng.randint(365, 2000))
            score = round(rng.uniform(65, 99), 2)
            rows.append((sid, code, name, cat, tier, prov, cty, contact, phone, coop_start, "active", score))

        # 少数标记为 suspended
        for r in rows:
            if rng.random() < 0.05:
                rows[rows.index(r)] = (*r[:9], r[9], "suspended", r[11])

        inserted = len(rows)
        cur.executemany(
            "INSERT INTO suppliers (supplier_id, supplier_code, supplier_name, category, tier, "
            "province, city, contact_person, contact_phone, coop_start, status, last_audit_score) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            rows,
        )
        conn.commit()
        return inserted


def seed_customers(conn: pymysql.connections.Connection, rng: random.Random) -> int:
    """生成客户数据"""
    with conn.cursor() as cur:
        start_id = next_id(cur, "customers", "customer_id")
        industries = ["Automotive", "ConsumerElectronics", "Industrial", "Medical"]
        ratings = ["AA", "A", "B", "C"]
        rows = []
        for i, (cname, industry, prov, cty, rating) in enumerate(CUSTOMER_DATA):
            cid = start_id + i
            code = f"C_{''.join(w[0] for w in cname.split('（')[0].split()) if cname.split('（')[0].isascii() else f'CUS{cid}'}"
            sales = rng.choice(SALES_REPS)
            coop_start = date.today() - timedelta(days=rng.randint(365, 2200))
            rows.append((cid, code, cname, industry, prov, cty, rating, sales, coop_start, "active"))

        inserted = len(rows)
        cur.executemany(
            "INSERT INTO customers (customer_id, customer_code, customer_name, industry, "
            "province, city, credit_rating, sales_person, coop_start, status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            rows,
        )
        conn.commit()
        return inserted


def seed_wip_lots(conn: pymysql.connections.Connection, rng: random.Random, count: int) -> int:
    """生成在制晶圆批次"""
    with conn.cursor() as cur:
        start_id = next_id(cur, "wip_lots", "lot_id")
        rows = []
        lot_statuses = ["active", "hold", "completed", "scrapped"]

        for i in range(count):
            lot_id = start_id + i
            product_code = rng.choice(PRODUCT_CODE_LIST)
            route = PROCESS_ROUTES[product_code]
            total_stages = len(route)
            scode = product_code.split("-")[0]

            # 批次完成情况
            is_completed = rng.random() < 0.35
            is_hold = not is_completed and rng.random() < 0.08
            is_scrapped = not is_completed and not is_hold and rng.random() < 0.03

            if is_completed:
                status = "completed"
                current_idx = total_stages - 1
            elif is_scrapped:
                status = "scrapped"
                current_idx = rng.randint(2, total_stages - 2)
            elif is_hold:
                status = "hold"
                current_idx = rng.randint(0, total_stages - 1)
            else:
                status = "active"
                current_idx = rng.randint(0, total_stages - 2)

            current_stage = route[current_idx] if current_idx < total_stages else route[-1]
            stage_seq = current_idx + 1
            fab_id = rng.choice(FAB_FE)
            operator = rng.choice(OPERATORS)

            # 时间范围：当前批次在过去 120 天内
            if is_completed:
                start_day = rng.randint(30, 120)
                start = date.today() - timedelta(days=start_day)
                start_dt = datetime(start.year, start.month, start.day, rng.randint(6, 22), rng.randint(0, 59))
                cycle_days = rng.randint(int(total_stages * 0.5), int(total_stages * 1.5))
                end_dt = start_dt + timedelta(days=cycle_days, hours=rng.randint(0, 12))
                est_end = end_dt
                actual_end = end_dt
            else:
                start_day = rng.randint(1, 60)
                start = date.today() - timedelta(days=start_day)
                start_dt = datetime(start.year, start.month, start.day, rng.randint(6, 22), rng.randint(0, 59))
                remaining_stages = total_stages - stage_seq
                cycle_days = rng.randint(max(1, int(remaining_stages * 0.3)), max(2, int(remaining_stages * 1.2)))
                est_end = start_dt + timedelta(days=cycle_days, hours=rng.randint(0, 12))
                actual_end = None

            qty_input = rng.choices([25, 25, 25, 25, 50, 50, 100], weights=[30, 30, 20, 10, 5, 3, 2])[0]
            scrap_pct = rng.uniform(0, 0.12)
            if is_scrapped:
                scrap_pct = max(scrap_pct, 0.20)
            qty_scrap = max(0, int(qty_input * scrap_pct))
            hold_pct = rng.uniform(0, 0.05) if status != "hold" else rng.uniform(0.05, 0.30)
            qty_hold = max(0, int(qty_input * hold_pct))
            qty_output = max(0, qty_input - qty_scrap - qty_hold)

            lot_code = f"WLP-{start_dt.strftime('%Y%m%d')}-{scode}{lot_id % 10000:04d}"
            updated_at = (end_dt if is_completed else datetime.now()) - timedelta(hours=rng.randint(0, 24))

            rows.append((
                lot_id, lot_code, product_code, f"ROUTE_{product_code}",
                current_stage, stage_seq, total_stages,
                qty_input, qty_output, qty_hold, qty_scrap,
                status, fab_id, operator, start_dt, est_end,
                actual_end, updated_at,
            ))

        cur.executemany(
            "INSERT INTO wip_lots (lot_id, lot_code, product_code, route_code, "
            "current_stage, stage_seq, total_stages, "
            "qty_input, qty_output, qty_hold, qty_scrap, "
            "lot_status, fab_id, operator, start_time, est_end_time, "
            "actual_end_time, updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            rows,
        )
        conn.commit()
        return len(rows)


def seed_production_orders(conn: pymysql.connections.Connection, rng: random.Random, count: int) -> int:
    """生成工单"""
    with conn.cursor() as cur:
        start_id = next_id(cur, "production_orders", "order_id")
        rows = []
        order_types = ["normal", "normal", "normal", "pilot", "rework"]
        priorities = ["P1", "P2", "P3"]
        statuses = ["pending", "running", "completed", "delayed", "cancelled"]
        status_weights = [0.10, 0.15, 0.50, 0.15, 0.10]

        for i in range(count):
            oid = start_id + i
            product_code = rng.choice(PRODUCT_CODE_LIST)
            scode = product_code.split("-")[0]
            otype = rng.choice(order_types)
            pri = rng.choices(priorities, weights=[0.15, 0.25, 0.60])[0]
            status = rng.choices(statuses, weights=status_weights)[0]
            cost_center = rng.choice(COST_CENTERS)[0]

            start_dt = random_datetime_range(rng, 365, 1)
            plan_days = rng.randint(5, 20)
            plan_end = start_dt + timedelta(days=plan_days)
            order_qty = rng.choices([500, 1000, 1000, 2000, 3000, 5000], weights=[20, 30, 20, 15, 10, 5])[0]

            if status == "completed":
                actual_start = start_dt
                actual_end = start_dt + timedelta(days=rng.randint(plan_days - 3, plan_days + 5))
                completed_qty = order_qty - rng.randint(0, int(order_qty * 0.10))
            elif status == "running":
                actual_start = start_dt
                actual_end = None
                completed_qty = rng.randint(int(order_qty * 0.2), int(order_qty * 0.8))
            elif status == "delayed":
                actual_start = start_dt + timedelta(days=1)
                actual_end = None
                completed_qty = rng.randint(int(order_qty * 0.3), int(order_qty * 0.7))
            elif status == "cancelled":
                actual_start = start_dt + timedelta(days=rng.randint(0, 3))
                actual_end = start_dt + timedelta(days=rng.randint(1, plan_days))
                completed_qty = rng.randint(0, int(order_qty * 0.3))
            else:  # pending
                actual_start = None
                actual_end = None
                completed_qty = 0

            defect_qty = rng.randint(0, max(1, int(completed_qty * 0.03)))
            rework_qty = rng.randint(0, max(1, int(defect_qty * 0.5)))
            created_by = rng.choice(["王明", "李华", "张伟", "刘静", "陈志远"])
            notes = "" if rng.random() > 0.15 else f"备注：{rng.choice(['紧急插单', '客户加急', '工艺验证批次', '工程变更'])}"

            order_code = f"PO-{start_dt.strftime('%Y%m')}-{oid % 100000:05d}"
            rows.append((
                oid, order_code, product_code, order_qty, completed_qty,
                defect_qty, rework_qty, otype, pri,
                start_dt, plan_end, actual_start, actual_end,
                status, cost_center, created_by, start_dt, notes or None,
            ))

        cur.executemany(
            "INSERT INTO production_orders (order_id, order_code, product_code, order_qty, "
            "completed_qty, defect_qty, rework_qty, order_type, priority, "
            "plan_start, plan_end, actual_start, actual_end, status, "
            "cost_center, created_by, created_at, notes) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            rows,
        )
        conn.commit()
        return len(rows)


def seed_equipment_metrics(conn: pymysql.connections.Connection, rng: random.Random, count: int) -> int:
    """生成设备运行指标"""
    with conn.cursor() as cur:
        start_id = next_id(cur, "equipment_metrics", "metric_id")
        rows = []

        # 每个设备约产生 count/len(ALL_EQUIPMENT) 条数据
        per_eq = max(1, count // len(ALL_EQUIPMENT))
        total_generated = 0

        for eq_code, eq_type, fab_id in ALL_EQUIPMENT:
            # 生成 per_eq 条记录，分布在 90 天内
            base_time = datetime.now() - timedelta(days=90)
            for j in range(per_eq):
                if total_generated >= count:
                    break
                metric_id = start_id + total_generated
                collect_time = base_time + timedelta(
                    hours=rng.randint(0, 90 * 24 - 1),
                    minutes=rng.randint(0, 59),
                )

                # 设备状态分布
                status = rng.choices(
                    ["running", "idle", "maintenance", "downtime", "setup"],
                    weights=[0.65, 0.12, 0.08, 0.08, 0.07],
                )[0]

                if status == "running":
                    temp = round(rng.uniform(120, 180), 2)
                    pressure = round(rng.uniform(15, 60), 2)
                    power = round(rng.uniform(400, 1200), 2)
                    gas_flow = round(rng.uniform(50, 250), 2)
                    vibration = round(rng.uniform(0.3, 3.0), 2)
                    oee = round(rng.uniform(72, 98), 2)
                    throughput = rng.randint(10, 120)
                    downtime = 0
                    notes = ""
                elif status in ("maintenance", "downtime"):
                    temp = round(rng.uniform(20, 180), 2)
                    pressure = round(rng.uniform(0, 60), 2)
                    power = 0
                    gas_flow = 0
                    vibration = round(rng.uniform(0.1, 1.0), 2)
                    oee = 0
                    throughput = 0
                    downtime = rng.randint(30, 480)
                    notes = rng.choice([
                        "", "计划保养", "PM 维护", "紧急维修",
                        "更换零件中", "待机等待",
                    ])
                elif status == "idle":
                    temp = round(rng.uniform(20, 50), 2)
                    pressure = round(rng.uniform(0, 5), 2)
                    power = round(rng.uniform(0, 100), 2)
                    gas_flow = 0
                    vibration = round(rng.uniform(0.1, 0.5), 2)
                    oee = 0
                    throughput = 0
                    downtime = 0
                    notes = "待料中" if rng.random() > 0.5 else ""
                else:  # setup
                    temp = round(rng.uniform(20, 100), 2)
                    pressure = round(rng.uniform(0, 20), 2)
                    power = round(rng.uniform(0, 400), 2)
                    gas_flow = round(rng.uniform(0, 50), 2)
                    vibration = round(rng.uniform(0.1, 1.0), 2)
                    oee = 0
                    throughput = 0
                    downtime = 0
                    notes = "换型中"

                operator = rng.choice(OPERATORS) if status == "running" else ""

                rows.append((
                    metric_id, eq_code, eq_type, fab_id, collect_time, status,
                    temp, pressure, power, gas_flow, vibration,
                    oee, throughput, downtime, operator, notes or None,
                ))
                total_generated += 1

            if total_generated >= count:
                break

        cur.executemany(
            "INSERT INTO equipment_metrics (metric_id, equipment_code, equipment_type, fab_id, "
            "collect_time, status, temperature, pressure, power, gas_flow, "
            "vibration, oee_percent, throughput, downtime_minutes, operator, notes) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            rows,
        )
        conn.commit()
        return len(rows)


def seed_quality_inspections(conn: pymysql.connections.Connection, rng: random.Random, count: int) -> int:
    """生成质量检验记录"""
    with conn.cursor() as cur:
        start_id = next_id(cur, "quality_inspections", "inspect_id")

        # 先获取所有 lot_id
        cur.execute("SELECT lot_id, product_code, lot_status FROM wip_lots ORDER BY lot_id")
        lots = cur.fetchall()
        if not lots:
            return 0

        rows = []
        inspection_stages = [
            "INSPECT_AFTER_DEP", "INSPECT_AFTER_PHOTO", "INSPECT_AFTER_ETCH",
            "INSPECT_AFTER_CMP", "INSPECT_AFTER_PACKAGE", "INSPECT_FINAL",
        ]

        for i in range(count):
            inspect_id = start_id + i
            lot = rng.choice(lots)
            lot_id = lot["lot_id"]
            is_final_lot = lot["lot_status"] == "completed"

            stage = rng.choice(inspection_stages)
            is_final = 1 if (stage == "INSPECT_FINAL" or (is_final_lot and rng.random() > 0.7)) else 0

            sample_size = rng.choices([5, 10, 10, 20, 30, 50], weights=[10, 25, 20, 25, 15, 5])[0]
            # 良率：大部分在85-99.5%，少数低良率
            if rng.random() < 0.1:
                yield_rate = round(rng.uniform(60, 84), 2)
            elif rng.random() < 0.3:
                yield_rate = round(rng.uniform(85, 94), 2)
            else:
                yield_rate = round(rng.uniform(95, 99.8), 2)

            pass_qty = max(0, int(sample_size * yield_rate / 100))
            fail_qty = sample_size - pass_qty

            if fail_qty > 0:
                defect_type = rng.choices(
                    DEFECT_TYPES[:-1],  # exclude 'none'
                    weights=[0.35, 0.20, 0.25, 0.20],
                )[0]
                defect_detail = {
                    "particle": "Particle contamination at edge",
                    "scratch": "Scratch on wafer surface",
                    "thickness_err": "Film thickness out of spec",
                    "electrical": "Electrical test failure - open circuit",
                }[defect_type]
            else:
                defect_type = "none"
                defect_detail = ""

            inspector = rng.choice(INSPECTORS)
            inspect_time = random_datetime_range(rng, 365, 1)

            rows.append((
                inspect_id, lot_id, stage, sample_size, pass_qty, fail_qty,
                defect_type, defect_detail, yield_rate, inspector, inspect_time, is_final,
            ))

        cur.executemany(
            "INSERT INTO quality_inspections (inspect_id, lot_id, inspect_stage, sample_size, "
            "pass_qty, fail_qty, defect_type, defect_detail, yield_rate, "
            "inspector, inspect_time, is_final) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            rows,
        )
        conn.commit()
        return len(rows)


def seed_purchase_orders(conn: pymysql.connections.Connection, rng: random.Random, count: int) -> int:
    """生成采购订单"""
    with conn.cursor() as cur:
        start_id = next_id(cur, "purchase_orders", "po_id")

        cur.execute("SELECT supplier_id, category, supplier_name FROM suppliers WHERE status='active'")
        suppliers = cur.fetchall()
        if not suppliers:
            return 0

        material_catalog = {
            "Silicon Wafer": [
                ("SW-8INCH-P100", "8英寸抛光硅片", 850.00),
                ("SW-8INCH-P200", "8英寸外延硅片", 1200.00),
                ("SW-12INCH-P100", "12英寸抛光硅片", 1800.00),
                ("SW-6INCH-SOI", "6英寸 SOI 硅片", 2500.00),
            ],
            "Photoresist": [
                ("PR-I-LINE-01", "I-line 光刻胶", 3500.00),
                ("PR-KRF-01", "KrF 光刻胶", 5800.00),
                ("PR-ARF-01", "ArF 光刻胶", 9200.00),
            ],
            "Gas": [
                ("GAS-N2-01", "高纯氮气(瓶)", 350.00),
                ("GAS-O2-01", "高纯氧气(瓶)", 420.00),
                ("GAS-AR-01", "高纯氩气(瓶)", 680.00),
                ("GAS-CF4-01", "CF4 刻蚀气体(瓶)", 2800.00),
            ],
            "Parts": [
                ("PRT-QUARTZ-01", "石英窗口", 15000.00),
                ("PRT-RING-01", "聚焦环", 8500.00),
                ("PRT-ELECTRODE-01", "静电卡盘", 45000.00),
                ("PRT-FILTER-01", "HEPA 过滤器", 1200.00),
            ],
            "Packaging": [
                ("PKG-SUBSTRATE-01", "BGA 基板(卷)", 3500.00),
                ("PKG-LEADFRAME-01", "引线框架(卷)", 2800.00),
                ("PKG-EPOXY-01", "环氧树脂(kg)", 650.00),
                ("PKG-BONDWIRE-01", "键合丝(卷)", 4200.00),
            ],
        }

        payment_terms_list = ["Net 30", "Net 60", "Net 90", "预付"]
        statuses = ["pending", "partial", "received", "closed", "cancelled"]
        status_weights = [0.15, 0.15, 0.35, 0.25, 0.10]

        rows = []
        for i in range(count):
            po_id = start_id + i
            sup = rng.choice(suppliers)
            cat = sup["category"]
            catalog = material_catalog.get(cat, material_catalog["Parts"])
            mat_code, mat_name, unit_price = rng.choice(catalog)

            order_qty = round(rng.uniform(10, 2000), 2) if cat in ("Gas",) else rng.randint(100, 5000)
            total_amount = round(unit_price * order_qty, 2)
            status = rng.choices(statuses, weights=status_weights)[0]

            order_date = random_date_365(rng)
            expected_date = order_date + timedelta(days=rng.randint(7, 45))

            if status in ("received", "closed"):
                received_qty = order_qty
                actual_receive = expected_date + timedelta(days=rng.randint(-3, 10))
                defect_qty = round(order_qty * rng.uniform(0, 0.02), 2)
            elif status == "partial":
                received_qty = round(order_qty * rng.uniform(0.2, 0.9), 2)
                actual_receive = expected_date + timedelta(days=rng.randint(-2, 5))
                defect_qty = round(received_qty * rng.uniform(0, 0.02), 2)
            else:
                received_qty = 0
                actual_receive = None
                defect_qty = 0

            if actual_receive and actual_receive > date.today():
                actual_receive = date.today() - timedelta(days=rng.randint(1, 5))

            purchaser = rng.choice(PURCHASERS)
            payment_terms = rng.choice(payment_terms_list)

            po_code = f"PO-{order_date.strftime('%Y-%m')}-{po_id % 100000:05d}"
            rows.append((
                po_id, po_code, sup["supplier_id"], mat_code, mat_name, cat,
                unit_price, order_qty, received_qty, defect_qty, total_amount,
                order_date, expected_date, actual_receive, payment_terms, status, purchaser,
            ))

        cur.executemany(
            "INSERT INTO purchase_orders (po_id, po_code, supplier_id, material_code, material_name, "
            "category, unit_price, order_qty, received_qty, defect_qty, total_amount, "
            "order_date, expected_date, actual_receive_date, payment_terms, status, purchaser) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            rows,
        )
        conn.commit()
        return len(rows)


def seed_cost_transactions(conn: pymysql.connections.Connection, rng: random.Random, count: int) -> int:
    """生成成本交易明细"""
    with conn.cursor() as cur:
        start_id = next_id(cur, "cost_transactions", "txn_id")

        source_types = {
            "material": "po_allocation",
            "labor": "labor_actual",
            "depreciation": "depreciation_schedule",
            "utilities": "utility_bill",
            "maintenance": "maintenance_work_order",
        }

        # 每种成本类别的大致金额范围
        amount_ranges = {
            "material": (50000, 800000),
            "labor": (30000, 300000),
            "depreciation": (100000, 600000),
            "utilities": (20000, 150000),
            "maintenance": (10000, 200000),
        }

        rows = []
        # 每天每个成本中心产生多笔
        days = 365
        per_day_target = max(1, count // (len(COST_CENTERS) * days))

        total_generated = 0
        for day_offset in range(days):
            if total_generated >= count:
                break
            txn_date = date.today() - timedelta(days=days - day_offset - 1)
            for cc_code, cc_name, fab in COST_CENTERS:
                if total_generated >= count:
                    break
                # 每天每个成本中心产生 1-2 笔成本交易
                num_txns = rng.randint(1, 3)
                for _ in range(min(num_txns, count - total_generated)):
                    txn_id = start_id + total_generated
                    product_code = rng.choice(PRODUCT_CODE_LIST)
                    cost_cat = rng.choices(COST_CATEGORIES, weights=[0.30, 0.20, 0.25, 0.15, 0.10])[0]
                    amount = round(rng.uniform(*amount_ranges[cost_cat]), 2)
                    source = source_types[cost_cat]

                    desc = {
                        "material": f"{cc_name} {txn_date} 材料成本分摊",
                        "labor": f"{cc_name} {txn_date} 直接人工",
                        "depreciation": f"{cc_name} {txn_date} 设备折旧",
                        "utilities": f"{cc_name} {txn_date} 水电动力",
                        "maintenance": f"{cc_name} {txn_date} 设备维护",
                    }[cost_cat]

                    created_at = datetime(txn_date.year, txn_date.month, txn_date.day,
                                          rng.randint(17, 23), rng.randint(0, 59))
                    rows.append((
                        txn_id, cc_code, product_code, txn_date, cost_cat, amount,
                        "CNY", source, f"REF-{txn_date.strftime('%Y%m%d')}-{cc_code}",
                        desc, created_at,
                    ))
                    total_generated += 1

        cur.executemany(
            "INSERT INTO cost_transactions (txn_id, cost_center, product_code, txn_date, "
            "cost_category, amount, currency, source_type, reference_id, description, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            rows,
        )
        conn.commit()
        return len(rows)


def seed_sales_orders(conn: pymysql.connections.Connection, rng: random.Random, count: int) -> int:
    """生成销售订单"""
    with conn.cursor() as cur:
        start_id = next_id(cur, "sales_orders", "order_id")

        cur.execute("SELECT customer_id, credit_rating, sales_person FROM customers WHERE status='active'")
        customers = cur.fetchall()
        if not customers:
            return 0

        # 产品定价
        product_prices: dict[str, float] = {
            "MCU-C2003-QFN": 45.00,
            "MCU-C2010-LQFP": 28.50,
            "SOC-A5000-BGA": 68.00,
            "SOC-A3200-BGA": 15.80,
            "MEMS-S1000-LGA": 12.50,
            "MEMS-S2000-LGA": 8.90,
            "PMIC-P100-QFN": 5.60,
        }

        channels = ["direct", "direct", "agent", "oem"]
        delivery_statuses = ["pending", "partial", "delivered", "delayed"]
        payment_statuses = ["unpaid", "partial", "paid"]
        priorities = ["P1", "P2", "P3"]

        rows = []
        for i in range(count):
            so_id = start_id + i
            cust = rng.choice(customers)
            product_code = rng.choices(
                PRODUCT_CODE_LIST,
                weights=[0.20, 0.15, 0.20, 0.10, 0.10, 0.10, 0.15],
            )[0]
            unit_price = product_prices[product_code]
            order_qty = rng.choices(
                [100, 500, 1000, 2000, 5000, 10000, 50000],
                weights=[15, 20, 25, 15, 15, 8, 2],
            )[0]
            total_amount = round(unit_price * order_qty, 2)

            order_date = random_date_365(rng)
            delivery_date = order_date + timedelta(days=rng.randint(14, 60))
            priority = rng.choices(priorities, weights=[0.15, 0.35, 0.50])[0]

            # 高信用等级客户较少延迟
            if cust["credit_rating"] in ("AA", "A"):
                d_status = rng.choices(
                    delivery_statuses,
                    weights=[0.10, 0.15, 0.70, 0.05],
                )[0]
            else:
                d_status = rng.choices(
                    delivery_statuses,
                    weights=[0.15, 0.15, 0.50, 0.20],
                )[0]

            if d_status in ("delivered", "partial"):
                actual_delivery = delivery_date + timedelta(days=rng.randint(-5, 15))
                if actual_delivery > date.today():
                    actual_delivery = date.today() - timedelta(days=rng.randint(1, 30))
                p_status = rng.choices(
                    payment_statuses,
                    weights=[0.05, 0.15, 0.80],
                )[0]
            elif d_status == "delayed":
                actual_delivery = None
                p_status = rng.choices(payment_statuses, weights=[0.6, 0.3, 0.1])[0]
            else:
                actual_delivery = None
                p_status = rng.choices(payment_statuses, weights=[0.7, 0.2, 0.1])[0]

            channel = rng.choice(channels)
            notes = "" if rng.random() > 0.15 else rng.choice([
                "客户紧急需求", "年度框架订单", "新客户试用", "样片订单",
            ])

            order_code = f"SO-{order_date.strftime('%Y-%m')}-{so_id % 100000:05d}"
            rows.append((
                so_id, order_code, cust["customer_id"], product_code, order_qty,
                unit_price, total_amount, order_date, delivery_date, actual_delivery,
                d_status, p_status, channel, priority, notes or None,
            ))

        cur.executemany(
            "INSERT INTO sales_orders (order_id, order_code, customer_id, product_code, "
            "order_qty, unit_price, total_amount, order_date, delivery_date, actual_delivery_date, "
            "delivery_status, payment_status, sales_channel, priority, notes) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            rows,
        )
        conn.commit()
        return len(rows)


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    total_start = time.time()

    print(f"═══ 华芯半导体 - 制造业演示数据生成 ═══")
    print(f"目标数据库: {args.database}@{args.host}:{args.port}")
    print(f"随机种子: {args.seed}")
    print()

    # 连接 MySQL
    conn = pymysql.connect(
        host=args.host, port=args.port, user=args.user, password=args.password,
        charset="utf8mb4", cursorclass=DictCursor, autocommit=False,
    )

    try:
        # Step 0: 清理 & 创建数据库
        print("[1/9] 初始化数据库...")
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{args.database}`")
            cur.execute(f"CREATE DATABASE `{args.database}` DEFAULT CHARSET utf8mb4")
            cur.execute(f"USE `{args.database}`")
        conn.commit()
        print(f"  ✔ 数据库 {args.database} 已重建")

        # Step 1: 建表
        print("[2/9] 创建 9 张表...")
        with conn.cursor() as cur:
            for stmt in DDL.split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(f"USE `{args.database}`")
                    cur.execute(stmt + ";")
        conn.commit()
        print("  ✔ 所有表创建完成")

        # Step 2: 生成数据
        print()
        print("[3/9] 生成客户数据...")
        c = seed_customers(conn, rng)
        print(f"  ✔ {c} 个客户")

        print("[4/9] 生成供应商数据...")
        c = seed_suppliers(conn, rng, args.suppliers)
        print(f"  ✔ {c} 个供应商")

        print("[5/9] 生成在制批次数据...")
        c = seed_wip_lots(conn, rng, args.wip_lots)
        print(f"  ✔ {c} 条批次记录")

        print("[6/9] 生成工单数据...")
        c = seed_production_orders(conn, rng, args.prod_orders)
        print(f"  ✔ {c} 条工单记录")

        print("[7/9] 生成设备运行指标数据...")
        c = seed_equipment_metrics(conn, rng, args.eqp_metrics)
        print(f"  ✔ {c} 条设备指标记录")

        print("[8/9] 生成质量检验数据...")
        c = seed_quality_inspections(conn, rng, args.quality)
        print(f"  ✔ {c} 条检验记录")

        print("[9/9] 生成采购、成本、销售数据...")
        c1 = seed_purchase_orders(conn, rng, args.purchase_orders)
        c2 = seed_cost_transactions(conn, rng, args.cost_txns)
        c3 = seed_sales_orders(conn, rng, args.sales_orders)
        print(f"  ✔ {c1} 条采购订单")
        print(f"  ✔ {c2} 条成本交易")
        print(f"  ✔ {c3} 条销售订单")

        # 总结
        elapsed = time.time() - total_start
        print()
        print(f"═══ 生成完成 ═══")
        print(f"耗时: {elapsed:.1f} 秒")
        print(f"数据库: {args.database}")
        print(f"共计: suppliers={args.suppliers}, customers={len(CUSTOMER_DATA)}, "
              f"wip_lots={args.wip_lots}, production_orders={args.prod_orders}, "
              f"equipment_metrics={args.eqp_metrics}, quality_inspections={args.quality}, "
              f"purchase_orders={args.purchase_orders}, cost_transactions={args.cost_txns}, "
              f"sales_orders={args.sales_orders}")
        print(f"总计行数: ~{args.wip_lots + args.prod_orders + args.eqp_metrics + args.quality + args.suppliers + args.purchase_orders + args.cost_txns + len(CUSTOMER_DATA) + args.sales_orders}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
