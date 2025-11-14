# scripts/query_join.py
import sqlite3
import pandas as pd
from pathlib import Path

db_path = Path(__file__).resolve().parents[1] / "data" / "ecom.db"
conn = sqlite3.connect(str(db_path))

print("Tables:")
print(pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;", conn))

print("\nCounts:")
for t in ['customers','categories','products','orders','order_items','analytics']:
    try:
        c = pd.read_sql_query(f"SELECT count(*) AS cnt FROM {t}", conn)
        print(f"{t}: {int(c['cnt'][0])} rows")
    except Exception as e:
        print(f"{t}: ERROR -> {e}")

print("\nJoin sample (10 rows):")
q = """
SELECT
  o.order_id, o.order_date,
  c.name AS customer_name,
  p.name AS product_name,
  cat.name AS category_name,
  oi.quantity, oi.unit_price,
  (oi.quantity * oi.unit_price) AS line_total,
  o.total_amount AS order_total
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
JOIN categories cat ON p.category_id = cat.category_id
LIMIT 10;
"""
print(pd.read_sql_query(q, conn))

conn.close()