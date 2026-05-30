"""Pandas ETL: read orders, merge items, write summary."""
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine("postgresql://localhost/warehouse")

orders_sql = """
SELECT o.id, o.user_id, o.created_at
FROM orders o
WHERE o.status = 'paid'
"""
orders_df = pd.read_sql(orders_sql, engine)

items_sql = """
SELECT order_id, product_id, amount
FROM order_items
"""
items_df = pd.read_sql(items_sql, engine)

merged = pd.merge(orders_df, items_df, left_on="id", right_on="order_id", how="inner")

summary = merged.groupby(["user_id"]).agg({"amount": "sum"}).reset_index()
summary.to_sql("dwd_order_summary", engine, if_exists="replace", index=False)
