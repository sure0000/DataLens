#!/usr/bin/env python3
from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta

import pymysql


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed more data into existing ecommerce MySQL tables.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--database", default="ecommerce")
    parser.add_argument("--users", type=int, default=300)
    parser.add_argument("--products", type=int, default=120)
    parser.add_argument("--orders", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20260429)
    return parser.parse_args()


def next_id(cur: pymysql.cursors.Cursor, table_name: str, id_col: str) -> int:
    cur.execute(f"SELECT COALESCE(MAX({id_col}), 0) + 1 AS next_id FROM {table_name}")
    return int(cur.fetchone()["next_id"])


def dt_in_last_days(days: int) -> datetime:
    return datetime.now() - timedelta(
        days=random.randint(0, days), hours=random.randint(0, 23), minutes=random.randint(0, 59), seconds=random.randint(0, 59)
    )


def ensure_minimal_schema(cur: pymysql.cursors.Cursor) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
          id BIGINT PRIMARY KEY,
          category_name VARCHAR(64) NOT NULL,
          category_level INT NOT NULL DEFAULT 1
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
          user_id BIGINT PRIMARY KEY,
          user_name VARCHAR(64) NOT NULL,
          city VARCHAR(64) NOT NULL,
          created_at DATETIME NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
          product_id BIGINT PRIMARY KEY,
          product_name VARCHAR(128) NOT NULL,
          category VARCHAR(64) NOT NULL,
          price DECIMAL(10,2) NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
          order_id BIGINT PRIMARY KEY,
          user_id BIGINT NOT NULL,
          product_id BIGINT NOT NULL,
          order_amt DECIMAL(12,2) NOT NULL,
          status VARCHAR(32) NOT NULL,
          created_at DATETIME NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def seed_categories(cur: pymysql.cursors.Cursor) -> list[str]:
    cats = ["手机数码", "电脑办公", "家电", "食品生鲜", "服饰鞋包", "美妆个护", "运动户外", "母婴用品", "图书文娱", "家居家装"]
    start = next_id(cur, "categories", "id")
    rows = [(start + i, c, 1) for i, c in enumerate(cats)]
    cur.executemany("INSERT INTO categories (id, category_name, category_level) VALUES (%s, %s, %s)", rows)
    return cats


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

    cities = ["上海", "北京", "广州", "深圳", "杭州", "南京", "成都", "重庆", "武汉", "西安", "苏州", "天津"]
    statuses = ["paid", "shipped", "completed", "cancelled", "refunded"]

    try:
        with conn.cursor() as cur:
            ensure_minimal_schema(cur)

            categories = seed_categories(cur)

            user_start = next_id(cur, "users", "user_id")
            users = []
            for i in range(args.users):
                uid = user_start + i
                users.append((uid, f"用户{uid}", random.choice(cities), dt_in_last_days(900).strftime("%Y-%m-%d %H:%M:%S")))
            cur.executemany("INSERT INTO users (user_id, user_name, city, created_at) VALUES (%s, %s, %s, %s)", users)

            product_start = next_id(cur, "products", "product_id")
            products = []
            price_map: dict[int, float] = {}
            for i in range(args.products):
                pid = product_start + i
                cat = random.choice(categories)
                price = round(random.uniform(19, 4999), 2)
                products.append((pid, f"{cat}-商品{pid}", cat, price))
                price_map[pid] = price
            cur.executemany("INSERT INTO products (product_id, product_name, category, price) VALUES (%s, %s, %s, %s)", products)

            all_user_ids = [u[0] for u in users]
            all_product_ids = [p[0] for p in products]

            order_start = next_id(cur, "orders", "order_id")
            orders = []
            for i in range(args.orders):
                oid = order_start + i
                uid = random.choice(all_user_ids)
                pid = random.choice(all_product_ids)
                qty = random.randint(1, 4)
                amount = round(price_map[pid] * qty * random.uniform(0.85, 1.05), 2)
                orders.append((oid, uid, pid, amount, random.choices(statuses, weights=[26, 21, 33, 12, 8], k=1)[0], dt_in_last_days(365).strftime("%Y-%m-%d %H:%M:%S")))
            cur.executemany(
                "INSERT INTO orders (order_id, user_id, product_id, order_amt, status, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                orders,
            )

            conn.commit()
            print("Seed completed:")
            print(f"- categories: +{len(categories)}")
            print(f"- users: +{len(users)}")
            print(f"- products: +{len(products)}")
            print(f"- orders: +{len(orders)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
