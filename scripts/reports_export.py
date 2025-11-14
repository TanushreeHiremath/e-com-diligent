# scripts/reports_export.py
import sqlite3
import pandas as pd
from pathlib import Path


# Path to DB and output folder
db = Path(__file__).resolve().parents[1] / "data" / "ecom.db"
out = Path(__file__).resolve().parents[1] / "data"


conn = sqlite3.connect(str(db))

# Top customers
q1 = """
SELECT
c.customer_id,
c.name,
c.email,
SUM(o.total_amount) AS total_spent,
COUNT(o.order_id) AS num_orders
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
GROUP BY c.customer_id
ORDER BY total_spent DESC
LIMIT 10;
"""
pd.read_sql_query(q1, conn).to_csv(out / "report_top_customers.csv", index=False)

# Sales by category
q2 = """
SELECT
cat.category_id,
cat.name AS category_name,
SUM(oi.quantity) AS total_quantity_sold,
SUM(oi.quantity * oi.unit_price) AS total_revenue
FROM categories cat
JOIN products p ON p.category_id = cat.category_id
JOIN order_items oi ON oi.product_id = p.product_id
GROUP BY cat.category_id
ORDER BY total_revenue DESC;
"""
pd.read_sql_query(q2, conn).to_csv(out / "report_sales_by_category.csv", index=False)

# Full order lines
q3 = """
SELECT
o.order_id,
o.order_date,
c.customer_id,
c.name AS customer_name,
c.email AS customer_email,
p.product_id,
p.name AS product_name,
cat.category_id,
cat.name AS category_name,
oi.quantity,
oi.unit_price,
(oi.quantity * oi.unit_price) AS line_total,
o.total_amount AS order_total
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
JOIN products p ON oi.product_id = p.product_id
JOIN categories cat ON p.category_id = cat.category_id
ORDER BY o.order_id, oi.order_item_id;
"""