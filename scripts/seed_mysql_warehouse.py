#!/usr/bin/env python3
from __future__ import annotations

import argparse
import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta

import pymysql


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed a warehouse-like MySQL schema/data in ecommerce database.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--database", default="ecommerce")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--extra-orders", type=int, default=15000)
    parser.add_argument("--events", type=int, default=50000)
    parser.add_argument("--seed", type=int, default=20260429)
    return parser.parse_args()


def dt_in_last_days(days: int) -> datetime:
    now = datetime.now()
    return now - timedelta(
        days=random.randint(0, days),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59),
    )


def create_schema(cur: pymysql.cursors.Cursor) -> None:
    ddl_list = [
        """
        CREATE TABLE IF NOT EXISTS dim_date (
          dt DATE PRIMARY KEY,
          year_num INT NOT NULL,
          quarter_num INT NOT NULL,
          month_num INT NOT NULL,
          day_num INT NOT NULL,
          week_num INT NOT NULL,
          is_weekend TINYINT(1) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS dim_region (
          region_id INT PRIMARY KEY,
          province VARCHAR(32) NOT NULL,
          city VARCHAR(32) NOT NULL,
          city_tier VARCHAR(16) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS dim_channel (
          channel_id INT PRIMARY KEY,
          channel_name VARCHAR(32) NOT NULL,
          source_type VARCHAR(32) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS dim_campaign (
          campaign_id INT PRIMARY KEY,
          campaign_name VARCHAR(64) NOT NULL,
          channel_id INT NOT NULL,
          campaign_type VARCHAR(32) NOT NULL,
          start_date DATE NOT NULL,
          end_date DATE NOT NULL,
          INDEX idx_dim_campaign_channel_id (channel_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS dim_store (
          store_id INT PRIMARY KEY,
          store_name VARCHAR(64) NOT NULL,
          region_id INT NOT NULL,
          store_type VARCHAR(16) NOT NULL,
          open_date DATE NOT NULL,
          INDEX idx_dim_store_region_id (region_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS dim_supplier (
          supplier_id INT PRIMARY KEY,
          supplier_name VARCHAR(64) NOT NULL,
          supplier_level VARCHAR(16) NOT NULL,
          cooperation_start DATE NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS dim_product (
          product_id BIGINT PRIMARY KEY,
          product_name VARCHAR(128) NOT NULL,
          category VARCHAR(64) NOT NULL,
          brand VARCHAR(64) NOT NULL,
          supplier_id INT NOT NULL,
          is_self_operated TINYINT(1) NOT NULL,
          launch_date DATE NOT NULL,
          list_price DECIMAL(10,2) NOT NULL,
          INDEX idx_dim_product_category (category),
          INDEX idx_dim_product_supplier_id (supplier_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS fct_order_dwd (
          order_id BIGINT PRIMARY KEY,
          order_datetime DATETIME NOT NULL,
          order_date DATE NOT NULL,
          user_id BIGINT NOT NULL,
          product_id BIGINT NOT NULL,
          region_id INT NOT NULL,
          channel_id INT NOT NULL,
          campaign_id INT NOT NULL,
          store_id INT NOT NULL,
          order_amt DECIMAL(12,2) NOT NULL,
          status VARCHAR(32) NOT NULL,
          INDEX idx_fct_order_dwd_order_date (order_date),
          INDEX idx_fct_order_dwd_user_id (user_id),
          INDEX idx_fct_order_dwd_product_id (product_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS fct_payment_dwd (
          payment_id BIGINT PRIMARY KEY,
          order_id BIGINT NOT NULL,
          pay_datetime DATETIME NOT NULL,
          pay_date DATE NOT NULL,
          pay_method VARCHAR(32) NOT NULL,
          pay_amt DECIMAL(12,2) NOT NULL,
          pay_status VARCHAR(32) NOT NULL,
          INDEX idx_fct_payment_dwd_order_id (order_id),
          INDEX idx_fct_payment_dwd_pay_date (pay_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS fct_refund_dwd (
          refund_id BIGINT PRIMARY KEY,
          order_id BIGINT NOT NULL,
          refund_datetime DATETIME NOT NULL,
          refund_date DATE NOT NULL,
          refund_amt DECIMAL(12,2) NOT NULL,
          refund_reason VARCHAR(64) NOT NULL,
          INDEX idx_fct_refund_dwd_order_id (order_id),
          INDEX idx_fct_refund_dwd_refund_date (refund_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS fct_user_event_dwd (
          event_id BIGINT PRIMARY KEY,
          event_datetime DATETIME NOT NULL,
          event_date DATE NOT NULL,
          user_id BIGINT NOT NULL,
          product_id BIGINT,
          channel_id INT NOT NULL,
          event_type VARCHAR(32) NOT NULL,
          event_page VARCHAR(64) NOT NULL,
          INDEX idx_fct_user_event_dwd_event_date (event_date),
          INDEX idx_fct_user_event_dwd_user_id (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS fct_inventory_snapshot_dwd (
          dt DATE NOT NULL,
          product_id BIGINT NOT NULL,
          store_id INT NOT NULL,
          on_hand_qty INT NOT NULL,
          reserved_qty INT NOT NULL,
          in_transit_qty INT NOT NULL,
          PRIMARY KEY (dt, product_id, store_id),
          INDEX idx_fct_inventory_snapshot_dwd_product_id (product_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS dws_product_sales_1d (
          dt DATE NOT NULL,
          product_id BIGINT NOT NULL,
          order_cnt INT NOT NULL,
          paid_order_cnt INT NOT NULL,
          gmv DECIMAL(14,2) NOT NULL,
          refund_amt DECIMAL(14,2) NOT NULL,
          PRIMARY KEY (dt, product_id),
          INDEX idx_dws_product_sales_1d_product_id (product_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS dws_region_sales_1d (
          dt DATE NOT NULL,
          region_id INT NOT NULL,
          order_cnt INT NOT NULL,
          buyer_cnt INT NOT NULL,
          gmv DECIMAL(14,2) NOT NULL,
          PRIMARY KEY (dt, region_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS dws_channel_conversion_1d (
          dt DATE NOT NULL,
          channel_id INT NOT NULL,
          uv BIGINT NOT NULL,
          add_cart_cnt BIGINT NOT NULL,
          pay_order_cnt BIGINT NOT NULL,
          conversion_rate DECIMAL(10,4) NOT NULL,
          PRIMARY KEY (dt, channel_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS dws_user_rfm (
          user_id BIGINT PRIMARY KEY,
          recency_days INT NOT NULL,
          frequency_90d INT NOT NULL,
          monetary_90d DECIMAL(14,2) NOT NULL,
          rfm_segment VARCHAR(32) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
        """
        CREATE TABLE IF NOT EXISTS ads_kpi_dashboard_1d (
          dt DATE PRIMARY KEY,
          order_cnt INT NOT NULL,
          paid_order_cnt INT NOT NULL,
          gmv DECIMAL(14,2) NOT NULL,
          refund_amt DECIMAL(14,2) NOT NULL,
          uv BIGINT NOT NULL,
          pay_conversion_rate DECIMAL(10,4) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """,
    ]

    for ddl in ddl_list:
        cur.execute(ddl)


def seed_dimensions(cur: pymysql.cursors.Cursor, days: int) -> tuple[list[int], list[int], list[int], list[int], list[int]]:
    today = date.today()
    start_day = today - timedelta(days=days)

    dim_date_rows = []
    day = start_day
    while day <= today:
        dim_date_rows.append(
            (
                day,
                day.year,
                (day.month - 1) // 3 + 1,
                day.month,
                day.day,
                int(day.strftime("%W")),
                1 if day.weekday() >= 5 else 0,
            )
        )
        day += timedelta(days=1)
    cur.executemany(
        """
        INSERT IGNORE INTO dim_date (dt, year_num, quarter_num, month_num, day_num, week_num, is_weekend)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        dim_date_rows,
    )

    region_seed = [
        (1, "北京", "北京", "一线"),
        (2, "上海", "上海", "一线"),
        (3, "广东", "广州", "一线"),
        (4, "广东", "深圳", "一线"),
        (5, "浙江", "杭州", "新一线"),
        (6, "江苏", "南京", "新一线"),
        (7, "四川", "成都", "新一线"),
        (8, "重庆", "重庆", "新一线"),
        (9, "湖北", "武汉", "新一线"),
        (10, "陕西", "西安", "新一线"),
        (11, "天津", "天津", "二线"),
        (12, "山东", "青岛", "二线"),
        (13, "福建", "厦门", "二线"),
        (14, "河南", "郑州", "二线"),
        (15, "湖南", "长沙", "二线"),
    ]
    cur.executemany(
        "INSERT IGNORE INTO dim_region (region_id, province, city, city_tier) VALUES (%s, %s, %s, %s)",
        region_seed,
    )

    channel_seed = [
        (1, "自然流量", "organic"),
        (2, "搜索广告", "ad"),
        (3, "信息流广告", "ad"),
        (4, "直播渠道", "live"),
        (5, "社群裂变", "social"),
        (6, "短信召回", "crm"),
    ]
    cur.executemany(
        "INSERT IGNORE INTO dim_channel (channel_id, channel_name, source_type) VALUES (%s, %s, %s)",
        channel_seed,
    )

    campaign_rows = []
    cid = 1
    for channel_id, channel_name, _ in channel_seed:
        for idx in range(1, 9):
            s_date = today - timedelta(days=random.randint(30, days))
            e_date = min(today, s_date + timedelta(days=random.randint(7, 45)))
            campaign_rows.append(
                (
                    cid,
                    f"{channel_name}-活动{idx}",
                    channel_id,
                    random.choice(["拉新", "促活", "转化", "复购"]),
                    s_date,
                    e_date,
                )
            )
            cid += 1
    cur.executemany(
        """
        INSERT IGNORE INTO dim_campaign (campaign_id, campaign_name, channel_id, campaign_type, start_date, end_date)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        campaign_rows,
    )

    store_rows = []
    store_types = ["直营", "加盟", "仓配中心"]
    for sid in range(1, 31):
        rid = random.choice([r[0] for r in region_seed])
        store_rows.append((sid, f"门店{sid:03d}", rid, random.choice(store_types), today - timedelta(days=random.randint(80, 1200))))
    cur.executemany(
        """
        INSERT IGNORE INTO dim_store (store_id, store_name, region_id, store_type, open_date)
        VALUES (%s, %s, %s, %s, %s)
        """,
        store_rows,
    )

    supplier_rows = []
    for sid in range(1, 41):
        supplier_rows.append(
            (
                sid,
                f"供应商{sid:03d}",
                random.choice(["S", "A", "B", "C"]),
                today - timedelta(days=random.randint(120, 2000)),
            )
        )
    cur.executemany(
        """
        INSERT IGNORE INTO dim_supplier (supplier_id, supplier_name, supplier_level, cooperation_start)
        VALUES (%s, %s, %s, %s)
        """,
        supplier_rows,
    )

    return (
        [r[0] for r in region_seed],
        [r[0] for r in channel_seed],
        [r[0] for r in campaign_rows],
        [r[0] for r in store_rows],
        [r[0] for r in supplier_rows],
    )


def seed_dim_product(cur: pymysql.cursors.Cursor, supplier_ids: list[int]) -> list[int]:
    cur.execute("SELECT product_id, product_name, category, price FROM products ORDER BY product_id")
    products = cur.fetchall()
    brands = ["Aurora", "Nova", "Peak", "Ever", "Prime", "Pulse", "Zenith", "Halo", "Vector", "Ridge"]
    rows = []
    for p in products:
        rows.append(
            (
                int(p["product_id"]),
                str(p["product_name"]),
                str(p["category"]),
                random.choice(brands),
                random.choice(supplier_ids),
                1 if random.random() < 0.35 else 0,
                date.today() - timedelta(days=random.randint(60, 1400)),
                float(p["price"]),
            )
        )
    cur.executemany(
        """
        INSERT INTO dim_product (product_id, product_name, category, brand, supplier_id, is_self_operated, launch_date, list_price)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          product_name=VALUES(product_name),
          category=VALUES(category),
          brand=VALUES(brand),
          supplier_id=VALUES(supplier_id),
          is_self_operated=VALUES(is_self_operated),
          launch_date=VALUES(launch_date),
          list_price=VALUES(list_price)
        """,
        rows,
    )
    return [int(p["product_id"]) for p in products]


def seed_order_fact(
    cur: pymysql.cursors.Cursor,
    product_ids: list[int],
    user_ids: list[int],
    region_ids: list[int],
    channel_ids: list[int],
    campaign_ids: list[int],
    store_ids: list[int],
    extra_orders: int,
    days: int,
) -> tuple[list[tuple], list[tuple], list[tuple]]:
    cur.execute("SELECT COALESCE(MAX(order_id), 0) AS max_id FROM fct_order_dwd")
    max_fact_order_id = int(cur.fetchone()["max_id"])

    cur.execute("SELECT order_id, user_id, product_id, order_amt, status, created_at FROM orders ORDER BY order_id")
    base_orders = cur.fetchall()
    order_rows = []
    payment_rows = []
    refund_rows = []
    payment_id = 1
    refund_id = 1

    cur.execute("SELECT COALESCE(MAX(payment_id), 0) AS max_id FROM fct_payment_dwd")
    payment_id = int(cur.fetchone()["max_id"]) + 1
    cur.execute("SELECT COALESCE(MAX(refund_id), 0) AS max_id FROM fct_refund_dwd")
    refund_id = int(cur.fetchone()["max_id"]) + 1

    for o in base_orders:
        oid = int(o["order_id"])
        if oid <= max_fact_order_id:
            continue
        created = o["created_at"] if isinstance(o["created_at"], datetime) else dt_in_last_days(days)
        order_date = created.date()
        amt = float(o["order_amt"])
        status = str(o["status"])
        channel_id = random.choice(channel_ids)
        order_rows.append(
            (
                oid,
                created,
                order_date,
                int(o["user_id"]),
                int(o["product_id"]),
                random.choice(region_ids),
                channel_id,
                random.choice(campaign_ids),
                random.choice(store_ids),
                amt,
                status,
            )
        )
        if status in {"paid", "shipped", "completed", "refunded"}:
            pay_dt = created + timedelta(minutes=random.randint(1, 360))
            payment_rows.append((payment_id, oid, pay_dt, pay_dt.date(), random.choice(["alipay", "wechat", "bank_card"]), amt, "success"))
            payment_id += 1
        if status == "refunded" or (status in {"paid", "completed"} and random.random() < 0.035):
            refund_amt = round(amt * random.uniform(0.15, 0.95), 2)
            refund_dt = created + timedelta(days=random.randint(1, 20))
            refund_rows.append((refund_id, oid, refund_dt, refund_dt.date(), refund_amt, random.choice(["质量问题", "物流超时", "用户取消", "重复下单"])))
            refund_id += 1

    next_order_id = max(max_fact_order_id, max([int(o["order_id"]) for o in base_orders], default=0)) + 1
    statuses = ["paid", "shipped", "completed", "cancelled", "refunded"]
    for i in range(extra_orders):
        oid = next_order_id + i
        created = dt_in_last_days(days)
        order_date = created.date()
        status = random.choices(statuses, weights=[24, 20, 38, 12, 6], k=1)[0]
        amt = round(random.uniform(20, 4200), 2)
        channel_id = random.choice(channel_ids)
        order_rows.append(
            (
                oid,
                created,
                order_date,
                random.choice(user_ids),
                random.choice(product_ids),
                random.choice(region_ids),
                channel_id,
                random.choice(campaign_ids),
                random.choice(store_ids),
                amt,
                status,
            )
        )
        if status in {"paid", "shipped", "completed", "refunded"}:
            pay_dt = created + timedelta(minutes=random.randint(1, 360))
            payment_rows.append((payment_id, oid, pay_dt, pay_dt.date(), random.choice(["alipay", "wechat", "bank_card"]), amt, "success"))
            payment_id += 1
        if status == "refunded" or (status == "completed" and random.random() < 0.03):
            refund_amt = round(amt * random.uniform(0.12, 0.88), 2)
            refund_dt = created + timedelta(days=random.randint(1, 20))
            refund_rows.append((refund_id, oid, refund_dt, refund_dt.date(), refund_amt, random.choice(["质量问题", "物流超时", "用户取消", "重复下单"])))
            refund_id += 1

    cur.executemany(
        """
        INSERT IGNORE INTO fct_order_dwd (
          order_id, order_datetime, order_date, user_id, product_id, region_id, channel_id, campaign_id, store_id, order_amt, status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        order_rows,
    )
    cur.executemany(
        """
        INSERT IGNORE INTO fct_payment_dwd (payment_id, order_id, pay_datetime, pay_date, pay_method, pay_amt, pay_status)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        payment_rows,
    )
    cur.executemany(
        """
        INSERT IGNORE INTO fct_refund_dwd (refund_id, order_id, refund_datetime, refund_date, refund_amt, refund_reason)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        refund_rows,
    )
    return order_rows, payment_rows, refund_rows


def seed_event_fact(
    cur: pymysql.cursors.Cursor,
    user_ids: list[int],
    product_ids: list[int],
    channel_ids: list[int],
    total_events: int,
    days: int,
) -> list[tuple]:
    cur.execute("SELECT COALESCE(MAX(event_id), 0) AS max_id FROM fct_user_event_dwd")
    next_id = int(cur.fetchone()["max_id"]) + 1
    event_types = ["view", "search", "add_to_cart", "favorite", "purchase", "share"]
    pages = ["home", "search", "detail", "cart", "recommend", "campaign", "live_room"]
    rows = []
    for i in range(total_events):
        eid = next_id + i
        dt = dt_in_last_days(days)
        evt = random.choices(event_types, weights=[42, 17, 16, 9, 10, 6], k=1)[0]
        pid = random.choice(product_ids) if evt != "search" else None
        rows.append((eid, dt, dt.date(), random.choice(user_ids), pid, random.choice(channel_ids), evt, random.choice(pages)))
    cur.executemany(
        """
        INSERT IGNORE INTO fct_user_event_dwd (
          event_id, event_datetime, event_date, user_id, product_id, channel_id, event_type, event_page
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
    return rows


def seed_inventory_snapshot(cur: pymysql.cursors.Cursor, product_ids: list[int], store_ids: list[int], days: int) -> int:
    start = date.today() - timedelta(days=min(days, 90))
    day = start
    rows = []
    while day <= date.today():
        sample_products = random.sample(product_ids, k=min(len(product_ids), 80))
        for pid in sample_products:
            for sid in random.sample(store_ids, k=min(len(store_ids), 8)):
                on_hand = random.randint(20, 600)
                reserved = random.randint(0, min(120, on_hand))
                in_transit = random.randint(0, 200)
                rows.append((day, pid, sid, on_hand, reserved, in_transit))
        day += timedelta(days=1)
    cur.executemany(
        """
        INSERT IGNORE INTO fct_inventory_snapshot_dwd (dt, product_id, store_id, on_hand_qty, reserved_qty, in_transit_qty)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        rows,
    )
    return len(rows)


def rebuild_aggregates(cur: pymysql.cursors.Cursor) -> None:
    cur.execute("DELETE FROM dws_product_sales_1d")
    cur.execute("DELETE FROM dws_region_sales_1d")
    cur.execute("DELETE FROM dws_channel_conversion_1d")
    cur.execute("DELETE FROM dws_user_rfm")
    cur.execute("DELETE FROM ads_kpi_dashboard_1d")

    cur.execute(
        """
        SELECT
          o.order_date AS dt,
          o.product_id,
          COUNT(*) AS order_cnt,
          SUM(CASE WHEN o.status IN ('paid','shipped','completed','refunded') THEN 1 ELSE 0 END) AS paid_order_cnt,
          SUM(o.order_amt) AS gmv
        FROM fct_order_dwd o
        GROUP BY o.order_date, o.product_id
        """
    )
    product_agg = cur.fetchall()

    cur.execute(
        """
        SELECT o.order_date AS dt, o.product_id, COALESCE(SUM(r.refund_amt), 0) AS refund_amt
        FROM fct_order_dwd o
        LEFT JOIN fct_refund_dwd r ON o.order_id = r.order_id
        GROUP BY o.order_date, o.product_id
        """
    )
    refund_by_product = {(r["dt"], int(r["product_id"])): float(r["refund_amt"]) for r in cur.fetchall()}
    product_rows = [
        (
            row["dt"],
            int(row["product_id"]),
            int(row["order_cnt"]),
            int(row["paid_order_cnt"]),
            float(row["gmv"] or 0),
            float(refund_by_product.get((row["dt"], int(row["product_id"])), 0)),
        )
        for row in product_agg
    ]
    cur.executemany(
        """
        INSERT INTO dws_product_sales_1d (dt, product_id, order_cnt, paid_order_cnt, gmv, refund_amt)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        product_rows,
    )

    cur.execute(
        """
        SELECT
          o.order_date AS dt,
          o.region_id,
          COUNT(*) AS order_cnt,
          COUNT(DISTINCT o.user_id) AS buyer_cnt,
          SUM(o.order_amt) AS gmv
        FROM fct_order_dwd o
        GROUP BY o.order_date, o.region_id
        """
    )
    region_rows = [(r["dt"], int(r["region_id"]), int(r["order_cnt"]), int(r["buyer_cnt"]), float(r["gmv"] or 0)) for r in cur.fetchall()]
    cur.executemany(
        """
        INSERT INTO dws_region_sales_1d (dt, region_id, order_cnt, buyer_cnt, gmv)
        VALUES (%s, %s, %s, %s, %s)
        """,
        region_rows,
    )

    cur.execute(
        """
        SELECT event_date AS dt, channel_id, COUNT(DISTINCT user_id) AS uv,
               SUM(CASE WHEN event_type='add_to_cart' THEN 1 ELSE 0 END) AS add_cart_cnt
        FROM fct_user_event_dwd
        GROUP BY event_date, channel_id
        """
    )
    event_agg = {(r["dt"], int(r["channel_id"])): (int(r["uv"]), int(r["add_cart_cnt"])) for r in cur.fetchall()}

    cur.execute(
        """
        SELECT order_date AS dt, channel_id,
               SUM(CASE WHEN status IN ('paid','shipped','completed','refunded') THEN 1 ELSE 0 END) AS pay_order_cnt
        FROM fct_order_dwd
        GROUP BY order_date, channel_id
        """
    )
    order_agg = {(r["dt"], int(r["channel_id"])): int(r["pay_order_cnt"]) for r in cur.fetchall()}
    channel_rows = []
    all_keys = sorted(set(event_agg.keys()) | set(order_agg.keys()))
    for k in all_keys:
        uv, add_cart = event_agg.get(k, (0, 0))
        pay_cnt = order_agg.get(k, 0)
        conv = round(pay_cnt / uv, 4) if uv > 0 else 0
        channel_rows.append((k[0], k[1], uv, add_cart, pay_cnt, conv))
    cur.executemany(
        """
        INSERT INTO dws_channel_conversion_1d (dt, channel_id, uv, add_cart_cnt, pay_order_cnt, conversion_rate)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        channel_rows,
    )

    cur.execute(
        """
        SELECT user_id,
               MAX(order_date) AS last_dt,
               SUM(CASE WHEN order_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY) THEN 1 ELSE 0 END) AS freq_90d,
               SUM(CASE WHEN order_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY) AND status IN ('paid','shipped','completed','refunded')
                        THEN order_amt ELSE 0 END) AS monetary_90d
        FROM fct_order_dwd
        GROUP BY user_id
        """
    )
    user_rows = []
    today = date.today()
    for r in cur.fetchall():
        recency = (today - r["last_dt"]).days if r["last_dt"] else 9999
        freq = int(r["freq_90d"] or 0)
        monetary = float(r["monetary_90d"] or 0)
        if recency <= 14 and freq >= 8 and monetary >= 3000:
            seg = "高价值活跃"
        elif recency <= 30 and freq >= 4:
            seg = "稳定复购"
        elif recency > 60 and freq <= 1:
            seg = "沉默待召回"
        else:
            seg = "普通用户"
        user_rows.append((int(r["user_id"]), recency, freq, monetary, seg))
    cur.executemany(
        """
        INSERT INTO dws_user_rfm (user_id, recency_days, frequency_90d, monetary_90d, rfm_segment)
        VALUES (%s, %s, %s, %s, %s)
        """,
        user_rows,
    )

    cur.execute(
        """
        SELECT
          d.dt,
          COALESCE(o.order_cnt,0) AS order_cnt,
          COALESCE(o.paid_order_cnt,0) AS paid_order_cnt,
          COALESCE(o.gmv,0) AS gmv,
          COALESCE(r.refund_amt,0) AS refund_amt,
          COALESCE(e.uv,0) AS uv
        FROM dim_date d
        LEFT JOIN (
          SELECT order_date AS dt, COUNT(*) AS order_cnt,
                 SUM(CASE WHEN status IN ('paid','shipped','completed','refunded') THEN 1 ELSE 0 END) AS paid_order_cnt,
                 SUM(order_amt) AS gmv
          FROM fct_order_dwd
          GROUP BY order_date
        ) o ON d.dt = o.dt
        LEFT JOIN (
          SELECT refund_date AS dt, SUM(refund_amt) AS refund_amt
          FROM fct_refund_dwd
          GROUP BY refund_date
        ) r ON d.dt = r.dt
        LEFT JOIN (
          SELECT event_date AS dt, COUNT(DISTINCT user_id) AS uv
          FROM fct_user_event_dwd
          GROUP BY event_date
        ) e ON d.dt = e.dt
        WHERE d.dt >= DATE_SUB(CURDATE(), INTERVAL 400 DAY)
        ORDER BY d.dt
        """
    )
    ads_rows = []
    for row in cur.fetchall():
        pay_conv = round((float(row["paid_order_cnt"]) / float(row["uv"])) if float(row["uv"]) > 0 else 0, 4)
        ads_rows.append(
            (
                row["dt"],
                int(row["order_cnt"]),
                int(row["paid_order_cnt"]),
                float(row["gmv"]),
                float(row["refund_amt"]),
                int(row["uv"]),
                pay_conv,
            )
        )
    cur.executemany(
        """
        INSERT INTO ads_kpi_dashboard_1d (dt, order_cnt, paid_order_cnt, gmv, refund_amt, uv, pay_conversion_rate)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        ads_rows,
    )


def count_table(cur: pymysql.cursors.Cursor, table_name: str) -> int:
    cur.execute(f"SELECT COUNT(*) AS c FROM {table_name}")
    return int(cur.fetchone()["c"])


def main() -> None:
    args = parse_args()
    random.seed(args.seed)

    conn = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )

    try:
        with conn.cursor() as cur:
            create_schema(cur)

            region_ids, channel_ids, campaign_ids, store_ids, supplier_ids = seed_dimensions(cur, args.days)

            cur.execute("SELECT user_id FROM users ORDER BY user_id")
            user_ids = [int(r["user_id"]) for r in cur.fetchall()]
            product_ids = seed_dim_product(cur, supplier_ids)

            order_rows, payment_rows, refund_rows = seed_order_fact(
                cur,
                product_ids=product_ids,
                user_ids=user_ids,
                region_ids=region_ids,
                channel_ids=channel_ids,
                campaign_ids=campaign_ids,
                store_ids=store_ids,
                extra_orders=args.extra_orders,
                days=args.days,
            )
            event_rows = seed_event_fact(cur, user_ids=user_ids, product_ids=product_ids, channel_ids=channel_ids, total_events=args.events, days=args.days)
            inv_cnt = seed_inventory_snapshot(cur, product_ids=product_ids, store_ids=store_ids, days=args.days)
            rebuild_aggregates(cur)

            conn.commit()

            target_tables = [
                "dim_date",
                "dim_region",
                "dim_channel",
                "dim_campaign",
                "dim_store",
                "dim_supplier",
                "dim_product",
                "fct_order_dwd",
                "fct_payment_dwd",
                "fct_refund_dwd",
                "fct_user_event_dwd",
                "fct_inventory_snapshot_dwd",
                "dws_product_sales_1d",
                "dws_region_sales_1d",
                "dws_channel_conversion_1d",
                "dws_user_rfm",
                "ads_kpi_dashboard_1d",
            ]

            print("Warehouse seed completed:")
            print(f"- inserted fct_order_dwd rows: {len(order_rows)}")
            print(f"- inserted fct_payment_dwd rows: {len(payment_rows)}")
            print(f"- inserted fct_refund_dwd rows: {len(refund_rows)}")
            print(f"- inserted fct_user_event_dwd rows: {len(event_rows)}")
            print(f"- inserted fct_inventory_snapshot_dwd rows: {inv_cnt}")
            print("")
            print("Current row counts:")
            for t in target_tables:
                print(f"- {t}: {count_table(cur, t)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
